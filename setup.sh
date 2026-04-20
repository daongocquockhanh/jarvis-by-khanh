#!/usr/bin/env bash
# One-shot setup: venv, deps, env file.
# Usage: ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3.12 python3.11; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "Need python3.11 or python3.12. Install: brew install python@3.12"
  exit 1
fi
echo "Using: $($PY --version)"

if [ -d .venv ]; then
  VENV_PY_VER="$(.venv/bin/python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
  case "$VENV_PY_VER" in
    3.11|3.12|3.13) ;;
    *) echo "Removing old .venv (py $VENV_PY_VER)"; rm -rf .venv ;;
  esac
fi

if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip wheel

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. PyAudio may fail. Install brew: https://brew.sh"
else
  brew list portaudio >/dev/null 2>&1 || brew install portaudio
fi

pip install -e '.[rag,jarvis,dev]'

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env — set ANTHROPIC_API_KEY before running."
fi

mkdir -p documents

echo ""
echo "Setup done."
echo "Activate:   source .venv/bin/activate"
echo "Ingest:     python main.py ingest"
echo "Chat:       python main.py chat"
echo "Voice:      python main.py voice"