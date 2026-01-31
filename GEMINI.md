# Project Overview

**LLM Ensemble** is a tool designed to orchestrate multiple AI models (Gemini and Codex) to solve complex problems. By running models multiple times or in parallel and then synthesizing their outputs, it produces a high-quality, "ensembled" final answer that often outperforms single-shot responses.

The tool provides both a **Command Line Interface (CLI)** and a modern, tabbed **Graphical User Interface (GUI)**.

## Key Features
*   **Project-Centric Workflow:** Define a project directory (`-d`). All context files, prompts, and outputs are resolved relative to this path, and models run within this working directory.
*   **Multi-Model Support:** Orchestrates Google's Gemini and OpenAI's Codex (simulated via CLI tools).
*   **Parallel Execution:** Runs model iterations concurrently using thread pools for improved performance.
*   **Rich Context Support:** Natively extracts text from **PDF**, **DOCX**, and text files to provide robust context for the models.
*   **Human-in-the-Loop:** Pause execution after initial drafts to review generated HTML reports and refine the final merge instruction before the synthesis step.
*   **Automatic Merging:** Aggregates all candidate answers and uses a "reasoning" model (Gemini or Codex) to generate a final, consolidated response.
*   **Output Formats:** Supports plain **TXT**, **RTF** (Rich Text Format), and **DOCX** (Word Document).
*   **Reporting:** Generates `pre_report.html` (visualization of candidates) and `post_report.html` (final result and logs).
*   **Configurable:** Model lists and defaults are loaded from an external `config.json` file.

# Key Files

*   **`llm_ensemble.py`**: The core Python CLI application and logic library.
*   **`llm_ensemble_gui.py`**: A Tkinter-based GUI with a tabbed interface and Human-in-the-Loop controls.
*   **`config.json`**: JSON configuration file defining available models and defaults.
*   **`test_llm_ensemble.py`**: A comprehensive `unittest` suite mocking external CLI calls and file operations.
*   **`docs/`**: Directory containing the user guide (`index.html`) and technical reference (`reference.html`).

# Building and Running

The project is a standalone Python script with no external package dependencies beyond the standard library.
**Requirements:**
*   Python 3.8+
*   `gemini` and `codex` executables in system `PATH`.
*   `poppler-utils` (or `pdftotext`) for PDF support.

## Running the GUI
For a visual interface, simply run:
```bash
python3 llm_ensemble_gui.py
```
This launches a window where you can:
*   **Project Dir:** Select a base directory for your work.
*   **Execution Tab:** Enter prompts, attach context files (TXT/PDF/DOCX), and configure custom merge instructions.
*   **Configuration Tab:** Select specific models (Gemini/Codex), set iterations, timeouts, and output formats (TXT/RTF/DOCX).
*   **Human-in-the-Loop:** Enable the "Pause before Merge" checkbox to review intermediate results (HTML report) before finalizing.

## Running the CLI
```bash
python3 llm_ensemble.py -d /my/project -m gemini,codex -n 2 -p "Your prompt here"
```

### Common Flags
*   `-d, --project-dir`: Base directory for the project. Context files and outputs are relative to this.
*   `-m, --models`: Comma-separated list of providers (e.g., `gemini`, `codex:gpt-4`).
*   `-n, --iterations`: Number of times to run each model.
*   `-p, --prompt`: The input prompt text.
*   `-f, --prompt-file`: Read prompt from a file (relative to project dir).
*   `-c, --context`: Attach additional files as context (relative to project dir).
*   `-mc, --merge-context`: Attach context files specifically for the merge step.
*   `-o, --outdir`: Directory to save artifacts. Defaults to `<project_dir>/Outputs/llm_ensemble_<timestamp>`.
    *   **Note:** The `Outputs/` directory is excluded from the repository to keep it clean.
*   `--no-pre-report` / `--no-post-report`: Disable HTML report generation.

## Output Structure
Every run creates a timestamped folder inside `<project_dir>/Outputs/` containing:
*   **`Runs/`**: Subdirectory containing individual model outputs (`.txt`) and error logs (`.log`).
*   **`final.txt`**: The final synthesized answer (also saved as `.rtf` or `.docx` if requested).
*   **`pre_report.html`**: Visual report of all candidate answers and prompts (before merge).
*   **`post_report.html`**: Visual report of the final result and execution summary.
*   **`prompt.txt`**: The complete prompt sent to the models (including extracted context).
*   **`merge_prompt.txt`**: The instruction used for the final merge step (including merge context).

## Running Tests
To verify the logic (argument parsing, file handling, merge prompt construction) without calling external APIs:
```bash
python3 test_llm_ensemble.py
```