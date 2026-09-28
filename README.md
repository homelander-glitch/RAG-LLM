# Privacy-Preserving Academic Knowledge Management System

A local Retrieval-Augmented Generation (RAG) system for academic documents. All documents, vector embeddings, similarity search, and LLM inference run strictly on your local machine without sending data to third-party cloud services.

## Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Text Processing**: LangChain (`RecursiveCharacterTextSplitter`), `pypdf`, `python-docx`
- **Embeddings**: Sentence Transformers (`all-MiniLM-L6-v2`) running locally
- **Vector Database**: ChromaDB (Persistent storage)
- **Local LLM**: Ollama running `llama3` locally (`http://localhost:11434`)
- **Metadata & History**: SQLite (`rag_academic.db`)
- **Frontend**: Plain HTML, CSS, and Vanilla JavaScript

## Project Structure

```text
RAG-LLM/
├── app/
│   ├── main.py              # FastAPI endpoints & static routing
│   ├── database.py          # SQLite metadata, hashes & chat history
│   ├── rag/
│   │   ├── ingestion.py     # Document extraction, SHA-256 & chunking
│   │   ├── retrieval.py     # ChromaDB indexing & top-4 retrieval
│   │   └── generation.py    # Local Ollama Llama 3 grounded generation
│   └── static/
│       ├── index.html       # Minimal academic UI (Chat, Documents, Study, Search, Settings)
│       ├── style.css        # Restrained academic stylesheet
│       └── script.js        # Vanilla JS API interactions
├── uploads/                 # Stored document files
├── chroma_db/               # Persistent vector database
├── requirements.txt         # Minimal Python dependencies
├── .env.example             # Configuration template
├── .gitignore
└── README.md
```

## Installation

1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd Desktop/RAG-LLM
   ```

2. (Optional) Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install required dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

## Ollama & Llama 3 Setup

1. Install [Ollama](https://ollama.com) on your computer.
2. Verify Ollama is running:
   ```powershell
   ollama --version
   ```
3. Pull the local `llama3` model:
   ```powershell
   ollama pull llama3
   ```

## How to Run

1. Start the FastAPI application with Uvicorn:
   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. Open your web browser and navigate to:
   ```text
   http://127.0.0.1:8000
   ```

3. **Workflow**:
   - Go to **Documents** tab and upload your academic files (`.pdf`, `.docx`, or `.txt`).
   - Switch to the **Chat** tab to ask questions grounded strictly on the uploaded text.
   - Use the **Study** tab for revision summaries, or **Search** for semantic chunk retrieval.
