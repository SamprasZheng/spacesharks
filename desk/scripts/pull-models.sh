#!/usr/bin/env bash
# Pull the 5 primary + 3 backup voter models on the host's WSL Ollama.
# Run with:  wsl -d Ubuntu -- bash /mnt/d/DOT/spacesharks/desk/scripts/pull-models.sh
set -u
export PATH="$HOME/.local/bin:$PATH"
MODELS=(
  "qwen3:4b"
  "llama3.2:3b"
  "phi3.5"
  "gemma2:2b"
  "mistral:7b"
  "deepseek-r1:7b"
  "granite3-dense:2b"
)
for m in "${MODELS[@]}"; do
  echo "=== pulling $m ==="
  ollama pull "$m" 2>&1 | tail -3
done
echo "=== done ==="
ollama list
