#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
import shutil
import subprocess
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import time
import datetime

# --- Constants & Config ---
GEMINI_KNOWN_MODELS = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
]
CODEX_KNOWN_MODELS = [
    "gpt-5.2-codex",
    "gpt-5.2",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini"
]
CODEX_REASONING_LEVELS = ["low", "medium", "high", "xhigh"]

# Defaults
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_CODEX_MODEL = "gpt-5.2-codex"
DEFAULT_CODEX_REASONING = "high"

# --- Utils (Adapted from llm_ensemble.py) ---

def sanitize_label(text: str) -> str:
    """Replaces non-alphanumeric chars (except ._-) with _."""
    return re.sub(r'[^a-zA-Z0-9._-]', '_', text)

def extract_text_from_pdf(pdf_path: Path) -> str:
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return f"[Error extracting text from PDF: {pdf_path.name}]"
    else:
         return f"[Missing 'pdftotext' tool - could not read {pdf_path.name}]"

def extract_text_from_docx(docx_path: Path) -> str:
    try:
        with zipfile.ZipFile(docx_path) as zf:
            xml_content = zf.read('word/document.xml')
        root = ET.fromstring(xml_content)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        text_parts = []
        for p in root.findall('.//w:p', ns):
            p_text = []
            for t in p.findall('.//w:t', ns):
                if t.text:
                    p_text.append(t.text)
            text_parts.append("".join(p_text))
        return "\n".join(text_parts)
    except Exception:
        return f"[Error extracting text from DOCX: {docx_path.name}]"

def process_context_files(file_list: list[Path]) -> str:
    formatted_content = []
    for ctx_file in file_list:
        if not ctx_file.exists():
            continue
        ctx_text = ""
        suffix = ctx_file.suffix.lower()
        if suffix == '.pdf':
            ctx_text = extract_text_from_pdf(ctx_file)
        elif suffix == '.docx':
            ctx_text = extract_text_from_docx(ctx_file)
        else:
            try:
                raw_ctx = ctx_file.read_bytes()
                if b'\0' in raw_ctx:
                    ctx_text = "[Binary File Skipped]"
                else:
                    ctx_text = raw_ctx.decode('utf-8')
            except UnicodeDecodeError:
                ctx_text = raw_ctx.decode('latin-1', errors='replace')
        
        formatted_content.append(f"[Context File: {ctx_file.name}]\n<<<\n{ctx_text}\n>>>\n")
    return "".join(formatted_content)

def construct_meta_prompt(draft, context, target_model):
    """
    Constructs the meta-prompt.
    target_model string might look like: "gemini-3-pro-preview" or "gpt-5.2-codex model (Reasoning Level: high)"
    """
    
    context_section = ""
    context_intro = ""
    
    if context and context.strip():
        context_intro = "Before improving the prompt, analyze the attached documents, which constitute essential contextual material. These documents are intended to help you fully understand the underlying issue and should be taken into account when refining the prompt."
        context_section = f"\\n**Attached Background Context:**\\n{context}\\n"

    return f"""Please review and improve the following prompt so that it delivers optimal results when used with the {target_model}.
{context_intro}
{context_section}
Below is the draft prompt that requires correction and improvement:
{draft}

**Instructions:**
1. Improve clarity, structure, and persona.
2. Ensure all necessary context is included or referenced appropriately.
3. **Crucial:** Define a persona relevant to the *task* (e.g., "You are a Senior Python Dev" or "You are a Creative Writer"). Do **NOT** assume or state the model's identity (e.g., do NOT write "You are gpt-5.2" or "You are Gemini").
4. Output ONLY the optimized prompt."""

def construct_refinement_prompt(previous_output, feedback):
    return f"""Here is the prompt you just wrote:
<<<
{previous_output}
>>>>>

The user wants this change:
"{feedback}"

Rewrite the prompt to incorporate this feedback. Output ONLY the updated prompt."""

# --- Runners (Adapted from llm_ensemble.py) ---
class GeminiRunner:
    def __init__(self):
        self.executable = "gemini"

    def run(self, prompt_path: Path, output_path: Path, log_path: Path, model: str, timeout: int = 300, cwd: Path = None) -> bool:
        json_out = output_path.with_suffix(".json")
        cmd = [self.executable, "--output-format", "json", "--model", model]
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f_in, \
                 open(json_out, 'w', encoding='utf-8') as f_out, \
                 open(log_path, 'w', encoding='utf-8') as f_err:
                subprocess.run(cmd, stdin=f_in, stdout=f_out, stderr=f_err, timeout=timeout, env=env, check=True, cwd=cwd)
            
            with open(json_out, 'r', encoding='utf-8') as f:
                data = json.load(f)
                response = data.get("response", "") or ""
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response)
            return True
        except Exception as e:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Error: {str(e)}")
            return False

