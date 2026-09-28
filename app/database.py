import os
import json
import sqlite3
import hashlib
import uuid
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "rag_academic.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    """Secure password hashing using PBKDF2-HMAC-SHA256 with random salt."""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}:{dk}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:hash."""
    try:
        salt, dk = stored_hash.split(":")
        check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return check == dk
    except Exception:
        return False

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Documents Table (with user_id isolation)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            total_pages INTEGER DEFAULT 1,
            chunk_count INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, file_hash)
        )
    """)
    
    # 3. Chat History Table (with user_id isolation)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

# --- User Management ---

def create_user(name: str, email: str, password: str) -> Dict[str, Any]:
    email_clean = email.strip().lower()
    name_clean = name.strip()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM users WHERE email = ?", (email_clean,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("An account with this email/username already exists.")
    
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)
    
    cursor.execute("""
        INSERT INTO users (user_id, name, email, password_hash)
        VALUES (?, ?, ?, ?)
    """, (user_id, name_clean, email_clean, pw_hash))
    
    conn.commit()
    conn.close()
    
    return {
        "user_id": user_id,
        "name": name_clean,
        "email": email_clean
    }

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    email_clean = email.strip().lower()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    if verify_password(password, row["password_hash"]):
        return {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"]
        }
    return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, email, created_at FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# --- Document Management (User Isolated) ---

def get_document_by_hash(user_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE user_id = ? AND file_hash = ?", (user_id, file_hash))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_document_by_id(user_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE user_id = ? AND doc_id = ?", (user_id, doc_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def insert_document(user_id: str, doc_id: str, filename: str, file_hash: str, file_size: int, file_path: str, total_pages: int, chunk_count: int) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (doc_id, user_id, filename, file_hash, file_size, file_path, total_pages, chunk_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, user_id, filename, file_hash, file_size, file_path, total_pages, chunk_count))
    conn.commit()
    conn.close()
    return {
        "doc_id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "file_hash": file_hash,
        "file_size": file_size,
        "file_path": file_path,
        "total_pages": total_pages,
        "chunk_count": chunk_count
    }

def get_all_documents(user_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_document_record(user_id: str, doc_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE user_id = ? AND doc_id = ?", (user_id, doc_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# --- Chat History Management (User Isolated) ---

def insert_chat_history(user_id: str, question: str, answer: str, sources: List[Dict[str, Any]]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    sources_json = json.dumps(sources)
    cursor.execute("""
        INSERT INTO chat_history (user_id, question, answer, sources)
        VALUES (?, ?, ?, ?)
    """, (user_id, question, answer, sources_json))
    history_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return history_id

def get_all_chat_history(user_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        item = dict(r)
        try:
            item["sources"] = json.loads(item.get("sources", "[]"))
        except Exception:
            item["sources"] = []
        results.append(item)
    return results

def delete_all_chat_history(user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True
