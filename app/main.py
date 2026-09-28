import os
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Body, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, EmailStr

from app.database import (
    init_db,
    create_user,
    authenticate_user,
    get_user_by_id,
    get_document_by_hash,
    get_document_by_id,
    insert_document,
    get_all_documents,
    delete_document_record,
    insert_chat_history,
    get_all_chat_history,
    delete_all_chat_history
)
from app.rag.ingestion import compute_sha256, extract_chunks_from_file
from app.rag.retrieval import (
    add_chunks_to_vector_store,
    retrieve_top_chunks,
    delete_document_vectors,
    reset_user_vectors,
    get_collection,
    CHROMA_DIR,
    EMBEDDING_MODEL_NAME
)
from app.rag.generation import (
    query_local_llm,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    EXACT_INSUFFICIENT_MSG
)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)

# Initialize database
init_db()

app = FastAPI(
    title="Academic Document Intelligence",
    description="Privacy-Preserving Academic Knowledge Management System",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_warmup():
    """Pre-warm embedding model and ChromaDB client on server boot."""
    try:
        from app.rag.retrieval import get_embedding_model, get_collection
        get_embedding_model()
        get_collection()
    except Exception:
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Request Schemas ---

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=4)
    confirm_password: Optional[str] = None


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to ask against uploaded documents")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    top_k: Optional[int] = Field(default=4, ge=1, le=20)


class StudyRequest(BaseModel):
    mode: str = Field(..., description="One of: explain, summarize, questions, notes")
    topic: Optional[str] = Field(default="", description="Optional focus topic")


# --- Auth Dependency ---

