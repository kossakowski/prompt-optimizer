#!/usr/bin/env python3
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Callable

# --- Configuration & Defaults ---
# Hardcoded fallbacks in case config.json is missing
FALLBACK_GEMINI_MODEL = "gemini-3-pro-preview"
FALLBACK_CODEX_MODEL = "gpt-5.2-codex"
FALLBACK_CODEX_REASONING = "high"
FALLBACK_REASONING_LEVELS = ["minimal", "low", "medium", "high", "xhigh"]

def load_external_config():
    """Loads configuration from config.json if it exists."""
    config_path = Path("config.json")
    defaults = {
        "gemini_default_model": FALLBACK_GEMINI_MODEL,
        "codex_default_model": FALLBACK_CODEX_MODEL,
        "codex_reasoning_default": FALLBACK_CODEX_REASONING,
        "codex_reasoning_levels": FALLBACK_REASONING_LEVELS,
        "gemini_known_models": [FALLBACK_GEMINI_MODEL],
        "codex_known_models": [FALLBACK_CODEX_MODEL]
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                defaults.update(user_config)
        except Exception as e:
            print(f"Warning: Failed to load config.json: {e}", file=sys.stderr)
            
    return defaults

# Load Global Config
GLOBAL_CONFIG = load_external_config()

DEFAULT_GEMINI_MODEL = GLOBAL_CONFIG["gemini_default_model"]
DEFAULT_CODEX_MODEL = GLOBAL_CONFIG["codex_default_model"]
DEFAULT_CODEX_REASONING = GLOBAL_CONFIG["codex_reasoning_default"]
VALID_REASONING_LEVELS = set(GLOBAL_CONFIG["codex_reasoning_levels"])
GEMINI_KNOWN_MODELS = GLOBAL_CONFIG["gemini_known_models"]
CODEX_KNOWN_MODELS = GLOBAL_CONFIG["codex_known_models"]

DEFAULT_TIMEOUT = 300

@dataclass
class Config:
    models_csv: str
    iterations: int
    prompt_text: Optional[str]
    prompt_file: Optional[Path]
    context_files: List[Path]
    outdir: Path
    gemini_model: str
    codex_model: str
    codex_reasoning: str
    merge_codex_model: Optional[str] # This field name is legacy but we will use it for "merge_model"
    merge_provider: str # New field: 'gemini' or 'codex'
    merge_reasoning: Optional[str]
    merge_prompt_text: Optional[str]
    merge_prompt_file: Optional[Path]
    merge_context_files: List[Path]
    timeout: int
    output_format: str
    require_git: bool
    generate_pre_report: bool
    generate_post_report: bool

# --- Utils ---
def die(message: str):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)

def sanitize_label(text: str) -> str:
    """Replaces non-alphanumeric chars (except ._-) with _."""
    return re.sub(r'[^a-zA-Z0-9._-]', '_', text)

def text_to_rtf(text: str) -> str:
    """Converts plain text to basic RTF."""
    header = r"{\rtf1\ansi\deff0{\fonttbl{\f0\fswiss\fcharset0 Arial;}}\viewkind4\uc1\pard\f0\fs24 "
    footer = r"}"
    
    escaped = text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
    escaped = escaped.replace('\n', '\\par\n')
    
    res = []
    for char in escaped:
        if ord(char) > 127:
            res.append(f"\\u{ord(char)}?")
        else:
            res.append(char)
            
    return header + "".join(res) + footer

def create_docx(text: str, output_path: Path):
    """Creates a minimal valid .docx file from plain text using standard zipfile."""
    # 1. [Content_Types].xml
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    # 2. _rels/.rels
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    # 3. word/document.xml
    # Escape XML characters
    escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Split lines into paragraphs
    paragraphs = []
    for line in escaped_text.split('\n'):
        paragraphs.append(f'<w:p><w:r><w:t>{line}</w:t></w:r></w:p>')
    
    body_content = "".join(paragraphs)
    
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        {body_content}
    </w:body>
