import anthropic
from config import get_settings
from retriever import retrieve

_settings = get_settings()


def _get_client() -> "anthropic.Anthropic":
    return anthropic.Anthropic(api_key=_settings.anthropic_api_key)

SYSTEM_PROMPT = """You are JARVIS, a witty, concise AI assistant modeled after Tony Stark's JARVIS.

Rules:
- Prefer the provided context documents when the question relates to them, and cite the source.
- For general questions outside the context, answer from your own knowledge.
- Keep replies short and spoken-friendly (no markdown, no bullet lists)."""


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant documents found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk["metadata"]["source"]
        parts.append(f"[Source {i}: {source}]\n{chunk['text']}")
    return "\n\n".join(parts)


def _ask_api(question: str) -> str:
    chunks = retrieve(question)
    context = build_context(chunks)

    message = _get_client().messages.create(
        model=_settings.model_name,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            }
        ],
    )

    return message.content[0].text


def ask(question: str) -> str:
    backend = _settings.agent_backend.lower()
    if backend == "claude_cli":
        from agent_claude_cli import ask as _ask_cli

        return _ask_cli(question)
    if backend == "api":
        return _ask_api(question)
    raise ValueError(f"Unknown AGENT_BACKEND: {_settings.agent_backend!r}")
