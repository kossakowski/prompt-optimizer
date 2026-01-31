#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
from pathlib import Path
import datetime
import llm_ensemble

class EnsembleGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LLM Ensemble Orchestrator")
        self.root.geometry("800x900")
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.create_widgets()
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Config Section ---
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.pack(fill=tk.X, pady=5)
        
        # Models
        ttk.Label(config_frame, text="Models (CSV):").grid(row=0, column=0, sticky=tk.W)
        self.models_var = tk.StringVar(value="gemini,codex")
        ttk.Entry(config_frame, textvariable=self.models_var, width=50).grid(row=0, column=1, columnspan=3, sticky=tk.W, pady=2)
        
        # Iterations & Timeout
        ttk.Label(config_frame, text="Iterations:").grid(row=1, column=0, sticky=tk.W)
        self.iter_var = tk.IntVar(value=1)
        ttk.Spinbox(config_frame, from_=1, to=100, textvariable=self.iter_var, width=5).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(config_frame, text="Timeout (s):").grid(row=1, column=2, sticky=tk.W)
        self.timeout_var = tk.IntVar(value=300)
        ttk.Entry(config_frame, textvariable=self.timeout_var, width=10).grid(row=1, column=3, sticky=tk.W, pady=2)
        
        # Reasoning & Format
        ttk.Label(config_frame, text="Codex Reasoning:").grid(row=2, column=0, sticky=tk.W)
        self.reasoning_var = tk.StringVar(value="high")
        ttk.Combobox(config_frame, textvariable=self.reasoning_var, values=list(llm_ensemble.VALID_REASONING_LEVELS), state="readonly").grid(row=2, column=1, sticky=tk.W, pady=2)

        ttk.Label(config_frame, text="Output Format:").grid(row=2, column=2, sticky=tk.W)
        self.format_var = tk.StringVar(value="txt")
        ttk.Combobox(config_frame, textvariable=self.format_var, values=["txt", "rtf"], state="readonly", width=8).grid(row=2, column=3, sticky=tk.W, pady=2)
        
        # Merge Config
        ttk.Label(config_frame, text="Merge Reasoning:").grid(row=3, column=0, sticky=tk.W)
        self.merge_reasoning_var = tk.StringVar(value="(Default)")
        merge_levels = ["(Default)"] + list(llm_ensemble.VALID_REASONING_LEVELS)
        ttk.Combobox(config_frame, textvariable=self.merge_reasoning_var, values=merge_levels, state="readonly").grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # --- Prompt Section ---
        prompt_frame = ttk.LabelFrame(main_frame, text="Prompt", padding="10")
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8)
        self.prompt_text.pack(fill=tk.BOTH, expand=True)
        
        # --- Context Files Section ---
        ctx_frame = ttk.LabelFrame(main_frame, text="Context Files", padding="10")
        ctx_frame.pack(fill=tk.X, pady=5)
        
        self.ctx_listbox = tk.Listbox(ctx_frame, height=4)
        self.ctx_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        btn_frame = ttk.Frame(ctx_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(btn_frame, text="Add File", command=self.add_context_file).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Remove", command=self.remove_context_file).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Clear", command=self.clear_context_files).pack(fill=tk.X, pady=2)

        # --- Merge Prompt Section ---
        merge_frame = ttk.LabelFrame(main_frame, text="Merge Instructions (Optional)", padding="10")
        merge_frame.pack(fill=tk.X, pady=5)
        
        self.merge_prompt_text = scrolledtext.ScrolledText(merge_frame, height=4)
        self.merge_prompt_text.pack(fill=tk.BOTH, expand=True)
        
        # --- Action Section ---
        action_frame = ttk.Frame(main_frame, padding="10")
        action_frame.pack(fill=tk.X)
        
        self.run_btn = ttk.Button(action_frame, text="RUN ENSEMBLE", command=self.start_thread)
        self.run_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        ttk.Button(action_frame, text="Quit", command=self.root.quit).pack(side=tk.RIGHT, padx=5)
        
        # --- Logs ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state='disabled', bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        self.root.after(0, self._log_safe, message)

    def _log_safe(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def add_context_file(self):
        filenames = filedialog.askopenfilenames()
        for f in filenames:
            self.ctx_listbox.insert(tk.END, f)

    def remove_context_file(self):
        sel = self.ctx_listbox.curselection()
        if sel:
            self.ctx_listbox.delete(sel)

    def clear_context_files(self):
        self.ctx_listbox.delete(0, tk.END)

    def start_thread(self):
        # Disable button
        self.run_btn.config(state='disabled')
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        t = threading.Thread(target=self.run_process)
        t.start()

    def run_process(self):
        try:
            # Gather Data
            models = self.models_var.get()
            iterations = self.iter_var.get()
            timeout = self.timeout_var.get()
            reasoning = self.reasoning_var.get()
            out_format = self.format_var.get()
            
            merge_reasoning_val = self.merge_reasoning_var.get()
            if merge_reasoning_val == "(Default)":
                merge_reasoning_val = None
            
            prompt = self.prompt_text.get("1.0", tk.END).strip()
            merge_prompt = self.merge_prompt_text.get("1.0", tk.END).strip()
            
            ctx_files = [Path(self.ctx_listbox.get(idx)) for idx in range(self.ctx_listbox.size())]
            
            if not prompt:
                self.log("Error: Prompt cannot be empty.")
                self.root.after(0, lambda: self.run_btn.config(state='normal'))
                return

            # Build Config
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            outdir = Path(f"./llm_ensemble_{ts}")
            
            config = llm_ensemble.Config(
                models_csv=models,
                iterations=iterations,
                prompt_text=prompt,
                prompt_file=None,
                context_files=ctx_files,
                outdir=outdir,
                gemini_model=llm_ensemble.DEFAULT_GEMINI_MODEL,
                codex_model=llm_ensemble.DEFAULT_CODEX_MODEL,
                codex_reasoning=reasoning,
                merge_codex_model=None,
                merge_reasoning=merge_reasoning_val,
                merge_prompt_text=merge_prompt if merge_prompt else None,
                merge_prompt_file=None,
                timeout=timeout,
                output_format=out_format,
                require_git=False
            )
            
            # Run App
            app = llm_ensemble.EnsembleApp(config, logger=self.log)
            self.log(f"Starting run in {outdir}...")
            
            app.validate_and_setup()
            results = app.execute_parallel()
            app.merge(results)
            
            self.log("DONE! Check the output directory.")
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state='normal'))

if __name__ == "__main__":
    root = tk.Tk()
    gui = EnsembleGUI(root)
    root.mainloop()
