#!/usr/bin/env bash
# llm_ensemble.sh (provider:model aware; sensible defaults)
# Defaults:
#   Gemini model: gemini-3-pro-preview
#   Codex model:  gpt-5.2-codex
#   Codex reasoning effort: high

set -uo pipefail

usage() {
  cat <<'EOF'
Usage:
  llm_ensemble.sh -m gemini,codex -n 3 -p "..."
  llm_ensemble.sh -m "gemini:gemini-3-pro-preview,codex:gpt-5.2-codex" -n 3 -p "..."

Required:
  -m, --models        Comma-separated list of runners:
                        - "gemini" or "gemini:<model>"
                        - "codex"  or "codex:<model>"
  -n, --iterations    Positive integer

Prompt input (choose one):
  -p, --prompt        Prompt text
  -f, --prompt-file   File containing prompt
  (or pipe prompt via stdin)

Optional:
  -o, --outdir            Output directory (default: ./llm_ensemble_<timestamp>)
      --gemini-model      Default Gemini model if not specified in -m
      --codex-model       Default Codex model if not specified in -m
      --codex-reasoning   Codex reasoning effort: minimal|low|medium|high|xhigh (default: high)
      --merge-codex-model Codex model used ONLY for the final merge (default: first codex model found)
      --merge-reasoning   Reasoning effort used ONLY for the final merge (default: same as --codex-reasoning)
      --merge-prompt      Custom text instruction for the final merge step
      --merge-prompt-file File containing custom instruction for the final merge step
      --timeout           Per-run timeout seconds (default: 300; 0 disables)
      --format            Output format: txt (default) or rtf
      --require-git       Do NOT pass --skip-git-repo-check to codex
  -h, --help              Show help
EOF
}

die(){ echo "Error: $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

MODELS_CSV=""
ITERATIONS=""
PROMPT_TEXT=""
PROMPT_FILE=""
OUTDIR=""

# >>> DEFAULTS YOU ASKED FOR <<<
DEFAULT_GEMINI_MODEL="gemini-3-pro-preview"
DEFAULT_CODEX_MODEL="gpt-5.2-codex"
DEFAULT_CODEX_REASONING="high"
# >>> END DEFAULTS <<<

MERGE_CODEX_MODEL=""
MERGE_CODEX_REASONING=""
TIMEOUT_SECS=300
SKIP_GIT_CHECK=1
OUTPUT_FORMAT="txt"
MERGE_PROMPT_TEXT=""
MERGE_PROMPT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--models) MODELS_CSV="${2:-}"; shift 2 ;;
    -n|--iterations) ITERATIONS="${2:-}"; shift 2 ;;
    -p|--prompt) PROMPT_TEXT="${2:-}"; shift 2 ;;
    -f|--prompt-file) PROMPT_FILE="${2:-}"; shift 2 ;;
    -o|--outdir) OUTDIR="${2:-}"; shift 2 ;;
    --gemini-model) DEFAULT_GEMINI_MODEL="${2:-}"; shift 2 ;;
    --codex-model) DEFAULT_CODEX_MODEL="${2:-}"; shift 2 ;;
    --codex-reasoning) DEFAULT_CODEX_REASONING="${2:-}"; shift 2 ;;
    --merge-codex-model) MERGE_CODEX_MODEL="${2:-}"; shift 2 ;;
    --merge-reasoning) MERGE_CODEX_REASONING="${2:-}"; shift 2 ;;
    --merge-prompt) MERGE_PROMPT_TEXT="${2:-}"; shift 2 ;;
    --merge-prompt-file) MERGE_PROMPT_FILE="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT_SECS="${2:-}"; shift 2 ;;
    --format) OUTPUT_FORMAT="${2:-}"; shift 2 ;;
    --require-git) SKIP_GIT_CHECK=0; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ "$1" == -* ]]; then
        die "Unknown argument: $1"
      else
        if [[ -n "$PROMPT_TEXT" ]]; then
           die "Multiple prompt arguments provided. Please quote your prompt or use -p."
        fi
        PROMPT_TEXT="$1"
        shift 1
      fi
      ;;
  esac
done

if [[ -n "$MERGE_PROMPT_TEXT" && -n "$MERGE_PROMPT_FILE" ]]; then
  die "Use only one of --merge-prompt or --merge-prompt-file"
fi