</w:document>"""

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', document_xml)

def generate_html_report(title: str, sections: List[Dict[str, str]], output_path: Path):
    """Generates a beautiful HTML report."""
    css = """
    :root { --primary: #2563eb; --bg: #f8fafc; --card-bg: #ffffff; --text: #1e293b; }
    body { font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; background: var(--bg); color: var(--text); margin: 0; padding: 2rem; }
    .container { max-width: 900px; margin: 0 auto; }
    h1 { color: var(--primary); border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; }
    .card { background: var(--card-bg); border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 2rem; overflow: hidden; }
    .card-header { background: #f1f5f9; padding: 1rem 1.5rem; font-weight: bold; color: #334155; border-bottom: 1px solid #e2e8f0; }
    .card-body { padding: 1.5rem; overflow-x: auto; }
    pre { background: #1e293b; color: #f8fafc; padding: 1rem; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; }
    """
    
    html_parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
"""]

    for section in sections:
        content = section.get('content', '')
        # Simple auto-formatting: if it looks like code, wrap in pre, else generic div
        if section.get('is_code', False):
            formatted_content = f"<pre>{content}</pre>"
        else:
            # Convert newlines to breaks for basic text
            formatted_content = f"<div>{content.replace(chr(10), '<br>')}</div>"
            
        html_parts.append(f"""
        <div class="card">
            <div class="card-header">{section.get('title', 'Section')}</div>
            <div class="card-body">{formatted_content}</div>
        </div>
""")

    html_parts.append("""
    </div>
</body>
</html>""")
    
    output_path.write_text("".join(html_parts), encoding='utf-8')

# --- Runners ---
class LLMRunner:
    def __init__(self, executable: str):
        self.executable = executable

    def check_dependency(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(self, prompt_path: Path, output_path: Path, log_path: Path, 
            timeout: int, **kwargs) -> bool:
        raise NotImplementedError

class GeminiRunner(LLMRunner):
    def __init__(self):
        super().__init__("gemini")

    def run(self, prompt_path: Path, output_path: Path, log_path: Path, 
            timeout: int, model: str = "") -> bool:
        
        json_out = output_path.with_suffix(".json")
        cmd = [self.executable, "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])
        
        # Environment setup for NO_COLOR (mimicking bash)
        env = os.environ.copy()
        env["NO_COLOR"] = "1"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f_in, \
                 open(json_out, 'w', encoding='utf-8') as f_out, \
                 open(log_path, 'w', encoding='utf-8') as f_err:
                
                subprocess.run(cmd, stdin=f_in, stdout=f_out, stderr=f_err, 
                               timeout=timeout if timeout > 0 else None, 
                               env=env, check=True)

            # Parse JSON output
            with open(json_out, 'r', encoding='utf-8') as f:
                data = json.load(f)
                response = data.get("response", "") or ""
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response)
                
            return True

        except subprocess.CalledProcessError as e:
            err_msg = f"[gemini] ERROR: Command failed with exit code {e.returncode}."
            try:
                if log_path.exists():
                    err_content = log_path.read_text(encoding='utf-8').strip()
                    if err_content:
                        err_msg += f"\n--- STDERR ---\n{err_content}\n--------------"
            except Exception:
                pass
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(err_msg)
            return False

        except (subprocess.TimeoutExpired, json.JSONDecodeError, IOError) as e:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"[gemini] ERROR: {str(e)} (see {log_path})")
            return False

class CodexRunner(LLMRunner):
    def __init__(self):
        super().__init__("codex")

    def run(self, prompt_path: Path, output_path: Path, log_path: Path, 
            timeout: int, model: str = "", reasoning: str = "high", 
            require_git: bool = False) -> bool:
        
        cmd = [self.executable, "exec", "--sandbox", "read-only", "--color", "never"]
        if not require_git:
            cmd.append("--skip-git-repo-check")
        if model:
            cmd.extend(["--model", model])
        
        cmd.extend(["--config", f'model_reasoning_effort="{reasoning}"'])
        cmd.append("-") # Read from stdin

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f_in, \
                 open(output_path, 'w', encoding='utf-8') as f_out, \
                 open(log_path, 'w', encoding='utf-8') as f_err:
                 
                subprocess.run(cmd, stdin=f_in, stdout=f_out, stderr=f_err, 
                               timeout=timeout if timeout > 0 else None, 
                               check=True)
            return True
        except subprocess.CalledProcessError as e:
            # Try to read the error log to provide more context
            err_msg = f"[codex] ERROR: Command failed with exit code {e.returncode}."
            try:
                if log_path.exists():
                    err_content = log_path.read_text(encoding='utf-8').strip()
                    if err_content:
                        err_msg += f"\n--- STDERR ---\n{err_content}\n--------------"
            except Exception:
                pass
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(err_msg)
            return False
        except (subprocess.TimeoutExpired, IOError) as e:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"[codex] ERROR: {str(e)} (see {log_path})")
            return False

# --- Main Application ---
class EnsembleApp:
    def __init__(self, config: Config, logger: Optional[Callable[[str], None]] = None):
        self.cfg = config
        self.gemini_runner = GeminiRunner()
        self.codex_runner = CodexRunner()
        self.runners_list = [] # List of tuples: (provider, model, label)
        self.merge_codex_model = ""
        self.logger = logger or (lambda msg: None)

    def log(self, message: str):
        """Sends message to the configured logger."""
        self.logger(message)

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts text from a PDF file using pdftotext (CLI)."""
        if shutil.which("pdftotext"):
            try:
                # Run pdftotext, output to stdout (-)
                result = subprocess.run(
                    ["pdftotext", "-layout", str(pdf_path), "-"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.stdout
            except subprocess.CalledProcessError as e:
                self.log(f"Error reading PDF {pdf_path}: {e.stderr}")
                return f"[Error extracting text from PDF: {pdf_path.name}]"
        else:
             self.log(f"Warning: 'pdftotext' tool not found. Skipping PDF content: {pdf_path}")
             return f"[Missing 'pdftotext' tool - could not read {pdf_path.name}]"

    def extract_text_from_docx(self, docx_path: Path) -> str:
        """Extracts text from a .docx file using standard zipfile/xml libraries."""
        try:
            with zipfile.ZipFile(docx_path) as zf:
                xml_content = zf.read('word/document.xml')
            
            root = ET.fromstring(xml_content)
            
            # XML Namespace for Word
            # Usually w is http://schemas.openxmlformats.org/wordprocessingml/2006/main
            # But ElementTree handling of namespaces can be verbose.
            # We simply look for all text nodes.
            
            text_parts = []
            # Iterate over all paragraph elements
            # In OpenXML, text is inside <w:p> -> <w:r> -> <w:t>
            # We define the namespace map
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            for p in root.findall('.//w:p', ns):
                p_text = []
                for t in p.findall('.//w:t', ns):
                    if t.text:
                        p_text.append(t.text)
                text_parts.append("".join(p_text))
            
            return "\n".join(text_parts)

        except Exception as e:
            self.log(f"Error reading DOCX {docx_path}: {e}")
            return f"[Error extracting text from DOCX: {docx_path.name}]"

    def process_context_files(self, file_list: List[Path]) -> str:
        """Reads and formats a list of context files."""
        formatted_content = []
        for ctx_file in file_list:
            if not ctx_file.exists():
                die(f"Context file not found: {ctx_file}")
            
            ctx_text = ""
            suffix = ctx_file.suffix.lower()
            
            if suffix == '.pdf':
                ctx_text = self.extract_text_from_pdf(ctx_file)
            elif suffix == '.docx':
                ctx_text = self.extract_text_from_docx(ctx_file)
            else:
                try:
                    # Basic binary check
                    raw_ctx = ctx_file.read_bytes()
                    if b'\0' in raw_ctx:
                        die(f"Context file appears to be binary: {ctx_file}")
                    
                    ctx_text = raw_ctx.decode('utf-8')
                except UnicodeDecodeError:
                    ctx_text = raw_ctx.decode('latin-1', errors='replace')
                    self.log(f"Warning: Converted context file {ctx_file} using fallback encoding.")
            
            formatted_content.append(f"[Context File: {ctx_file.name}]\n<<<\n{ctx_text}\n>>>\n")
        
        return "".join(formatted_content)

    def generate_pre_merge_report(self, result_files: List[Path], instruction: str):
        """Generates the Pre-Merge report. Exposed for HITL usage."""
        # We need to construct the context block again if not cached, 
        # or we just re-read the context files.
        # Ideally, we should reuse prompt construction logic.
        
        # Original Prompt
        original_prompt = ""
        if self.prompt_canon.exists():
            original_prompt = self.prompt_canon.read_text(encoding='utf-8')
            
        merge_ctx_block = self.process_context_files(self.cfg.merge_context_files)

        sections = [
            {"title": "Proposed Merge Instruction", "content": instruction},
            {"title": "Original Prompt & Context", "content": original_prompt, "is_code": True},
        ]
        if merge_ctx_block:
            sections.append({"title": "Merge Context", "content": merge_ctx_block, "is_code": True})
        
        # Add Candidates
        for res_file in result_files:
            c_content = res_file.read_text(encoding='utf-8', errors='replace') if res_file.exists() else "[Missing]"
            sections.append({"title": f"Candidate: {res_file.name}", "content": c_content, "is_code": True})
            
        generate_html_report("LLM Ensemble: Pre-Merge Report", sections, self.cfg.outdir / "pre_report.html")
        self.log(f"[Generated Pre-Report: {self.cfg.outdir / 'pre_report.html'}]")

    def validate_and_setup(self):
        # 1. Output Directory
        if not self.cfg.outdir.exists():
            try:
                self.cfg.outdir.mkdir(parents=True)
            except OSError as e:
                die(f"Cannot create outdir: {self.cfg.outdir} - {e}")
        
        # Create Runs subdirectory
        self.runs_dir = self.cfg.outdir / "Runs"
        try:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            die(f"Cannot create runs dir: {self.runs_dir} - {e}")
        
        # 2. Prompt Processing
        self.prompt_canon = self.cfg.outdir / "prompt.txt"
        
        # --- Context Processing ---
        context_block = self.process_context_files(self.cfg.context_files)

        # --- Main Prompt Processing ---
        content = ""
        
        if self.cfg.prompt_file:
            if not self.cfg.prompt_file.exists():
                die(f"Prompt file not found: {self.cfg.prompt_file}")
            if self.cfg.prompt_file.stat().st_size == 0:
                die(f"Prompt file is empty: {self.cfg.prompt_file}")
            
            # Binary check & Reading
            try:
                # First try reading as utf-8
                content = self.cfg.prompt_file.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # If utf-8 fails, check for null bytes to detect binary
                raw = self.cfg.prompt_file.read_bytes()
                if b'\0' in raw:
                    die(f"Prompt file appears to be binary: {self.cfg.prompt_file}")
                # Try latin-1 as fallback for non-utf8 text
                content = raw.decode('latin-1', errors='replace')
                self.log(f"Warning: Converted {self.cfg.prompt_file} to UTF-8 using fallback encoding.")
        
        elif self.cfg.prompt_text:
            content = self.cfg.prompt_text
        else:
            # Stdin check
            if not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                die("No prompt provided. Use --prompt, --prompt-file, or pipe stdin.")

        final_prompt_content = []
        if context_block:
            final_prompt_content.append(context_block)
        
        if final_prompt_content:
            final_prompt_content.append("USER PROMPT:\n")
        final_prompt_content.append(content)
        
        self.prompt_canon.write_text("".join(final_prompt_content), encoding='utf-8')

        # 3. Parse Models
        # Input: "gemini:modelA,codex,codex:modelB"
        raw_list = [x.strip() for x in self.cfg.models_csv.split(',')]
        found_codex_model = None

        for raw in raw_list:
            raw = raw.lower().replace(" ", "")
            if not raw: continue
            
            parts = raw.split(':', 1)
            provider = parts[0]
            model = parts[1] if len(parts) > 1 else ""

            if provider == 'gemini':
                if not model: model = self.cfg.gemini_model
                label = f"gemini__{sanitize_label(model)}"
                self.runners_list.append(('gemini', model, label))
            
            elif provider == 'codex':
                if not model: model = self.cfg.codex_model
                label = f"codex__{sanitize_label(model)}"
                self.runners_list.append(('codex', model, label))
                if not found_codex_model and model:
                    found_codex_model = model
            else:
                die(f"Unknown provider in --models: {provider} (allowed: gemini, codex)")

        if not self.runners_list:
            die("No valid runners parsed from --models")

        # 4. Resolve Merge Model
        if self.cfg.merge_codex_model:
            self.merge_codex_model = self.cfg.merge_codex_model
        elif found_codex_model:
            self.merge_codex_model = found_codex_model
        else:
            self.merge_codex_model = self.cfg.codex_model

        # 5. Check Dependencies
        need_gemini = any(r[0] == 'gemini' for r in self.runners_list)
        if need_gemini and not self.gemini_runner.check_dependency():
            die("gemini command not found on PATH.")
        if not self.codex_runner.check_dependency():
            die("codex command not found on PATH. (Needed at least for the final merge.)")


    def execute_parallel(self) -> List[Path]:
        tasks = []
        # Format: (provider, model, label, iteration_idx)
        for provider, model, label in self.runners_list:
            for i in range(1, self.cfg.iterations + 1):
                tasks.append((provider, model, label, i))
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_task = {}
            for t in tasks:
                provider, model, label, i = t
                base_name = f"{label}_run_{i}"
                out_txt = self.runs_dir / f"{base_name}.txt"
                log_file = self.runs_dir / f"{base_name}.log"
                
                self.log(f"Scheduling {provider} model='{model}' ({i}/{self.cfg.iterations})...")
                
                if provider == 'gemini':
                    future = executor.submit(self.gemini_runner.run, self.prompt_canon, out_txt, log_file, self.cfg.timeout, model=model)
                else: # codex
                    future = executor.submit(self.codex_runner.run, self.prompt_canon, out_txt, log_file, self.cfg.timeout, 
                                             model=model, reasoning=self.cfg.codex_reasoning, require_git=self.cfg.require_git)
                
                future_to_task[future] = (out_txt, provider, model, i)

            for future in concurrent.futures.as_completed(future_to_task):
                out_path, provider, model, i = future_to_task[future]
                try:
                    future.result() # Wait for completion
                    results.append(out_path)
                    self.log(f"Finished {provider} ({i}/{self.cfg.iterations})")
                except Exception as e:
                    self.log(f"Unexpected error in thread: {e}")
        
        # Sort results to ensure deterministic order if needed (e.g. by name)
        results.sort(key=lambda p: p.name)
        return results

    def merge(self, result_files: List[Path]):
        merge_prompt_path = self.cfg.outdir / "merge_prompt.txt"
        final_out = self.cfg.outdir / "final.txt"
        final_log = self.cfg.outdir / "final.log"

        # Determine merge instruction
        default_instruction = """You are given:
1) The user's original prompt.
2) Multiple candidate answers generated by different models and/or runs.

