# Project Overview

**LLM Ensemble** is a tool designed to orchestrate multiple AI models (Gemini and Codex) to solve complex problems. By running models multiple times or in parallel and then synthesizing their outputs, it produces a high-quality, "ensembled" final answer that often outperforms single-shot responses.

The tool provides both a Command Line Interface (CLI) and a Graphical User Interface (GUI).

## Key Features
*   **Multi-Model Support:** Orchestrates Google's Gemini and OpenAI's Codex (simulated via CLI tools).
*   **Parallel Execution:** Runs model iterations concurrently using thread pools for improved performance.
*   **Rich Context Support:** Natively extracts text from **PDF**, **DOCX**, and text files to provide robust context for the models.
*   **Automatic Merging:** Aggregates all candidate answers and uses a "reasoning" model to generate a final, consolidated response.
*   **Flexible Inputs:** Accepts prompts via arguments, files, or stdin.
*   **Output Formats:** Supports plain text and RTF (Rich Text Format) for document workflows.

# Key Files

*   **`llm_ensemble.py`**: The core Python CLI application and logic library.
*   **`llm_ensemble_gui.py`**: A Tkinter-based Graphical User Interface for easy interaction.
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
This launches a window where you can configure models, attach context files (drag & drop selection), set reasoning levels, and view real-time logs.

## Running the CLI
```bash
python3 llm_ensemble.py -m gemini,codex -n 2 -p "Your prompt here"
```

### Common Flags
*   `-m, --models`: Comma-separated list of providers (e.g., `gemini`, `codex:gpt-4`).
*   `-n, --iterations`: Number of times to run each model.
*   `-p, --prompt`: The input prompt text.
*   `-f, --prompt-file`: Read prompt from a file.
*   `-c, --context`: Attach additional files as context (repeatable). Supports **.txt**, **.pdf**, **.docx**.
*   `-o, --outdir`: Directory to save artifacts. Defaults to `Outputs/llm_ensemble_<timestamp>`.

## Output Structure
Every run creates a timestamped folder containing:
*   **`Runs/`**: Subdirectory containing individual model outputs and logs.
*   **`final.txt`**: The final synthesized answer.
*   **`prompt.txt`**: The complete prompt sent to the models.
*   **`merge_prompt.txt`**: The instruction used for the final merge step.

## Running Tests
To verify the logic (argument parsing, file handling, merge prompt construction) without calling external APIs:
```bash
python3 test_llm_ensemble.py
```

# Development Conventions

*   **Language:** Python 3 (Native Standard Library usage preferred).
*   **Concurrency:** `concurrent.futures.ThreadPoolExecutor` is used for model runs.
*   **Type Hinting:** Codebase uses standard Python typing.
*   **Observability:** Core logic uses a logger callback system to support both CLI (stderr) and GUI (text widget) outputs.
*   **Testing:** `unittest` with `unittest.mock` is used to simulate file I/O, subprocess execution, and zip/pdf extraction.