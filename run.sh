#!/usr/bin/env bash
# Run JARVIS. Defaults to voice mode.
# Usage:
#   ./run.sh              -> voice
#   ./run.sh chat         -> text chat
#   ./run.sh ingest       -> rebuild vector store
#   ./run.sh ask "q"      -> single question
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo ".venv missing. Run ./setup.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# macOS fork-safety hardening. PyAudio + torch/sentence-transformers +
# subprocess can segfault the Python interpreter on Darwin. These env
# vars disable the problematic paths.
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export ANONYMIZED_TELEMETRY=false

CMD="${1:-voice}"
shift || true
python main.py "$CMD" "$@"