[[ -n "$MODELS_CSV" ]] || { usage; die "--models is required"; }
[[ -n "$ITERATIONS" ]] || { usage; die "--iterations is required"; }
[[ "$ITERATIONS" =~ ^[0-9]+$ ]] && [[ "$ITERATIONS" -ge 1 ]] || die "--iterations must be a positive integer"
[[ "$TIMEOUT_SECS" =~ ^[0-9]+$ ]] || die "--timeout must be an integer"
if [[ "$OUTPUT_FORMAT" != "txt" && "$OUTPUT_FORMAT" != "rtf" ]]; then
  die "Invalid format: $OUTPUT_FORMAT. Supported: txt, rtf"
fi

validate_reasoning() {
  case "${1:-}" in
    minimal|low|medium|high|xhigh) return 0 ;;
    *) die "Invalid reasoning effort: '$1' (use minimal|low|medium|high|xhigh)" ;;
  esac
}
validate_reasoning "$DEFAULT_CODEX_REASONING"
[[ -n "$MERGE_CODEX_REASONING" ]] && validate_reasoning "$MERGE_CODEX_REASONING"

if [[ -n "$PROMPT_TEXT" && -n "$PROMPT_FILE" ]]; then
  die "Use only one of --prompt or --prompt-file"
fi

if [[ -z "$OUTDIR" ]]; then
  TS="$(date +%Y%m%d_%H%M%S)"
  OUTDIR="./llm_ensemble_${TS}"
fi
mkdir -p "$OUTDIR" || die "Cannot create outdir: $OUTDIR"

PROMPT_CANON="$OUTDIR/prompt.txt"
if [[ -n "$PROMPT_FILE" ]]; then
  [[ -f "$PROMPT_FILE" ]] || die "Prompt file not found: $PROMPT_FILE"
  [[ -s "$PROMPT_FILE" ]] || die "Prompt file is empty: $PROMPT_FILE"

  if have file; then
    mime_encoding="$(file --brief --mime-encoding "$PROMPT_FILE")"
    if [[ "$mime_encoding" == "binary" ]]; then
      die "Prompt file appears to be binary: $PROMPT_FILE"
    fi

    if [[ "$mime_encoding" != "utf-8" && "$mime_encoding" != "us-ascii" ]]; then
      if have iconv; then
        if iconv -f "$mime_encoding" -t "UTF-8" "$PROMPT_FILE" > "$PROMPT_CANON" 2>/dev/null; then
           : # Successfully converted
        else
           echo "Warning: Failed to convert $PROMPT_FILE from $mime_encoding to UTF-8. Using original." >&2
           cp "$PROMPT_FILE" "$PROMPT_CANON"
        fi
      else
        cp "$PROMPT_FILE" "$PROMPT_CANON"
      fi
    else
      cp "$PROMPT_FILE" "$PROMPT_CANON"
    fi
  else
    # Fallback if 'file' not available
    cp "$PROMPT_FILE" "$PROMPT_CANON"
  fi
elif [[ -n "$PROMPT_TEXT" ]]; then
  printf "%s" "$PROMPT_TEXT" > "$PROMPT_CANON"
else
  [[ -t 0 ]] && { usage; die "No prompt provided. Use --prompt, --prompt-file, or pipe stdin."; }
  cat > "$PROMPT_CANON"
fi

run_with_timeout() {
  if [[ "$TIMEOUT_SECS" -gt 0 ]] && have timeout; then
    timeout "${TIMEOUT_SECS}s" "$@"
  else
    "$@"
  fi
}

# -------- runner parsing: builds RUNNERS as "provider|model|label" ----------
normalize(){ local s="$1"; s="${s,,}"; s="${s//[[:space:]]/}"; echo "$s"; }
sanitize_label(){ local s="$1"; s="${s//[^a-zA-Z0-9._-]/_}"; echo "$s"; }

IFS=',' read -r -a RAW_LIST <<< "$MODELS_CSV"
RUNNERS=()
FOUND_CODEX_MODEL_FOR_MERGE=""

