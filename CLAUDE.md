# agentic-bot

JARVIS voice assistant + RAG agent + Nexus Orchestrator (Kafka/Postgres/multi-tenant) per `ARCHITECTURE.md`.

## Run

```
./run.sh ask "q"   # one-shot
./run.sh chat      # interactive
./run.sh voice     # JARVIS wake-word loop
./run.sh ingest    # rebuild ChromaDB
```

`./setup.sh` first if `.venv` missing.

## Architecture notes

- Voice mode: brain runs in **separate process** (`jarvis/brain_client.py` ↔ `jarvis/brain.py`). PyAudio + ChromaDB + claude-cli + macOS `say` crash each other if shared.
- macOS fork-safety env vars required (set in `run.sh`): `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`, `TOKENIZERS_PARALLELISM=false`, `OMP_NUM_THREADS=1`.
- Backend: claude-cli subprocess (`agent_claude_cli.py`), not direct API.
- STT: local faster-whisper by default (`jarvis/stt_whisper.py`), Google Web Speech fallback (`jarvis/stt_google.py`). First `./run.sh voice` downloads the `base` model (~140MB) to `~/.cache/huggingface`; offline after that. Capture lives in `jarvis/voice_in.py`; transcription is swappable via `STT_BACKEND`.
- Wake words include common mishearings (jarvus, service, harvest, etc).

## Skill routing

Use installed skills when the task matches. Skills live in `~/.claude/skills/`.

| Task | Skill |
|---|---|
| Investigating any bug / test failure / unexpected behavior | `superpowers:systematic-debugging` |
| New feature, before writing code | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Writing implementation code | `superpowers:test-driven-development` |
| Executing a written plan | `superpowers:executing-plans` |
| 2+ independent subtasks | `superpowers:dispatching-parallel-agents` |
| Before claiming work is done / before commit | `superpowers:verification-before-completion` |
| Receiving review feedback | `superpowers:receiving-code-review` |
| Pre-merge code review | `/gstack-review` or `/code-review:code-review` |
| Investigation / repo archaeology | `/gstack-investigate` |
| Shipping / deploy | `/gstack-ship`, `/gstack-land-and-deploy` |
| Frontend / UI work | `/frontend-design:frontend-design` |
| Security review of changes | `/security-review` |

If unsure which skill applies, list relevant ones with `ls ~/.claude/skills/` and pick by name.

## Conventions

- Python 3.12, `pyproject.toml`. Voice deps optional: `pip install '.[jarvis]'`.
- Tests in `tests/`. Run with `pytest`.
- Don't touch `chroma_db/` — vector store, regenerate via `./run.sh ingest`.
- `.env.local` overrides `.env`. Never commit either.
- Config validation in `config.py` — extend there, don't sprinkle env reads.

## Current state

- RAG agent: working, committed (`agent.py`, `ingest.py`, `retriever.py`). Two backends via `AGENT_BACKEND`: `claude_cli` (default in use) or `api`.
- JARVIS voice: working, committed (`jarvis/`).
- Orchestrator (`orchestrator/`): code complete per ARCHITECTURE.md (core loop, state store, event bus, decomposer, API, worker, schema.sql) but never run against live Kafka/Redis/Postgres. Unit tests exist for decomposer + models only.