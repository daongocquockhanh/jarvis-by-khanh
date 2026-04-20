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

CMD="${1:-voice}"
shift || true
python main.py "$CMD" "$@"