for raw in "${RAW_LIST[@]}"; do
  raw="$(normalize "$raw")"
  [[ -n "$raw" ]] || continue

  provider="${raw%%:*}"
  model=""
  if [[ "$raw" == *:* ]]; then
    model="${raw#*:}"
  fi

  case "$provider" in
    gemini)
      [[ -n "$model" ]] || model="$DEFAULT_GEMINI_MODEL"
      label="gemini__$(sanitize_label "$model")"
      RUNNERS+=("gemini|$model|$label")
      ;;
    codex)
      [[ -n "$model" ]] || model="$DEFAULT_CODEX_MODEL"
      label="codex__$(sanitize_label "$model")"
      RUNNERS+=("codex|$model|$label")
      if [[ -z "$FOUND_CODEX_MODEL_FOR_MERGE" && -n "$model" ]]; then
        FOUND_CODEX_MODEL_FOR_MERGE="$model"
      fi
      ;;
    *)
      die "Unknown provider in --models: $provider (allowed: gemini, codex)"
      ;;
  esac
done

[[ ${#RUNNERS[@]} -gt 0 ]] || die "No valid runners parsed from --models"

# Final merge model + reasoning defaults
if [[ -z "$MERGE_CODEX_MODEL" ]]; then
  MERGE_CODEX_MODEL="$FOUND_CODEX_MODEL_FOR_MERGE"
fi
[[ -n "$MERGE_CODEX_MODEL" ]] || MERGE_CODEX_MODEL="$DEFAULT_CODEX_MODEL"
[[ -n "$MERGE_CODEX_REASONING" ]] || MERGE_CODEX_REASONING="$DEFAULT_CODEX_REASONING"

# -------- dependency checks ----------
NEED_GEMINI=0
for r in "${RUNNERS[@]}"; do
  provider="${r%%|*}"
  [[ "$provider" == "gemini" ]] && NEED_GEMINI=1
done

if [[ $NEED_GEMINI -eq 1 ]] && ! have gemini; then
  die "gemini command not found on PATH."
fi
if ! have codex; then
  die "codex command not found on PATH. (Needed at least for the final merge.)"
fi

JSON_PARSER=""
if [[ $NEED_GEMINI -eq 1 ]]; then
  if have jq; then JSON_PARSER="jq"
  elif have python3; then JSON_PARSER="python3"
  else die "Need jq or python3 to parse Gemini JSON output."
  fi
fi

parse_gemini_json_response() {
  local json_file="$1"
  if [[ "$JSON_PARSER" == "jq" ]]; then
    jq -r '.response // ""' "$json_file"
  else
    python3 - "$json_file" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    d=json.load(f)
print(d.get("response","") or "")
PY
  fi
}

run_gemini_once() {
  # Usage: run_gemini_once <prompt_file> <model> <out_txt> <log>
  local prompt_file="$1"; local model="$2"; local out_txt="$3"; local log_file="$4"
  local json_out="${out_txt%.txt}.json"

  local -a cmd=(gemini --output-format json)
  [[ -n "$model" ]] && cmd+=(--model "$model")

  if ! run_with_timeout env NO_COLOR=1 "${cmd[@]}" < "$prompt_file" > "$json_out" 2> "$log_file"; then
    echo "[gemini] ERROR: command failed (see $log_file)" > "$out_txt"
    return 1
  fi

  parse_gemini_json_response "$json_out" > "$out_txt"
}

run_codex_once() {
  # Usage: run_codex_once <prompt_file> <model> <reasoning> <out_txt> <log>
  local prompt_file="$1"; local model="$2"; local reasoning="$3"; local out_txt="$4"; local log_file="$5"

  local -a cmd=(codex exec --sandbox read-only --color never)
  [[ $SKIP_GIT_CHECK -eq 1 ]] && cmd+=(--skip-git-repo-check)
  [[ -n "$model" ]] && cmd+=(--model "$model")

  # Force reasoning effort for this run (TOML string)
  cmd+=(--config "model_reasoning_effort=\"${reasoning}\"")

  cmd+=(-)

  if ! run_with_timeout "${cmd[@]}" < "$prompt_file" > "$out_txt" 2> "$log_file"; then
    echo "[codex] ERROR: command failed (see $log_file)" > "$out_txt"
    return 1
  fi
}

# -------- run ensemble ----------
RESULT_FILES=()

for runner in "${RUNNERS[@]}"; do
  provider="$(cut -d'|' -f1 <<<"$runner")"
  model="$(cut -d'|' -f2 <<<"$runner")"
  label="$(cut -d'|' -f3 <<<"$runner")"

  for ((i=1; i<=ITERATIONS; i++)); do
    base="$OUTDIR/${label}_run_${i}"
    out_txt="${base}.txt"
    log_file="${base}.log"

    echo "Running ${provider} model='${model:-default}' (${i}/${ITERATIONS})..." >&2

    case "$provider" in
      gemini)
        run_gemini_once "$PROMPT_CANON" "$model" "$out_txt" "$log_file" || true
        ;;
      codex)
        run_codex_once "$PROMPT_CANON" "$model" "$DEFAULT_CODEX_REASONING" "$out_txt" "$log_file" || true
        ;;
    esac

    RESULT_FILES+=("$out_txt")
  done
done

# -------- build merge prompt ----------
MERGE_PROMPT="$OUTDIR/merge_prompt.txt"

DEFAULT_MERGE_INSTRUCTION=$(cat <<'EOF'
You are given:
1) The user's original prompt.
2) Multiple candidate answers generated by different models and/or runs.