def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Extracts user_id from Authorization header.
    Format: 'Bearer <user_id>' or '<user_id>'.
    Defaults to 'anonymous' if no auth header for backward compatibility.
    """
    if not authorization:
        return "anonymous"
    
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return "anonymous"
    return token


# --- API Routes ---

router = APIRouter()


# 1. Auth Endpoints
@router.post("/auth/register")
async def register(req: RegisterRequest):
    if req.confirm_password and req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    
    try:
        user = create_user(name=req.name, email=req.email, password=req.password)
        return {
            "message": "Account created successfully.",
            "token": user["user_id"],
            "user": user
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/auth/login")
async def login(req: LoginRequest):
    user = authenticate_user(email=req.email, password=req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email/username or password.")
    
    return {
        "message": "Login successful.",
        "token": user["user_id"],
        "user": user
    }


@router.get("/auth/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    if user_id == "anonymous":
        return {"user_id": "anonymous", "name": "Guest User", "email": "guest@local"}
    
    user = get_user_by_id(user_id)
    if not user:
        return {"user_id": user_id, "name": "User", "email": ""}
    return user


# 2. Document Endpoints (User-Scoped)
@router.post("/upload")
@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id)
):
    filename = file.filename or "document.txt"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Only PDF, DOCX, and TXT files are accepted."
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    file_hash = compute_sha256(content)
    existing_doc = get_document_by_hash(user_id, file_hash)
    if existing_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate: '{existing_doc['filename']}' is already in your document library."
        )

    doc_id = str(uuid.uuid4())
    safe_file_name = f"{user_id}_{doc_id}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_file_name)

    try:
        with open(file_path, "wb") as f:
            f.write(content)

        # Extract text & split into chunks with user_id metadata
        chunks, total_pages = extract_chunks_from_file(
            file_path=file_path,
            filename=filename,
            doc_id=doc_id,
            user_id=user_id,
            chunk_size=800,
            chunk_overlap=100
        )

        # Vector indexing
        add_chunks_to_vector_store(chunks)

        # SQLite metadata
        doc_record = insert_document(
            user_id=user_id,
            doc_id=doc_id,
            filename=filename,
            file_hash=file_hash,
            file_size=len(content),
            file_path=file_path,
            total_pages=total_pages,
            chunk_count=len(chunks)
        )

        return JSONResponse(
            status_code=201,
            content={
                "message": f"'{filename}' uploaded and indexed successfully.",
                "document": doc_record
            }
        )

    except ValueError as ve:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@router.get("/documents")
async def list_documents(user_id: str = Depends(get_current_user_id)):
    """Returns list of documents belonging to the authenticated user."""
    return get_all_documents(user_id)


@router.get("/documents/{doc_id}/preview")
async def preview_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    """Returns document metadata and extracted text preview for Document Preview."""
    doc = get_document_by_id(user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_path = doc.get("file_path")
    text_preview = ""
    if file_path and os.path.exists(file_path):
        try:
            chunks, _ = extract_chunks_from_file(file_path, doc["filename"], doc_id, user_id=user_id)
            if chunks:
                sample_texts = [c["text"] for c in chunks[:4]]
                text_preview = "\n\n---\n\n".join(sample_texts)
        except Exception as e:
            text_preview = f"Could not extract preview: {str(e)}"

    return {
        "document": doc,
        "preview_text": text_preview
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    """Deletes document file, SQLite record, and ChromaDB embeddings for this user."""
    doc = get_document_by_id(user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # 1. Remove physical file
    file_path = doc.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

    # 2. Remove ChromaDB vectors
    delete_document_vectors(doc_id, user_id=user_id)

    # 3. Remove SQLite record
    delete_document_record(user_id, doc_id)

    return {"message": f"Document '{doc['filename']}' deleted successfully."}


# 3. Grounded Q&A Endpoint (User-Scoped)
@router.post("/ask")
@router.post("/chat")
async def ask_question(
    request: AskRequest,
    user_id: str = Depends(get_current_user_id)
):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    docs = get_all_documents(user_id)
    if not docs:
        return {
            "answer": "No documents uploaded yet. Please upload your academic documents (PDF, DOCX, TXT) on the Documents tab to ask questions.",
            "sources": []
        }

    # Top 4 chunks filtered by user_id
    top_chunks = retrieve_top_chunks(question, user_id=user_id, top_k=4)

    # Grounded answer generation
    result = await query_local_llm(question, top_chunks)

    # Record in SQLite chat history
    insert_chat_history(user_id, question, result["answer"], result["sources"])

    return result


# 4. Semantic Search Endpoint (User-Scoped)
@router.post("/search")
async def semantic_search(
    request: SearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    results = retrieve_top_chunks(query, user_id=user_id, top_k=request.top_k)
    return {
        "query": query,
        "results": results
    }


# 5. Study Mode Endpoint (4 Clean Modes)
@router.post("/study")
async def study_mode(
    request: StudyRequest,
    user_id: str = Depends(get_current_user_id)
):
    docs = get_all_documents(user_id)
    if not docs:
        return {
            "answer": "Please upload at least one document on the Documents tab before generating study material.",
            "sources": []
        }

    mode = request.mode.lower().strip()
    topic = request.topic.strip() if request.topic else "core concepts, theories, and takeaways"

    mode_instructions = {
        "explain": f"Explain the following academic concept in clear, structured, easy-to-understand detail based on the text: '{topic}'.",
        "summarize": f"Provide a comprehensive, high-yield academic summary of the main points and conclusions for: '{topic}'.",
        "questions": f"Generate 5 important exam and revision questions with concise answers based strictly on the text for: '{topic}'.",
        "notes": f"Create concise, bullet-pointed revision study notes highlighting key formulas, definitions, and takeaways for: '{topic}'."
    }

    instruction = mode_instructions.get(mode, mode_instructions["summarize"])
    top_chunks = retrieve_top_chunks(topic if topic else "key concepts summary", user_id=user_id, top_k=4)

    result = await query_local_llm(instruction, top_chunks)
    return result


# 6. Chat History Endpoints (User-Scoped)
@router.get("/history")
@router.get("/chats")
async def get_history(user_id: str = Depends(get_current_user_id)):
    return get_all_chat_history(user_id)


@router.delete("/history")
@router.delete("/chats")
async def clear_history(user_id: str = Depends(get_current_user_id)):
    delete_all_chat_history(user_id)
    return {"message": "Chat history cleared successfully."}


# 7. Reindex & System Settings
@router.post("/reindex")
async def reindex_documents(user_id: str = Depends(get_current_user_id)):
    """Rebuilds ChromaDB index for the current user from stored files."""
    documents = get_all_documents(user_id)
    reset_user_vectors(user_id)

    total_chunks = 0
    reindexed_count = 0

    for doc in documents:
        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                chunks, _ = extract_chunks_from_file(
                    file_path=file_path,
                    filename=doc["filename"],
                    doc_id=doc["doc_id"],
                    user_id=user_id,
                    chunk_size=800,
                    chunk_overlap=100
                )
                add_chunks_to_vector_store(chunks)
                total_chunks += len(chunks)
                reindexed_count += 1
            except Exception:
                pass

    return {
        "message": "Reindex complete.",
        "documents_reindexed": reindexed_count,
        "total_chunks_indexed": total_chunks
    }


@router.get("/settings")
async def get_system_settings(user_id: str = Depends(get_current_user_id)):
    docs = get_all_documents(user_id)
    collection = get_collection()
    return {
        "ollama_endpoint": OLLAMA_BASE_URL,
        "ollama_model": os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "vector_db": "ChromaDB (Persistent)",
        "vector_db_path": CHROMA_DIR,
        "database": "SQLite (rag_academic.db)",
        "user_documents_count": len(docs),
        "total_vectors_in_store": collection.count(),
        "processing_mode": "Local Processing Enabled",
        "privacy_guarantees": [
            "Documents processed and chunked locally",
            "Embeddings generated locally (all-MiniLM-L6-v2)",
            "ChromaDB persistent vector store on local disk",
            "Local LLM inference via Ollama (No cloud AI APIs)",
            "User-isolated documents and vector search"
        ]
    }


# Include router under both /api and root paths
app.include_router(router, prefix="/api")
app.include_router(router)

# Static assets
static_path = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(static_path / "index.html")
