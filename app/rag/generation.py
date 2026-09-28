import os
from typing import List, Dict, Any
from dotenv import load_dotenv

import httpx

load_dotenv()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

EXACT_INSUFFICIENT_MSG = "There is not enough information in the uploaded documents to answer this."


async def query_local_llm(question: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sends retrieved chunks and question to local Ollama (Llama 3).
    Strictly enforces context grounding and returns source citations.
    """
    if not context_chunks:
        return {
            "answer": EXACT_INSUFFICIENT_MSG,
            "sources": []
        }

    # Format the context chunks clearly with their metadata
    context_lines = []
    for idx, c in enumerate(context_chunks):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Document")
        page = meta.get("page", 1)
        cid = meta.get("chunk_id", f"c{idx+1}")
        text = c.get("text", "").strip()
        context_lines.append(f"--- Document: {fname} | Page: {page} | Chunk ID: {cid} ---\n{text}")

    formatted_context = "\n\n".join(context_lines)

    system_prompt = (
        "You are an academic knowledge management assistant.\n"
        "Answer the user's question STRICTLY and ONLY using the provided document context below.\n"
        "Do not use any prior knowledge or external information.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "If the context does not contain sufficient facts to directly answer the question, "
        "or if the question is unrelated to the context, you must reply with EXACTLY this sentence and nothing else:\n"
        f"{EXACT_INSUFFICIENT_MSG}\n\n"
        "Do not invent facts, citations, or page numbers. "
        "Be concise, academic, and completely grounded in the context."
    )

    user_prompt = f"Context:\n{formatted_context}\n\nQuestion:\n{question}\n\nAnswer:"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False,
        "keep_alive": "24h",
        "options": {
            "temperature": 0.0,
            "num_predict": 300,
            "num_ctx": 2048,
            "top_k": 20,
            "top_p": 0.9
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload
            )

            if resp.status_code == 404:
                return {
                    "answer": f"Ollama model '{OLLAMA_MODEL}' was not found. Please run 'ollama pull {OLLAMA_MODEL}' in your terminal.",
                    "sources": []
                }

            resp.raise_for_status()
            data = resp.json()
            answer_text = data.get("message", {}).get("content", "").strip()

    except httpx.ConnectError:
        return {
            "answer": "Error: Ollama is not accessible at http://localhost:11434. Please start the local Ollama service.",
            "sources": []
        }
    except Exception as e:
        return {
            "answer": f"Error communicating with local LLM: {str(e)}",
            "sources": []
        }

    # Normalize response if model indicates insufficient information
    normalized_answer = answer_text.strip().strip('"').strip("'")
    if (
        EXACT_INSUFFICIENT_MSG.lower() in normalized_answer.lower()
        or "not enough information" in normalized_answer.lower()
        or "does not contain" in normalized_answer.lower()
    ):
        return {
            "answer": EXACT_INSUFFICIENT_MSG,
            "sources": []
        }

    # Extract unique, valid sources with verified text snippet
    sources = []
    seen = set()
    for c in context_chunks:
        meta = c.get("metadata", {})
        fname = meta.get("filename")
        page = meta.get("page", 1)
        cid = meta.get("chunk_id", "")
        text_chunk = c.get("text", "").strip()
        snippet = (text_chunk[:280] + "...") if len(text_chunk) > 280 else text_chunk

        if fname:
            key = (fname, page, cid)
            if key not in seen:
                seen.add(key)
                sources.append({
                    "filename": fname,
                    "page": page,
                    "chunk": cid,
                    "snippet": snippet
                })

    return {
        "answer": normalized_answer,
        "sources": sources
    }
