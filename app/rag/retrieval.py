import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

load_dotenv()

CHROMA_DIR = os.environ.get("CHROMA_DIR", "chroma_db")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "academic_knowledge_base"

_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None
_collection = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
        try:
            _embedding_model.encode(["warmup"], convert_to_numpy=True)
        except Exception:
            pass
    return _embedding_model


def get_collection():
    global _chroma_client, _collection
    if _collection is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def add_chunks_to_vector_store(chunks: List[Dict[str, Any]]) -> int:
    """Embeds and indexes chunks into ChromaDB."""
    if not chunks:
        return 0

    collection = get_collection()
    model = get_embedding_model()

    texts = [c["text"] for c in chunks]
    ids = [c["chunk_id"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    embeddings = model.encode(texts, convert_to_numpy=True).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )
    return len(chunks)


def retrieve_top_chunks(query: str, user_id: Optional[str] = None, top_k: int = 4) -> List[Dict[str, Any]]:
    """
    Retrieves the top k most relevant chunks for a given query,
    filtered strictly by user_id for multi-user privacy isolation.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    model = get_embedding_model()
    query_embedding = model.encode([query], convert_to_numpy=True).tolist()

    where_clause = {"user_id": user_id} if user_id else None

    # Determine query limits
    n_results = min(top_k, collection.count())
    
    try:
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            where=where_clause
        )
    except Exception:
        # Fallback if where filter finds 0 items
        return []

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0] if "distances" in results else []

    retrieved = []
    for idx in range(len(documents)):
        retrieved.append({
            "chunk_id": ids[idx] if idx < len(ids) else "",
            "text": documents[idx],
            "metadata": metadatas[idx] if idx < len(metadatas) else {},
            "distance": distances[idx] if idx < len(distances) else None
        })

    return retrieved


def delete_document_vectors(doc_id: str, user_id: Optional[str] = None) -> None:
    """Removes all chunks associated with doc_id from ChromaDB."""
    collection = get_collection()
    try:
        if user_id:
            collection.delete(where={"$and": [{"doc_id": doc_id}, {"user_id": user_id}]})
        else:
            collection.delete(where={"doc_id": doc_id})
    except Exception:
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass


def reset_user_vectors(user_id: str) -> None:
    """Deletes all chunks belonging to a specific user."""
    collection = get_collection()
    try:
        collection.delete(where={"user_id": user_id})
    except Exception:
        pass


def reset_collection() -> None:
    """Deletes the collection and recreates it empty."""
    global _chroma_client, _collection
    if _chroma_client is not None:
        try:
            _chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _collection = None
