import os
import chromadb
from pypdf import PdfReader
from config import get_settings

_settings = get_settings()

_chroma_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=_settings.chroma_persist_dir)
    return _chroma_client


def load_text_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_pdf_file(filepath: str) -> str:
    reader = PdfReader(filepath)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_document(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return load_pdf_file(filepath)
    elif ext == ".txt":
        return load_text_file(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    if chunk_size is None:
        chunk_size = _settings.chunk_size
    if overlap is None:
        overlap = _settings.chunk_overlap
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def ingest_documents():
    documents_dir = _settings.documents_dir
    if not os.path.exists(documents_dir):
        print(f"Documents directory not found: {documents_dir}")
        return

    files = [
        f for f in os.listdir(documents_dir)
        if os.path.splitext(f)[1].lower() in (".txt", ".pdf")
    ]

    if not files:
        print("No .txt or .pdf files found in documents/")
        return

    client = _get_client()

    # Delete existing collection to re-ingest cleanly
    try:
        client.delete_collection(_settings.collection_name)
    except Exception:
        pass

    collection = client.get_or_create_collection(name=_settings.collection_name)

    all_ids = []
    all_documents = []
    all_metadatas = []

    for filename in files:
        filepath = os.path.join(documents_dir, filename)
        print(f"Loading {filename}...")
        text = load_document(filepath)
        chunks = chunk_text(text)
        print(f"  -> {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            all_ids.append(f"{filename}__chunk_{i}")
            all_documents.append(chunk)
            all_metadatas.append({"source": filename, "chunk_index": i})

    if all_documents:
        collection.add(
            ids=all_ids,
            documents=all_documents,
            metadatas=all_metadatas,
        )
        print(f"\nIngested {len(all_documents)} chunks from {len(files)} file(s).")
    else:
        print("No content extracted from documents.")
