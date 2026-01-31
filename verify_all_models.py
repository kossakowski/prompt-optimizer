#!/usr/bin/env python3
import json
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import llm_ensemble

# --- Setup a minimal Config for testing ---
def make_test_config(provider, model, reasoning=None):
    # Determine output dir
    outdir = Path("Verification_Output") / f"{provider}_{model}_{reasoning or 'default'}"
    
    # Clean up previous run if exists
    if outdir.exists():
        shutil.rmtree(outdir)
        
    return llm_ensemble.Config(
        models_csv=f"{provider}:{model}",
        iterations=1,
        prompt_text="Reply with 'OK'",
        prompt_file=None,
        context_files=[],
        outdir=outdir,
        gemini_model=model if provider == 'gemini' else "n/a",
        codex_model=model if provider == 'codex' else "n/a",
        codex_reasoning=reasoning if reasoning else "high",
        merge_codex_model=None,
        merge_provider="codex",
        merge_reasoning=None,
        merge_prompt_text=None,
        merge_prompt_file=None,
        merge_context_files=[],
        timeout=60, # Short timeout for quick check
        output_format="txt",
        require_git=False
    )

def run_test():
    # Load Config
    config_path = Path("config.json")
    if not config_path.exists():
        print("Error: config.json not found.")
        return

    with open(config_path, 'r') as f:
        conf = json.load(f)

    results = []

    print("=== STARTING COMPREHENSIVE MODEL VERIFICATION ===")
    print(f"Loaded {len(conf['gemini_known_models'])} Gemini models and {len(conf['codex_known_models'])} Codex models.")
    print("-" * 60)

    # 1. Test Gemini Models
    for model in conf['gemini_known_models']:
        print(f"Testing Gemini: {model}...", end=" ", flush=True)
        try:
            cfg = make_test_config('gemini', model)
            app = llm_ensemble.EnsembleApp(cfg)
            app.validate_and_setup()
            
            # Direct run of the runner to isolate the test
            log_file = cfg.outdir / "test.log"
            out_file = cfg.outdir / "test.txt"
            
            success = app.gemini_runner.run(app.prompt_canon, out_file, log_file, 60, model=model)
            
            if success:
                print("PASS")
                results.append({"Provider": "Gemini", "Model": model, "Reasoning": "N/A", "Status": "PASS"})
            else:
                print("FAIL")
                err = log_file.read_text() if log_file.exists() else "Unknown Error"
                results.append({"Provider": "Gemini", "Model": model, "Reasoning": "N/A", "Status": "FAIL", "Error": err[:50]})
                
        except Exception as e:
            print(f"CRASH ({e})")
            results.append({"Provider": "Gemini", "Model": model, "Reasoning": "N/A", "Status": "CRASH", "Error": str(e)[:50]})

    # 2. Test Codex Models
    for model in conf['codex_known_models']:
        for reasoning in conf['codex_reasoning_levels']:
            # Skip invalid combos if known (e.g., mini + low) 
            # Logic: If model contains 'mini' and reasoning is 'low', skip or expect fail?
            # User said "gpt-5.1-codex-mini only has medium and high". 
            # We will run it anyway to see if it fails (as requested "all possible").
            
            print(f"Testing Codex: {model} [{reasoning}]...", end=" ", flush=True)
            try:
                cfg = make_test_config('codex', model, reasoning)
                app = llm_ensemble.EnsembleApp(cfg)
                app.validate_and_setup()
                
                log_file = cfg.outdir / "test.log"
                out_file = cfg.outdir / "test.txt"
                
                success = app.codex_runner.run(app.prompt_canon, out_file, log_file, 60, model=model, reasoning=reasoning)
                
                if success:
                    print("PASS")
                    results.append({"Provider": "Codex", "Model": model, "Reasoning": reasoning, "Status": "PASS"})
                else:
                    print("FAIL")
                    err = ""
                    # Read the output file because updated run_codex writes error there too
                    if out_file.exists():
                        content = out_file.read_text()
                        if "[codex] ERROR" in content:
                            err = content.split("ERROR:")[1].strip()
                    results.append({"Provider": "Codex", "Model": model, "Reasoning": reasoning, "Status": "FAIL", "Error": err[:50]})

            except Exception as e:
                print(f"CRASH ({e})")
                results.append({"Provider": "Codex", "Model": model, "Reasoning": reasoning, "Status": "CRASH", "Error": str(e)[:50]})

    # --- Report ---
    print("\n" + "="*80)
    print(f"{ 'PROVIDER':<10} | {'MODEL':<25} | {'REASONING':<10} | {'STATUS':<6} | {'ERROR (If Any)'}")
    print("-" * 80)
    for r in results:
        err = r.get("Error", "")
        print(f"{r['Provider']:<10} | {r['Model']:<25} | {r['Reasoning']:<10} | {r['Status']:<6} | {err}")
    print("="*80)

if __name__ == "__main__":
    run_test()