class CodexRunner:
    def __init__(self):
        self.executable = "codex"

    def run(self, prompt_path: Path, output_path: Path, log_path: Path, model: str, reasoning: str, timeout: int = 300, cwd: Path = None) -> bool:
        cmd = [self.executable, "exec", "--sandbox", "read-only", "--color", "never", 
               "--model", model, "--config", f'model_reasoning_effort="{reasoning}"',
               "--skip-git-repo-check", "-"]
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f_in, \
                 open(output_path, 'w', encoding='utf-8') as f_out, \
                 open(log_path, 'w', encoding='utf-8') as f_err:
                subprocess.run(cmd, stdin=f_in, stdout=f_out, stderr=f_err, timeout=timeout, check=True, cwd=cwd)
            return True
        except Exception as e:
             with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Error: {str(e)}")
             return False

# --- GUI Application ---
class PromptOptimizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PromptOptimizer")
        self.root.geometry("1400x1000")
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.tmp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "prompt_optimizer"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main Vertical Split: Top (Inputs) / Bottom (Outputs) / Logs
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        
        # --- Top Pane: Inputs ---
        input_frame = ttk.Frame(main_pane)
        main_pane.add(input_frame, weight=1)
        
        # Project Directory Section
        proj_frame = ttk.Frame(input_frame)
        proj_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        ttk.Label(proj_frame, text="Project Dir:").pack(side=tk.LEFT)
        self.project_dir_var = tk.StringVar(value=str(Path(".").resolve()))
        ttk.Entry(proj_frame, textvariable=self.project_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(proj_frame, text="Browse", command=self.browse_project_dir).pack(side=tk.LEFT)
        
        # Split Inputs: Left (Draft) / Right (Files)
        input_split = ttk.PanedWindow(input_frame, orient=tk.HORIZONTAL)
        input_split.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Draft Prompt
        draft_frame = ttk.LabelFrame(input_split, text="Draft Prompt", padding=5)
        input_split.add(draft_frame, weight=3)
        self.draft_text = scrolledtext.ScrolledText(draft_frame, height=10)
        self.draft_text.pack(fill=tk.BOTH, expand=True)
        
        # Context Files
        files_frame = ttk.LabelFrame(input_split, text="Context Files", padding=5)
        input_split.add(files_frame, weight=1)
        self.files_list = tk.Listbox(files_frame)
        self.files_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(files_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(btn_frame, text="Add", command=self.add_file).pack(fill=tk.X)
        ttk.Button(btn_frame, text="Clear", command=lambda: self.files_list.delete(0, tk.END)).pack(fill=tk.X)
        
        # --- Model Configuration Frame ---
        config_frame = ttk.LabelFrame(input_frame, text="Model Configuration", padding=5)
        config_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Gemini Config
        ttk.Label(config_frame, text="Gemini Model:").pack(side=tk.LEFT, padx=(5, 2))
        self.gemini_model_var = tk.StringVar(value=DEFAULT_GEMINI_MODEL)
        ttk.Combobox(config_frame, textvariable=self.gemini_model_var, values=GEMINI_KNOWN_MODELS).pack(side=tk.LEFT, padx=(0, 15))
        
        # Codex Config
        ttk.Label(config_frame, text="ChatGPT Model:").pack(side=tk.LEFT, padx=(5, 2))
        self.codex_model_var = tk.StringVar(value=DEFAULT_CODEX_MODEL)
        ttk.Combobox(config_frame, textvariable=self.codex_model_var, values=CODEX_KNOWN_MODELS).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(config_frame, text="Reasoning Level:").pack(side=tk.LEFT, padx=(5, 2))
        self.reasoning_var = tk.StringVar(value=DEFAULT_CODEX_REASONING)
        ttk.Combobox(config_frame, textvariable=self.reasoning_var, values=CODEX_REASONING_LEVELS, state="readonly").pack(side=tk.LEFT, padx=(0, 5))

        # Action Buttons (Run & Export)
        action_frame = ttk.Frame(input_frame)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="RUN OPTIMIZATION", command=self.run_optimization).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(action_frame, text="Export Prompts to JSON", command=self.export_prompts).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # --- Middle Pane: Outputs ---
        output_frame = ttk.Frame(main_pane)
        main_pane.add(output_frame, weight=3)
        
        output_split = ttk.PanedWindow(output_frame, orient=tk.HORIZONTAL)
        output_split.pack(fill=tk.BOTH, expand=True)
        
        # Left Output: Gemini
        self.gemini_ui = self.create_output_column(output_split, "Gemini Optimization", self.refine_gemini)
        
        # Right Output: Codex
        self.codex_ui = self.create_output_column(output_split, "ChatGPT (Codex) Optimization", self.refine_codex)
        
        # --- Bottom Pane: Logs ---
        log_frame = ttk.LabelFrame(main_pane, text="Logs", padding=5)
        main_pane.add(log_frame, weight=0) # Minimal height initially
        self.log_text = scrolledtext.ScrolledText(log_frame, height=5, state='disabled', bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def create_output_column(self, parent, title, refine_command):
        frame = ttk.LabelFrame(parent, text=title, padding=5)
        parent.add(frame, weight=1)
        
        # Output Text
        text_area = scrolledtext.ScrolledText(frame, height=15)
        text_area.pack(fill=tk.BOTH, expand=True)
        
        # Toolbar (Copy)
        tool_frame = ttk.Frame(frame)
        tool_frame.pack(fill=tk.X, pady=2)
        ttk.Button(tool_frame, text="Copy to Clipboard", command=lambda: self.copy_to_clipboard(text_area)).pack(side=tk.RIGHT)
        
        # Refinement (Expanded)
        ref_frame = ttk.LabelFrame(frame, text="Feedback / Refinement", padding=5)
        ref_frame.pack(fill=tk.X, pady=5, expand=False) # Keep fixed height but larger
        
        # Use ScrolledText for multiline input
        ref_entry = scrolledtext.ScrolledText(ref_frame, height=4) 
        ref_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Refine button on the right, centered vertically or top aligned
        btn_frame = ttk.Frame(ref_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ref_btn = ttk.Button(btn_frame, text="Refine", command=refine_command)
        ref_btn.pack(side=tk.TOP, pady=(5,0))
        
        return {"text": text_area, "entry": ref_entry, "btn": ref_btn}

    # --- Actions ---
    def browse_project_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.project_dir_var.set(d)

    def add_file(self):
        # Start in current project dir
        init_dir = self.project_dir_var.get()
        if not Path(init_dir).exists():
            init_dir = "."
        
        files = filedialog.askopenfilenames(initialdir=init_dir)
        for f in files:
            self.files_list.insert(tk.END, f)
            
    def copy_to_clipboard(self, widget):
        text = widget.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log("Copied to clipboard.")

    def export_prompts(self):
        """Exports the current prompts to a JSON file in the project directory."""
        project_dir_str = self.project_dir_var.get().strip()
        project_dir = Path(project_dir_str)
        
        if not project_dir.exists():
            self.log(f"Error: Project directory '{project_dir}' does not exist.")
            return

        prompts_dir = project_dir / "Prompts"
        try:
            prompts_dir.mkdir(exist_ok=True)
        except Exception as e:
            self.log(f"Error creating Prompts directory: {e}")
            return
            
        gemini_prompt = self.gemini_ui["text"].get("1.0", tk.END).strip()
        codex_prompt = self.codex_ui["text"].get("1.0", tk.END).strip()
        
        if not gemini_prompt and not codex_prompt:
             self.log("Warning: Both prompt outputs are empty. Nothing to export.")
             return
        
        export_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "gemini": {
                "model": self.gemini_model_var.get(),
                "prompt": gemini_prompt
            },
            "codex": {
                "model": self.codex_model_var.get(),
                "reasoning_level": self.reasoning_var.get(),
                "prompt": codex_prompt
            }
        }
        
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimized_prompts_{{ts}}.json"
        filepath = prompts_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4)
            self.log(f"Successfully exported prompts to: {filepath}")
        except Exception as e:
            self.log(f"Error writing export file: {e}")

    def log(self, message):
        self.root.after(0, self._log_safe, message)

    def _log_safe(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def get_context_text(self):
        files = [Path(self.files_list.get(idx)) for idx in range(self.files_list.size())]
        return process_context_files(files)

    # --- Threading & Execution ---
    def run_optimization(self):
        draft = self.draft_text.get("1.0", tk.END).strip()
        if not draft:
            messagebox.showerror("Error", "Please enter a draft prompt.")
            return

        context = self.get_context_text()
        
        # Get Model Configs
        gemini_model = self.gemini_model_var.get().strip() or DEFAULT_GEMINI_MODEL
        codex_model = self.codex_model_var.get().strip() or DEFAULT_CODEX_MODEL
        reasoning = self.reasoning_var.get().strip() or DEFAULT_CODEX_REASONING
        
        # Get Project Directory
        project_dir_str = self.project_dir_var.get().strip()
        project_dir = Path(project_dir_str)
        if not project_dir.exists():
             self.log(f"Warning: Project directory '{project_dir}' does not exist. Using current directory.")
             project_dir = Path(".")
        
        self.log("Starting optimization...")
        self.log(f"Project Dir: {project_dir.resolve()}")
        self.log(f"Gemini: {gemini_model}")
        self.log(f"ChatGPT: {codex_model} (Reasoning: {reasoning})")
        
        # Clear previous outputs
        self.gemini_ui["text"].delete("1.0", tk.END)
        self.codex_ui["text"].delete("1.0", tk.END)

        # Launch Threads
        t_gemini = threading.Thread(target=self.worker_optimization_gemini, args=(gemini_model, draft, context, project_dir))
        t_codex = threading.Thread(target=self.worker_optimization_codex, args=(codex_model, reasoning, draft, context, project_dir))
        
        t_gemini.start()
        t_codex.start()

    def refine_gemini(self):
        model = self.gemini_model_var.get().strip() or DEFAULT_GEMINI_MODEL
        project_dir = Path(self.project_dir_var.get().strip())
        self.run_refinement("gemini", model=model, reasoning=None, project_dir=project_dir)

    def refine_codex(self):
        model = self.codex_model_var.get().strip() or DEFAULT_CODEX_MODEL
        reasoning = self.reasoning_var.get().strip() or DEFAULT_CODEX_REASONING
        project_dir = Path(self.project_dir_var.get().strip())
        self.run_refinement("codex", model=model, reasoning=reasoning, project_dir=project_dir)

    def run_refinement(self, provider, model, reasoning, project_dir):
        ui = self.gemini_ui if provider == "gemini" else self.codex_ui
        feedback = ui["entry"].get("1.0", tk.END).strip()
        previous = ui["text"].get("1.0", tk.END).strip()
        
        if not feedback or not previous:
            return
            
        self.log(f"Refining {provider}...")
        ui["entry"].delete("1.0", tk.END)
        
        # We spawn a thread that uses the same execute_llm function but with refinement prompt
        t = threading.Thread(target=self.worker_refinement, args=(provider, model, reasoning, previous, feedback, project_dir))
        t.start()

    def worker_optimization_gemini(self, model, draft, context, project_dir):
        # Target string for prompt wrapper
        target_str = f"{model} model"
        prompt_content = construct_meta_prompt(draft, context, target_str)
        self.execute_llm("gemini", model, None, prompt_content, project_dir)

    def worker_optimization_codex(self, model, reasoning, draft, context, project_dir):
        # Target string for prompt wrapper
        target_str = f"{model} model (Reasoning Level: {reasoning})"
        prompt_content = construct_meta_prompt(draft, context, target_str)
        self.execute_llm("codex", model, reasoning, prompt_content, project_dir)

    def worker_refinement(self, provider, model, reasoning, previous, feedback, project_dir):
        prompt_content = construct_refinement_prompt(previous, feedback)
        self.execute_llm(provider, model, reasoning, prompt_content, project_dir)

    def execute_llm(self, provider, model, reasoning, prompt_content, project_dir):
        # Setup Paths
        ts = int(time.time() * 1000)
        base = self.tmp_dir / f"{provider}_{{ts}}"
        prompt_path = base.with_suffix(".prompt")
        out_path = base.with_suffix(".out")
        log_path = base.with_suffix(".log")
        
        try:
            prompt_path.write_text(prompt_content, encoding='utf-8')
        except Exception as e:
            self.log(f"{provider} Error writing prompt: {e}")
            return
        
        success = False
        if provider == "gemini":
            runner = GeminiRunner()
            success = runner.run(prompt_path, out_path, log_path, model=model, cwd=project_dir)
        else:
            runner = CodexRunner()
            success = runner.run(prompt_path, out_path, log_path, model=model, reasoning=reasoning, cwd=project_dir)
        
        if success and out_path.exists():
            result = out_path.read_text(encoding='utf-8')
            self.update_ui(provider, result)
            self.log(f"{provider} finished.")
        else:
            err = "Unknown Error"
            if out_path.exists():
                err = out_path.read_text(encoding='utf-8')
            elif log_path.exists():
                err = log_path.read_text(encoding='utf-8')
                
            self.log(f"{provider} Failed: {err}")
            self.update_ui(provider, f"[Error]\n{err}")

    def update_ui(self, provider, text):
        ui = self.gemini_ui if provider == "gemini" else self.codex_ui
        self.root.after(0, lambda: self._update_text(ui["text"], text))

    def _update_text(self, widget, text):
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)

if __name__ == "__main__":
    root = tk.Tk()
    app = PromptOptimizerApp(root)
    root.mainloop()