Task:
- Produce a single best final answer to the user's original prompt.
- Combine the strongest parts of the candidates, fix mistakes, resolve contradictions.
- If something is uncertain, say so plainly.
- Do NOT mention the candidates, tools, or your merging process.
- Output ONLY the final answer.

USER PROMPT:
<<<
"""
        
        instruction = default_instruction
        if self.cfg.merge_prompt_file:
             if self.cfg.merge_prompt_file.exists():
                 instruction = self.cfg.merge_prompt_file.read_text(encoding='utf-8')
             else:
                 die(f"Merge prompt file not found: {self.cfg.merge_prompt_file}")
        elif self.cfg.merge_prompt_text:
            instruction = self.cfg.merge_prompt_text

        # Process Merge Context Files
        merge_ctx_block = self.process_context_files(self.cfg.merge_context_files)

        # Build merge content
        with open(merge_prompt_path, 'w', encoding='utf-8') as f:
            f.write(instruction)
            if merge_ctx_block:
                f.write("\n\nMERGE CONTEXT:\n")
                f.write(merge_ctx_block)
            f.write("\n\nORIGINAL PROMPT & CONTEXT:\n")
            f.write(self.prompt_canon.read_text(encoding='utf-8'))
            f.write("\n>>>\n\nCANDIDATE ANSWERS:\n")
            
            for res_file in result_files:
                f.write(f"\n--- {res_file.name} ---\n<<<\n")
                if res_file.exists():
                    f.write(res_file.read_text(encoding='utf-8', errors='replace'))
                else:
                    f.write("[File missing]")
                f.write("\n>>>\n")
            
            f.write("\n\nFINAL ANSWER (output only this):\n")

        # --- PRE-REPORT ---
        if self.cfg.generate_pre_report:
            sections = [
                {"title": "Merge Instruction", "content": instruction},
                {"title": "Original Prompt & Context", "content": self.prompt_canon.read_text(encoding='utf-8'), "is_code": True},
            ]
            if merge_ctx_block:
                sections.append({"title": "Merge Context", "content": merge_ctx_block, "is_code": True})
            
            # Add Candidates
            for res_file in result_files:
                c_content = res_file.read_text(encoding='utf-8', errors='replace') if res_file.exists() else "[Missing]"
                sections.append({"title": f"Candidate: {res_file.name}", "content": c_content, "is_code": True})
                
            generate_html_report("LLM Ensemble: Pre-Merge Report", sections, self.cfg.outdir / "pre_report.html")
            self.log(f"[Generated Pre-Report: {self.cfg.outdir / 'pre_report.html'}]")

        # Run Merge
        reasoning = self.cfg.merge_reasoning or self.cfg.codex_reasoning
        merge_model = self.merge_codex_model
        provider = self.cfg.merge_provider
        
        self.log(f"Merging with {provider} model='{merge_model}' reasoning='{reasoning if provider=='codex' else 'N/A'}'...")
        
        success = False
        if provider == 'gemini':
            success = self.gemini_runner.run(merge_prompt_path, final_out, final_log, self.cfg.timeout, model=merge_model)
        else:
            success = self.codex_runner.run(merge_prompt_path, final_out, final_log, self.cfg.timeout, 
                                  model=merge_model, reasoning=reasoning, require_git=self.cfg.require_git)
        
        # Display and Format
        final_text = ""
        if success and final_out.exists():
            final_text = final_out.read_text(encoding='utf-8')
            self.log(f"\n=== FINAL ANSWER ===\n{final_text}\n")
            
            if self.cfg.output_format == 'rtf':
                rtf_content = text_to_rtf(final_text)
                rtf_path = self.cfg.outdir / "final.rtf"
                rtf_path.write_text(rtf_content, encoding='utf-8')
                self.log(f"[Generated RTF: {rtf_path}]")
            
            elif self.cfg.output_format == 'docx':
                docx_path = self.cfg.outdir / "final.docx"
                try:
                    create_docx(final_text, docx_path)
                    self.log(f"[Generated DOCX: {docx_path}]")
                except Exception as e:
                    self.log(f"Error creating DOCX: {e}")

        else:
             self.log("Warning: Final output not generated.")

        # --- POST-REPORT ---
        if self.cfg.generate_post_report:
            sections = [
                {"title": "Final Answer", "content": final_text or "[No Output Generated]", "is_code": False},
                {"title": "Execution Summary", "content": f"Output Directory: {self.cfg.outdir}\nModels: {self.cfg.models_csv}\nIterations: {self.cfg.iterations}"}
            ]
            
            # Include Merge Logs if any
            if final_log.exists():
                log_content = final_log.read_text(encoding='utf-8').strip()
                if log_content:
                    sections.append({"title": "Merge Logs/Errors", "content": log_content, "is_code": True})
            
            generate_html_report("LLM Ensemble: Post-Merge Report", sections, self.cfg.outdir / "post_report.html")
            self.log(f"[Generated Post-Report: {self.cfg.outdir / 'post_report.html'}]")

        self.log(f"\n[Saved artifacts in: {self.cfg.outdir}]")


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="LLM Ensemble Orchestrator")
    
    # Required
    parser.add_argument("-m", "--models", required=True, help="Comma-separated list of providers/models")
    parser.add_argument("-n", "--iterations", required=True, type=int, help="Number of iterations per model")
    
    # Prompts
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--prompt", help="Prompt text")
    group.add_argument("-f", "--prompt-file", type=Path, help="Prompt file path")
    parser.add_argument("positional_prompt", nargs="?", help="Positional prompt text")

    parser.add_argument("-c", "--context", action="append", type=Path, dest="context_files", help="Additional context file (can be used multiple times)")
    parser.add_argument("-mc", "--merge-context", action="append", type=Path, dest="merge_context_files", help="Context file for merge step only (repeatable)")

    # Options
    parser.add_argument("-o", "--outdir", type=Path, help="Output directory")
    
    # Defaults
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL, help=f"Default: {DEFAULT_GEMINI_MODEL}")
    parser.add_argument("--codex-model", default=DEFAULT_CODEX_MODEL, help=f"Default: {DEFAULT_CODEX_MODEL}")
    parser.add_argument("--codex-reasoning", default=DEFAULT_CODEX_REASONING, choices=VALID_REASONING_LEVELS, help=f"Default: {DEFAULT_CODEX_REASONING}")
    
    parser.add_argument("--merge-codex-model", help="Model for merging (Gemini or Codex)")
    parser.add_argument("--merge-reasoning", choices=VALID_REASONING_LEVELS, help="Reasoning for merging")
    
    merge_group = parser.add_mutually_exclusive_group()
    merge_group.add_argument("--merge-prompt", help="Custom merge instruction")
    merge_group.add_argument("--merge-prompt-file", type=Path, help="Custom merge instruction file")
    
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--format", dest="output_format", choices=['txt', 'rtf', 'docx'], default="txt", help="Output format")
    parser.add_argument("--require-git", action="store_true", help="Enable Codex git repo check")
    
    # Report flags (Defaults true for GUI parity, but let's make them flags here)
    parser.add_argument("--no-pre-report", action="store_false", dest="generate_pre_report", help="Disable Pre-Merge HTML Report")
    parser.add_argument("--no-post-report", action="store_false", dest="generate_post_report", help="Disable Post-Merge HTML Report")
    parser.set_defaults(generate_pre_report=True, generate_post_report=True)

    args = parser.parse_args()

    # Validate iterations
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    # Handle prompts
    prompt_text = args.prompt
    if args.positional_prompt:
        if prompt_text:
            parser.error("Multiple prompt arguments provided.")
        prompt_text = args.positional_prompt
        
    if args.prompt_file and prompt_text:
        parser.error("Use only one of --prompt (or positional) or --prompt-file")
    
    if not args.outdir:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Default: ./Outputs/llm_ensemble_TIMESTAMP
        args.outdir = Path("Outputs") / f"llm_ensemble_{ts}"

    merge_provider = "codex"
    if args.merge_codex_model and "gemini" in args.merge_codex_model.lower():
        merge_provider = "gemini"

    return Config(
        models_csv=args.models,
        iterations=args.iterations,
        prompt_text=prompt_text,
        prompt_file=args.prompt_file,
        context_files=args.context_files or [],
        outdir=args.outdir,
        gemini_model=args.gemini_model,
        codex_model=args.codex_model,
        codex_reasoning=args.codex_reasoning,
        merge_codex_model=args.merge_codex_model, # Now holds either model
        merge_provider=merge_provider,
        merge_reasoning=args.merge_reasoning,
        merge_prompt_text=args.merge_prompt,
        merge_prompt_file=args.merge_prompt_file,
        merge_context_files=args.merge_context_files or [],
        timeout=args.timeout,
        output_format=args.output_format,
        require_git=args.require_git,
        generate_pre_report=args.generate_pre_report,
        generate_post_report=args.generate_post_report
    )

def main():
    config = parse_args()
    # Default CLI logger prints to stderr
    app = EnsembleApp(config, logger=lambda msg: print(msg, file=sys.stderr))
    app.validate_and_setup()
    results = app.execute_parallel()
    app.merge(results)

if __name__ == "__main__":
    main()
