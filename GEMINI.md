# PromptOptimizer Project

## Project Overview

**PromptOptimizer** is a Python-based desktop GUI application that facilitates the creation and refinement of high-quality prompts for Large Language Models. It serves as an orchestration layer, allowing users to:

1.  Draft a prompt and attach context files (PDF, DOCX, TXT).
2.  Simultaneously optimize the prompt using two distinct AI models: **Google Gemini** and **OpenAI ChatGPT (via Codex)**.
3.  Iteratively refine the results through a chat-like interface.
4.  Export the finalized prompts to JSON.

The application leverages the power of the `gemini` and `codex` command-line tools to perform the actual LLM inference.

## Architecture & Key Files

*   **`prompt_optimizer.py`**: The single-file application containing all logic.
    *   **GUI Layer:** Built with `tkinter` and `ttk`. Implements a dual-pane layout for side-by-side model comparison.
    *   **Runner Layer:** `GeminiRunner` and `CodexRunner` classes wrap the respective CLI tools, handling process execution, input piping, and output capture.
    *   **File Handling:** Includes utility functions to extract text from PDFs (via `pdftotext`) and DOCX files (via `zipfile`/`xml`).
    *   **Orchestration:** Manages threading to ensure the GUI remains responsive while waiting for LLM responses.

*   **`Prompts/`**: A directory created at runtime within the user-selected project folder. It stores exported prompts in JSON format.

## Building and Running

### Prerequisites

*   **Python 3.8+**
*   **Tkinter:** Ensure it is installed (e.g., `sudo apt install python3-tk` on Debian/Ubuntu).
*   **CLI Tools:**
    *   `gemini` (Google Gemini CLI)
    *   `codex` (OpenAI/Codex CLI)
    *   `pdftotext` (Optional, for PDF support. Part of `poppler-utils`).

### Execution

The application is distributed as a standalone script.

```bash
# Make executable
chmod +x prompt_optimizer.py

# Run
./prompt_optimizer.py
```

## Development Conventions

*   **Single-File Structure:** All application logic, including GUI, business logic, and utilities, is contained within `prompt_optimizer.py` for ease of distribution.
*   **Threading Model:** Long-running LLM operations are offloaded to background threads (`threading.Thread`). The main thread is never blocked. UI updates from background threads must be scheduled using `root.after` to ensure thread safety.
*   **Inter-Process Communication:** The app communicates with the LLM CLIs via temporary files stored in `os.environ["TMPDIR"]` (or `/tmp`).
*   **Meta-Prompting:** The application uses a specific "meta-prompt" structure to instruct the optimizing LLMs. This structure injects the user's context and draft, while explicitly instructing the model *not* to hardcode its own identity into the result.
*   **Model Configuration:** Available models (e.g., `gemini-3-pro-preview`) are defined as constants at the top of the script (`GEMINI_KNOWN_MODELS`, `CODEX_KNOWN_MODELS`).

## Usage Flow

1.  **Project Setup:** User selects a project directory.
2.  **Input:** User provides a draft prompt and optionally adds context files.
3.  **Optimization:** User clicks "RUN OPTIMIZATION". The app constructs a meta-prompt and calls both CLIs.
4.  **Refinement:** User can refine individual outputs. The app sends the previous output + user feedback back to the specific model.
5.  **Export:** User clicks "Export Prompts to JSON" to save the results.
