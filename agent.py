import anthropic
from config import get_settings
from retriever import retrieve

_settings = get_settings()
client = anthropic.Anthropic(api_key=_settings.anthropic_api_key)

SYSTEM_PROMPT = """You are a helpful Q&A assistant. Answer the user's question based on the provided context documents.

Rules:
- Only use information from the provided context to answer questions.
- If the context doesn't contain enough information, say so clearly.
- Reference which source document(s) your answer comes from.
- Be concise and accurate."""


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant documents found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk["metadata"]["source"]
        parts.append(f"[Source {i}: {source}]\n{chunk['text']}")
    return "\n\n".join(parts)


def ask(question: str) -> str:
    chunks = retrieve(question)
    context = build_context(chunks)

    message = client.messages.create(
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
