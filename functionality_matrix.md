| Flag | Python Argument | Default | Description |
| :--- | :--- | :--- | :--- |
| `-m`, `--models` | `models` | Required | Comma-separated list of providers/models (e.g., "gemini,codex:gpt-4"). |
| `-n`, `--iterations` | `iterations` | Required | Number of iterations per model (must be > 0). |
| `-p`, `--prompt` | `prompt` | None | Input prompt text. Mutually exclusive with `-f`. |
| `-f`, `--prompt-file` | `prompt_file` | None | Input prompt file path. Mutually exclusive with `-p`. |
| `[Positional]` | `positional_prompt` | None | Fallback if `-p` is not used. |
| `-o`, `--outdir` | `outdir` | `./llm_ensemble_<timestamp>` | Directory for output artifacts. |
| `--gemini-model` | `gemini_model` | `gemini-3-pro-preview` | Default model name for Gemini provider. |
| `--codex-model` | `codex_model` | `gpt-5.2-codex` | Default model name for Codex provider. |
| `--codex-reasoning` | `codex_reasoning` | `high` | Reasoning effort for Codex (minimal-xhigh). |
| `--merge-codex-model` | `merge_codex_model` | `None` (Defaults to first used Codex or default) | Specific Codex model for the final merge step. |
| `--merge-reasoning` | `merge_reasoning` | `None` (Defaults to `codex_reasoning`) | Reasoning effort for the final merge step. |
| `--merge-prompt` | `merge_prompt` | `None` | Custom text for merge instruction. |
| `--merge-prompt-file` | `merge_prompt_file` | `None` | File path for custom merge instruction. |
| `--timeout` | `timeout` | `300` | Timeout in seconds per model execution (0 to disable). |
| `--format` | `format` | `txt` | Output format: `txt` or `rtf`. |
| `--require-git` | `require_git` | `False` | If set, enables git repo checks in Codex (removes `--skip-git-repo-check`). |
