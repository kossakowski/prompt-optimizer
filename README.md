# PromptOptimizer

**PromptOptimizer** is a powerful desktop GUI application designed to help you craft high-quality prompts for Large Language Models (LLMs). It orchestrates two leading AI models—**Google Gemini** and **OpenAI ChatGPT (via Codex CLI)**—in parallel, allowing you to compare, refine, and perfect your prompts in a single interface.

## 🚀 Key Features

*   **Dual-Pane Optimization:** View optimized prompts from Gemini and ChatGPT side-by-side.
*   **Context-Aware:** Attach PDF, DOCX, or TXT files to give the models full background context before they optimize your prompt.
*   **Iterative Refinement:** Tweak the output of each model independently using a chat-like feedback loop (e.g., "Make it shorter", "Add more examples").
*   **Model Selection:** Choose specific model versions (e.g., `gemini-3-pro-preview`, `gpt-5.2`) and reasoning levels (for Codex).
*   **Project Management:** Set a project directory to easily manage input files and exports.
*   **Export to JSON:** Save your perfected prompts and configuration to a JSON file for future use.

## 🛠️ Prerequisites

Before running the application, ensure you have the following installed:

1.  **Python 3.8+**
2.  **Tkinter** (Usually included with Python, but requires `python3-tk` on some Linux distros).
3.  **CLI Tools:**
    *   `gemini` (Google Gemini CLI)
    *   `codex` (OpenAI/Codex CLI)
    *   `pdftotext` (Optional: Required only if you want to extract text from PDF files. Part of the `poppler-utils` package).

## 📦 Installation

1.  **Download the script:**
    Save the `prompt_optimizer.py` file to your desired directory.

2.  **Make it executable (Linux/macOS):**
    ```bash
    chmod +x prompt_optimizer.py
    ```

## 🖥️ Usage

1.  **Launch the Application:**
    ```bash
    ./prompt_optimizer.py
    ```

2.  **Set Project Directory:**
    *   Use the "Browse" button at the top to select your working folder. This sets the default location for opening files and saving exports.

3.  **Input Your Draft:**
    *   Type your rough idea in the **"Draft Prompt"** text box.
    *   *(Optional)* Click **"Add"** under "Context Files" to attach relevant documents (PDF/DOCX/TXT).

4.  **Configure Models:**
    *   Select your desired **Gemini Model**.
    *   Select your desired **ChatGPT Model** and **Reasoning Level** (low/medium/high/xhigh).

5.  **Run Optimization:**
    *   Click **"RUN OPTIMIZATION"**.
    *   The application will send your draft + context to both models.
    *   Results will appear in the split view below.

6.  **Refine & Polish:**
    *   If you want changes, type instructions in the **"Feedback / Refinement"** box under the specific model's output (e.g., "Change the tone to professional").
    *   Click **"Refine"**. The model will update its prompt based on your feedback.

7.  **Export:**
    *   Click **"Export Prompts to JSON"** to save both versions to a `Prompts/` folder in your project directory.
    *   Use **"Copy to Clipboard"** to grab the text immediately.

## 📝 Configuration Details

The application uses the following internal defaults if no selection is made:
*   **Gemini:** `gemini-3-pro-preview`
*   **ChatGPT:** `gpt-5.2-codex` (Reasoning: `high`)

## ❓ Troubleshooting

*   **"gemini command not found":** Ensure the Gemini CLI is installed and in your system PATH.
*   **"codex command not found":** Ensure the Codex CLI is installed and in your system PATH.
*   **"Missing pdftotext tool":** Install `poppler-utils` (Linux) or `poppler` (macOS via brew) to enable PDF reading.
*   **Logs:** Check the "Logs" section at the bottom of the window for detailed error messages.

## 📄 License

[Your License Here]
