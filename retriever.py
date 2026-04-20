import chromadb
from config import get_settings

_settings = get_settings()

_chroma_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=_settings.chroma_persist_dir)
    return _chroma_client


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    if top_k is None:
        top_k = _settings.top_k
    client = _get_client()

    try:
        collection = client.get_collection(name=_settings.collection_name)
    except ValueError:
        print("No document collection found. Run 'python main.py ingest' first.")
        return []

    results = collection.query(query_texts=[query], n_results=top_k)

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })

    return chunks