Task:
- Produce a single best final answer to the user's original prompt.
- Combine the strongest parts of the candidates, fix mistakes, resolve contradictions.
- If something is uncertain, say so plainly.
- Do NOT mention the candidates, tools, or your merging process.
- Output ONLY the final answer.

USER PROMPT:
<<<
EOF
)

FINAL_MERGE_INSTRUCTION=""

if [[ -n "$MERGE_PROMPT_FILE" ]]; then
  [[ -f "$MERGE_PROMPT_FILE" ]] || die "Merge prompt file not found: $MERGE_PROMPT_FILE"
  FINAL_MERGE_INSTRUCTION=$(cat "$MERGE_PROMPT_FILE")
elif [[ -n "$MERGE_PROMPT_TEXT" ]]; then
  FINAL_MERGE_INSTRUCTION="$MERGE_PROMPT_TEXT"
else
  FINAL_MERGE_INSTRUCTION="$DEFAULT_MERGE_INSTRUCTION"
fi

{
  echo "$FINAL_MERGE_INSTRUCTION"
  cat "$PROMPT_CANON"
  cat <<'MID'
>>>

CANDIDATE ANSWERS:
MID

  for f in "${RESULT_FILES[@]}"; do
    name="$(basename "$f")"
    printf "\n--- %s ---\n<<<\n" "$name"
    cat "$f"
    printf "\n>>>\n"
  done

  cat <<'FOOT'

FINAL ANSWER (output only this):
FOOT
} > "$MERGE_PROMPT"

# -------- final merge (Codex) ----------
FINAL_OUT="$OUTDIR/final.txt"
FINAL_LOG="$OUTDIR/final.log"

echo "Merging with Codex model='${MERGE_CODEX_MODEL}' reasoning='${MERGE_CODEX_REASONING}'..." >&2
run_codex_once "$MERGE_PROMPT" "$MERGE_CODEX_MODEL" "$MERGE_CODEX_REASONING" "$FINAL_OUT" "$FINAL_LOG" || true

convert_text_to_rtf() {
  # Usage: convert_text_to_rtf < input_txt > output_rtf
  local py_script="$OUTDIR/_rtf_converter.py"
  cat > "$py_script" <<'PY'
import sys

def text_to_rtf(text):
    # Basic RTF header
    header = r"{\rtf1\ansi\deff0{\fonttbl{\f0\fswiss\fcharset0 Arial;}}\viewkind4\uc1\pard\f0\fs24 "
    footer = r"}"
    
    # Escape special RTF chars
    escaped = text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
    
    # Handle newlines
    escaped = escaped.replace('\n', '\\par\n')
    
    # Handle unicode
    res = []
    for char in escaped:
        if ord(char) > 127:
            res.append(f"\\u{ord(char)}?")
        else:
            res.append(char)
    
    return header + "".join(res) + footer

if __name__ == "__main__":
    content = sys.stdin.read()
    print(text_to_rtf(content))
PY

  python3 "$py_script"
  rm "$py_script"
}

if [[ "$OUTPUT_FORMAT" == "rtf" ]]; then
  FINAL_RTF="${FINAL_OUT%.txt}.rtf"
  convert_text_to_rtf < "$FINAL_OUT" > "$FINAL_RTF"
  echo "[Generated RTF: $FINAL_RTF]" >&2
else
  cat "$FINAL_OUT"
fi

printf "\n[Saved artifacts in: %s]\n" "$OUTDIR" >&2
