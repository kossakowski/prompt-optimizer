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
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

# --- Configuration & Defaults ---
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_CODEX_MODEL = "gpt-5.2-codex"
DEFAULT_CODEX_REASONING = "high"
VALID_REASONING_LEVELS = {"minimal", "low", "medium", "high", "xhigh"}
DEFAULT_TIMEOUT = 300

@dataclass
class Config:
    models_csv: str
    iterations: int
    prompt_text: Optional[str]
    prompt_file: Optional[Path]
    outdir: Path
    gemini_model: str
    codex_model: str
    codex_reasoning: str
    merge_codex_model: Optional[str]
    merge_reasoning: Optional[str]
    merge_prompt_text: Optional[str]
    merge_prompt_file: Optional[Path]
    timeout: int
    output_format: str
    require_git: bool

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

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, IOError) as e:
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
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, IOError) as e:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"[codex] ERROR: {str(e)} (see {log_path})")
            return False

# --- Main Application ---
class EnsembleApp:
    def __init__(self, config: Config):
        self.cfg = config
        self.gemini_runner = GeminiRunner()
        self.codex_runner = CodexRunner()
        self.runners_list = [] # List of tuples: (provider, model, label)
        self.merge_codex_model = ""

    def validate_and_setup(self):
        # 1. Output Directory
        if not self.cfg.outdir.exists():
            try:
                self.cfg.outdir.mkdir(parents=True)
            except OSError as e:
                die(f"Cannot create outdir: {self.cfg.outdir} - {e}")
        
        # 2. Prompt Processing
        self.prompt_canon = self.cfg.outdir / "prompt.txt"
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
                print(f"Warning: Converted {self.cfg.prompt_file} to UTF-8 using fallback encoding.", file=sys.stderr)
        
        elif self.cfg.prompt_text:
            content = self.cfg.prompt_text
        else:
            # Stdin check
            if not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                die("No prompt provided. Use --prompt, --prompt-file, or pipe stdin.")

        self.prompt_canon.write_text(content, encoding='utf-8')

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
                out_txt = self.cfg.outdir / f"{base_name}.txt"
                log_file = self.cfg.outdir / f"{base_name}.log"
                
                print(f"Scheduling {provider} model='{model}' ({i}/{self.cfg.iterations})...", file=sys.stderr)
                
                if provider == 'gemini':
                    future = executor.submit(self.gemini_runner.run, self.prompt_canon, out_txt, log_file, self.cfg.timeout, model=model)
                else: # codex
                    future = executor.submit(self.codex_runner.run, self.prompt_canon, out_txt, log_file, self.cfg.timeout, 
                                             model=model, reasoning=self.cfg.codex_reasoning, require_git=self.cfg.require_git)
                
                future_to_task[future] = out_txt

            for future in concurrent.futures.as_completed(future_to_task):
                out_path = future_to_task[future]
                try:
                    future.result() # Wait for completion
                    results.append(out_path)
                except Exception as e:
                    print(f"Unexpected error in thread: {e}", file=sys.stderr)
        
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

        # Build merge content
        with open(merge_prompt_path, 'w', encoding='utf-8') as f:
            f.write(instruction)
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

        # Run Merge
        reasoning = self.cfg.merge_reasoning or self.cfg.codex_reasoning
        print(f"Merging with Codex model='{self.merge_codex_model}' reasoning='{reasoning}'...", file=sys.stderr)
        
        self.codex_runner.run(merge_prompt_path, final_out, final_log, self.cfg.timeout, 
                              model=self.merge_codex_model, reasoning=reasoning, require_git=self.cfg.require_git)
        
        # Formatting
        if self.cfg.output_format == 'rtf':
            if final_out.exists():
                text = final_out.read_text(encoding='utf-8')
                rtf_content = text_to_rtf(text)
                rtf_path = self.cfg.outdir / "final.rtf"
                rtf_path.write_text(rtf_content, encoding='utf-8')
                print(f"[Generated RTF: {rtf_path}]", file=sys.stderr)
            else:
                 print(f"Warning: Final output not generated, cannot convert to RTF.", file=sys.stderr)
        else:
            if final_out.exists():
                print(final_out.read_text(encoding='utf-8'))

        print(f"\n[Saved artifacts in: {self.cfg.outdir}]", file=sys.stderr)


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

    # Options
    parser.add_argument("-o", "--outdir", type=Path, help="Output directory")
    
    # Defaults
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL, help=f"Default: {DEFAULT_GEMINI_MODEL}")
    parser.add_argument("--codex-model", default=DEFAULT_CODEX_MODEL, help=f"Default: {DEFAULT_CODEX_MODEL}")
    parser.add_argument("--codex-reasoning", default=DEFAULT_CODEX_REASONING, choices=VALID_REASONING_LEVELS, help=f"Default: {DEFAULT_CODEX_REASONING}")
    
    parser.add_argument("--merge-codex-model", help="Codex model for merging")
    parser.add_argument("--merge-reasoning", choices=VALID_REASONING_LEVELS, help="Reasoning for merging")
    
    merge_group = parser.add_mutually_exclusive_group()
    merge_group.add_argument("--merge-prompt", help="Custom merge instruction")
    merge_group.add_argument("--merge-prompt-file", type=Path, help="Custom merge instruction file")
    
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--format", dest="output_format", choices=['txt', 'rtf'], default="txt", help="Output format")
    parser.add_argument("--require-git", action="store_true", help="Enable Codex git repo check")

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
        args.outdir = Path(f"./llm_ensemble_{ts}")

    return Config(
        models_csv=args.models,
        iterations=args.iterations,
        prompt_text=prompt_text,
        prompt_file=args.prompt_file,
        outdir=args.outdir,
        gemini_model=args.gemini_model,
        codex_model=args.codex_model,
        codex_reasoning=args.codex_reasoning,
        merge_codex_model=args.merge_codex_model,
        merge_reasoning=args.merge_reasoning,
        merge_prompt_text=args.merge_prompt,
        merge_prompt_file=args.merge_prompt_file,
        timeout=args.timeout,
        output_format=args.output_format,
        require_git=args.require_git
    )

def main():
    config = parse_args()
    app = EnsembleApp(config)
    app.validate_and_setup()
    results = app.execute_parallel()
    app.merge(results)

if __name__ == "__main__":
    main()
