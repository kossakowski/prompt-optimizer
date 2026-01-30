# Architecture Design: LLM Ensemble Python CLI

## Class Structure

1.  **`Config` (Dataclass)**
    *   Stores all runtime configuration (parsed arguments).
    *   Centralizes default values (e.g., default models, timeout).

2.  **`LLMRunner` (Abstract Base Class)**
    *   Defines the interface for executing a model run.
    *   `run(self, prompt_path: Path, output_path: Path, log_path: Path, timeout: int) -> bool`
    *   `check_dependencies(self) -> bool`

3.  **`GeminiRunner` (Inherits `LLMRunner`)**
    *   Implements `run` using `subprocess.call("gemini", ...)`
    *   Handles JSON output parsing using Python's `json` module.

4.  **`CodexRunner` (Inherits `LLMRunner`)**
    *   Implements `run` using `subprocess.call("codex", ...)`
    *   Handles specific flags: `--sandbox`, `--skip-git-repo-check`, `--config`.

5.  **`EnsembleManager`**
    *   Main orchestration logic.
    *   `__init__(self, config)`
    *   `prepare_workspace()`: Creates directories, processes input prompt (encoding/file checks).
    *   `execute_parallel()`: Uses `concurrent.futures.ThreadPoolExecutor` to run model iterations concurrently.
    *   `merge_results()`: Aggregates outputs, builds the merge prompt, and runs the final consolidation step.
    *   `finalize()`: Handles RTF conversion and user feedback.

## Key Logic Changes

### 1. Parallel Execution
The Bash script runs sequentially. The Python version will generate a list of "tasks" (e.g., `(runner_instance, iteration_index)`) and submit them to a `ThreadPoolExecutor`.
*   **Benefit:** Significantly reduced total wait time.
*   **Safety:** Each run writes to a unique file (`<model>_run_<n>.txt`), avoiding race conditions on file writes.

### 2. Argument Parsing strategy
We will use `argparse` to replicate the Bash flags exactly.
*   **Validation:** Custom validators for reasoning levels (minimal-xhigh) and positive integers.
*   **Positional Args:** Handle the optional positional prompt argument to match Bash behavior.

### 3. File & Encoding Handling
Instead of `file` and `iconv`:
*   Use `pathlib` for file existence/checks.
*   Read files using a standard `utf-8` try-block.
*   If `UnicodeDecodeError`, try `latin-1` or raise an error similar to the script's binary check (detecting null bytes).
*   Ensure the "canonical prompt" is always written as UTF-8 for the tools to consume.

### 4. Dependency Management
*   `shutil.which()` will be used to check for `gemini` and `codex` executables at startup.
