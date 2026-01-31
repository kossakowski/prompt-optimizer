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
        self.root.geometry("900x800")
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Main Layout
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tab_execution = ttk.Frame(self.notebook, padding="10")
        self.tab_config = ttk.Frame(self.notebook, padding="10")
        
        self.notebook.add(self.tab_execution, text="Execution & Prompts")
        self.notebook.add(self.tab_config, text="Models & Configuration")
        
        self.create_execution_tab()
        self.create_config_tab()
        self.create_log_section()
        
    def create_execution_tab(self):
        frame = self.tab_execution
        
        # --- Prompt Section ---
        prompt_frame = ttk.LabelFrame(frame, text="Main Prompt", padding="10")
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8)
        self.prompt_text.pack(fill=tk.BOTH, expand=True)
        
        # --- Context Files ---
        ctx_frame = ttk.LabelFrame(frame, text="Context Files (Iteration Phase)", padding="10")
        ctx_frame.pack(fill=tk.X, pady=5)
        self.ctx_listbox = tk.Listbox(ctx_frame, height=4)
        self.ctx_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        btn_frame = ttk.Frame(ctx_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(btn_frame, text="Add", command=lambda: self.add_file(self.ctx_listbox)).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Clear", command=lambda: self.clear_list(self.ctx_listbox)).pack(fill=tk.X, pady=2)

        # --- Merge Section ---
        merge_frame = ttk.LabelFrame(frame, text="Merge Phase (Optional)", padding="10")
        merge_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Merge Prompt
        ttk.Label(merge_frame, text="Custom Merge Instructions:").pack(anchor=tk.W)
        self.merge_prompt_text = scrolledtext.ScrolledText(merge_frame, height=4)
        self.merge_prompt_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Merge Context Files
        ttk.Label(merge_frame, text="Merge Context Files:").pack(anchor=tk.W)
        self.merge_ctx_listbox = tk.Listbox(merge_frame, height=3)
        self.merge_ctx_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        m_btn_frame = ttk.Frame(merge_frame)
        m_btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(m_btn_frame, text="Add", command=lambda: self.add_file(self.merge_ctx_listbox)).pack(fill=tk.X, pady=2)
        ttk.Button(m_btn_frame, text="Clear", command=lambda: self.clear_list(self.merge_ctx_listbox)).pack(fill=tk.X, pady=2)

        # Run Button
        self.run_btn = ttk.Button(frame, text="RUN ENSEMBLE", command=self.start_thread)
        self.run_btn.pack(fill=tk.X, pady=10)

    def create_config_tab(self):
        frame = self.tab_config
        
        # --- Model Selection ---
        model_frame = ttk.LabelFrame(frame, text="Model Selection", padding="10")
        model_frame.pack(fill=tk.X, pady=5)
        
        # Gemini
        self.use_gemini = tk.BooleanVar(value=True)
        ttk.Checkbutton(model_frame, text="Use Gemini", variable=self.use_gemini).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(model_frame, text="Model:").grid(row=0, column=1, sticky=tk.W)
        self.gemini_model_var = tk.StringVar(value=llm_ensemble.DEFAULT_GEMINI_MODEL)
        ttk.Combobox(model_frame, textvariable=self.gemini_model_var, values=llm_ensemble.GEMINI_KNOWN_MODELS).grid(row=0, column=2, sticky=tk.EW, padx=5)
        
        # Codex
        self.use_codex = tk.BooleanVar(value=True)
        ttk.Checkbutton(model_frame, text="Use Codex", variable=self.use_codex).grid(row=1, column=0, sticky=tk.W)
        ttk.Label(model_frame, text="Model:").grid(row=1, column=1, sticky=tk.W)
        self.codex_model_var = tk.StringVar(value=llm_ensemble.DEFAULT_CODEX_MODEL)
        codex_cb = ttk.Combobox(config_frame, textvariable=self.codex_model_var, values=llm_ensemble.CODEX_KNOWN_MODELS)
        codex_cb.grid(row=1, column=2, sticky=tk.EW, padx=5)
        codex_cb.bind("<<ComboboxSelected>>", self.update_reasoning_options)
        
        ttk.Label(model_frame, text="Reasoning:").grid(row=1, column=3, sticky=tk.W)
        self.reasoning_var = tk.StringVar(value=llm_ensemble.DEFAULT_CODEX_REASONING)
        self.reasoning_cb = ttk.Combobox(model_frame, textvariable=self.reasoning_var, values=sorted(list(llm_ensemble.VALID_REASONING_LEVELS)), state="readonly")
        self.reasoning_cb.grid(row=1, column=4, sticky=tk.EW, padx=5)

        model_frame.columnconfigure(2, weight=1)

        # --- Iteration Settings ---
        iter_frame = ttk.LabelFrame(frame, text="Execution Settings", padding="10")
        iter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(iter_frame, text="Iterations per Model:").grid(row=0, column=0, sticky=tk.W)
        self.iter_var = tk.IntVar(value=1)
        ttk.Spinbox(iter_frame, from_=1, to=100, textvariable=self.iter_var, width=5).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(iter_frame, text="Timeout (seconds):").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.timeout_var = tk.IntVar(value=300)
        ttk.Entry(iter_frame, textvariable=self.timeout_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # --- Merge & Output ---
        merge_conf_frame = ttk.LabelFrame(frame, text="Merge & Output Configuration", padding="10")
        merge_conf_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(merge_conf_frame, text="Merge Model:").grid(row=0, column=0, sticky=tk.W)
        self.merge_model_var = tk.StringVar(value="(Default: Codex)")
        
        # Combine lists for merge dropdown
        all_merge_models = ["(Default: Codex)"] + llm_ensemble.CODEX_KNOWN_MODELS + llm_ensemble.GEMINI_KNOWN_MODELS
        ttk.Combobox(merge_conf_frame, textvariable=self.merge_model_var, values=all_merge_models).grid(row=0, column=1, sticky=tk.EW, padx=5)
        
        ttk.Label(merge_conf_frame, text="Merge Reasoning:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.merge_reasoning_var = tk.StringVar(value="(Default)")
        merge_levels = ["(Default)"] + sorted(list(llm_ensemble.VALID_REASONING_LEVELS))
        ttk.Combobox(merge_conf_frame, textvariable=self.merge_reasoning_var, values=merge_levels, state="readonly").grid(row=0, column=3, sticky=tk.EW, padx=5)
        
        ttk.Label(merge_conf_frame, text="Output Format:").grid(row=1, column=0, sticky=tk.W, pady=(10,0))
        self.format_var = tk.StringVar(value="txt")
        ttk.Combobox(merge_conf_frame, textvariable=self.format_var, values=["txt", "rtf", "docx"], state="readonly", width=10).grid(row=1, column=1, sticky=tk.W, padx=5, pady=(10,0))

        merge_conf_frame.columnconfigure(1, weight=1)

    def create_log_section(self):
        log_frame = ttk.LabelFrame(self.root, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state='disabled', bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # --- Helpers ---
    def log(self, message):
        self.root.after(0, self._log_safe, message)

    def _log_safe(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def add_file(self, listbox):
        filenames = filedialog.askopenfilenames()
        for f in filenames:
            listbox.insert(tk.END, f)

    def clear_list(self, listbox):
        listbox.delete(0, tk.END)

    def update_reasoning_options(self, event=None):
        selected_model = self.codex_model_var.get()
        all_levels = sorted(list(llm_ensemble.VALID_REASONING_LEVELS))
        
        if selected_model == "gpt-5.1-codex-mini":
            # Remove 'xhigh' if present
            filtered_levels = [x for x in all_levels if x != "xhigh"]
            self.reasoning_cb['values'] = filtered_levels
            
            # If current selection is invalid, reset to default (medium or high)
            if self.reasoning_var.get() == "xhigh":
                self.reasoning_var.set("high")
        else:
            # Restore all levels
            self.reasoning_cb['values'] = all_levels

    def start_thread(self):
        # Disable button
        self.run_btn.config(state='disabled')
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # Switch to logs tab logic (conceptually) or just ensure logs are visible
        # Since logs are at bottom, no switch needed.
        
        t = threading.Thread(target=self.run_process)
        t.start()

    def run_process(self):
        try:
            # Construct Models CSV based on checkboxes
            models_list = []
            if self.use_gemini.get():
                model_name = self.gemini_model_var.get().strip()
                if model_name:
                    models_list.append(f"gemini:{model_name}")
                else:
                    models_list.append("gemini") # Uses default
            
            if self.use_codex.get():
                model_name = self.codex_model_var.get().strip()
                if model_name:
                    models_list.append(f"codex:{model_name}")
                else:
                    models_list.append("codex")

            if not models_list:
                self.log("Error: No models selected! Please enable Gemini or Codex in the Configuration tab.")
                return

            models_csv = ",".join(models_list)
            
            # Gather other config
            iterations = self.iter_var.get()
            timeout = self.timeout_var.get()
            reasoning = self.reasoning_var.get()
            out_format = self.format_var.get()
            
            merge_model_val = self.merge_model_var.get()
            if merge_model_val.startswith("(Default"):
                merge_model_val = None
            
            # Determine Merge Provider
            merge_provider = "codex"
            if merge_model_val and "gemini" in merge_model_val.lower():
                merge_provider = "gemini"
                
            merge_reasoning_val = self.merge_reasoning_var.get()
            if merge_reasoning_val.startswith("(Default"):
                merge_reasoning_val = None
            
            prompt = self.prompt_text.get("1.0", tk.END).strip()
            merge_prompt = self.merge_prompt_text.get("1.0", tk.END).strip()
            
            ctx_files = [Path(self.ctx_listbox.get(idx)) for idx in range(self.ctx_listbox.size())]
            merge_ctx_files = [Path(self.merge_ctx_listbox.get(idx)) for idx in range(self.merge_ctx_listbox.size())]
            
            if not prompt:
                self.log("Error: Prompt cannot be empty.")
                self.root.after(0, lambda: self.run_btn.config(state='normal'))
                return

            # Build Config
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            outdir = Path("Outputs") / f"llm_ensemble_{ts}"
            
            config = llm_ensemble.Config(
                models_csv=models_csv,
                iterations=iterations,
                prompt_text=prompt,
                prompt_file=None,
                context_files=ctx_files,
                outdir=outdir,
                gemini_model=llm_ensemble.DEFAULT_GEMINI_MODEL,
                codex_model=llm_ensemble.DEFAULT_CODEX_MODEL,
                codex_reasoning=reasoning,
                merge_codex_model=merge_model_val,
                merge_provider=merge_provider, # Added this
                merge_reasoning=merge_reasoning_val,
                merge_prompt_text=merge_prompt if merge_prompt else None,
                merge_prompt_file=None,
                merge_context_files=merge_ctx_files,
                timeout=timeout,
                output_format=out_format,
                require_git=False
            )
            
            # Run App
            app = llm_ensemble.EnsembleApp(config, logger=self.log)
            self.log(f"Starting run in {outdir}...")
            self.log(f"Active Models: {models_csv}")
            
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