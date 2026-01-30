# Project Overview

**LLM Ensemble** is a CLI tool designed to orchestrate multiple AI models (specifically Gemini and Codex) to solve complex problems. By running models multiple times or in parallel and then synthesizing their outputs, it produces a high-quality, "ensembled" final answer that often outperforms single-shot responses.

The project recently underwent a refactoring from a legacy Bash script (`llm_ensemble.sh`) to a robust, concurrent Python application (`llm_ensemble.py`).

## Key Features
*   **Multi-Model Support:** Orchestrates Google's Gemini and OpenAI's Codex (simulated via CLI tools).
*   **Parallel Execution:** Runs model iterations concurrently using thread pools for improved performance.
*   **Automatic Merging:** Aggregates all candidate answers and uses a "reasoning" model to generate a final, consolidated response.
*   **Flexible Inputs:** Accepts prompts via command-line arguments, files (with encoding detection), or stdin.
*   **Output Formats:** Supports plain text and RTF (Rich Text Format) for document workflows.

# Key Files

*   **`llm_ensemble.py`**: The main Python CLI application. This is the recommended entry point.
*   **`test_llm_ensemble.py`**: A comprehensive `unittest` suite for the Python application, mocking external CLI calls.
*   **`llm_ensemble.sh`**: The legacy Bash script implementation (kept for reference/backward compatibility).
*   **`GUIDE.html`**: A detailed HTML user guide explaining usage scenarios and flags.
*   **`functionality_matrix.md`**: Documentation mapping legacy Bash flags to the new Python arguments.
*   **`architecture_design.md`**: High-level design document for the Python refactor.

# Building and Running

The project is a standalone Python script with no external package dependencies beyond the standard library, though it relies on `gemini` and `codex` executables being present in the system `PATH`.

## Running the Tool
```bash
python3 llm_ensemble.py -m gemini,codex -n 2 -p "Your prompt here"
```

### Common Flags
*   `-m, --models`: Comma-separated list of providers (e.g., `gemini`, `codex:gpt-4`).
*   `-n, --iterations`: Number of times to run each model.
*   `-p, --prompt`: The input prompt text.
*   `-f, --prompt-file`: Read prompt from a file.
*   `-o, --outdir`: Directory to save artifacts (defaults to timestamped folder).

## Running Tests
To verify the logic (argument parsing, file handling, merge prompt construction) without calling external APIs:
```bash
python3 test_llm_ensemble.py
```

# Development Conventions

*   **Language:** Python 3 (Native Standard Library usage preferred).
*   **Concurrency:** `concurrent.futures.ThreadPoolExecutor` is used for model runs.
*   **Type Hinting:** Codebase uses standard Python typing.
*   **External Calls:** `subprocess` is used to invoke `gemini` and `codex` CLIs.
*   **Testing:** `unittest` with `unittest.mock` is used to simulate file I/O and subprocess execution.
