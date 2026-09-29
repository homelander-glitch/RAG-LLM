// Academic Document Intelligence - Complete Client Script

const API_BASE = localStorage.getItem("academic_rag_api_base") || window.API_BASE_URL || "";
let currentUser = null;
let currentStudyMode = "explain";

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initAuth();
    initNavigation();
    initChat();
    initDocuments();
    initStudy();
    initSearch();
    initSettings();
    initModal();

    checkSession();
});

// --- 1. Theme Management (White & Dark) ---
function initTheme() {
    const toggleBtn = document.getElementById("themeToggleBtn");
    const themeIcon = document.getElementById("themeIcon");
    const savedTheme = localStorage.getItem("academic_rag_theme") || "light";

    setTheme(savedTheme);

    toggleBtn.addEventListener("click", () => {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        setTheme(isDark ? "light" : "dark");
    });
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("academic_rag_theme", theme);
    const themeIcon = document.getElementById("themeIcon");
    if (themeIcon) {
        themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
    }
}

// --- 2. Authentication & Session ---
function getAuthHeader() {
    const token = localStorage.getItem("academic_rag_token");
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

function initAuth() {
    const loginForm = document.getElementById("loginForm");
    const registerForm = document.getElementById("registerForm");
    const showRegisterBtn = document.getElementById("showRegisterBtn");
    const showLoginBtn = document.getElementById("showLoginBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    showRegisterBtn.addEventListener("click", (e) => {
        e.preventDefault();
        loginForm.style.display = "none";
        registerForm.style.display = "flex";
        document.getElementById("loginError").textContent = "";
    });

    showLoginBtn.addEventListener("click", (e) => {
        e.preventDefault();
        registerForm.style.display = "none";
        loginForm.style.display = "flex";
        document.getElementById("registerError").textContent = "";
    });

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("loginEmail").value.trim();
        const password = document.getElementById("loginPassword").value;
        const errElem = document.getElementById("loginError");
        errElem.textContent = "";

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            if (!res.ok) {
                errElem.textContent = data.detail || "Login failed.";
                return;
            }

            localStorage.setItem("academic_rag_token", data.token);
            currentUser = data.user;
            showApp();
        } catch (err) {
            errElem.textContent = `Error: ${err.message}`;
        }
    });

    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("regName").value.trim();
        const email = document.getElementById("regEmail").value.trim();
        const password = document.getElementById("regPassword").value;
        const confirm_password = document.getElementById("regConfirmPassword").value;
        const errElem = document.getElementById("registerError");
        errElem.textContent = "";

        if (password !== confirm_password) {
            errElem.textContent = "Passwords do not match.";
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, email, password, confirm_password })
            });
            const data = await res.json();
            if (!res.ok) {
                errElem.textContent = data.detail || "Registration failed.";
                return;
            }

            localStorage.setItem("academic_rag_token", data.token);
            currentUser = data.user;
            showApp();
        } catch (err) {
            errElem.textContent = `Error: ${err.message}`;
        }
    });

    logoutBtn.addEventListener("click", () => {
        localStorage.removeItem("academic_rag_token");
        currentUser = null;
        showAuth();
    });
}

async function checkSession() {
    const token = localStorage.getItem("academic_rag_token");
    if (!token) {
        showAuth();
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/auth/me`, { headers: getAuthHeader() });
        if (res.ok) {
            currentUser = await res.json();
            showApp();
        } else {
            showAuth();
        }
    } catch (e) {
        showAuth();
    }
}

function showAuth() {
    document.getElementById("authScreen").style.display = "flex";
    document.getElementById("appContainer").style.display = "none";
}

function showApp() {
    document.getElementById("authScreen").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    document.getElementById("userNameDisplay").textContent = currentUser ? currentUser.name : "User";

    loadChatHistory();
    loadDocuments();
    loadSettings();
}

// --- 3. Navigation Tabs ---
function initNavigation() {
    const tabs = document.querySelectorAll(".nav-tab");
    const panes = document.querySelectorAll(".tab-pane");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.getAttribute("data-tab");

            tabs.forEach(t => t.classList.remove("active"));
            panes.forEach(p => p.classList.remove("active"));

            tab.classList.add("active");
            const targetPane = document.getElementById(`tab-${target}`);
            if (targetPane) targetPane.classList.add("active");

            if (target === "documents") loadDocuments();
            if (target === "settings") loadSettings();
        });
    });
}

// --- 4. Chat Functionality ---
function initChat() {
    const form = document.getElementById("chatForm");
    const input = document.getElementById("chatInput");
    const clearBtn = document.getElementById("clearChatBtn");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const question = input.value.trim();
        if (!question) return;

        const welcome = document.getElementById("chatWelcome");
        if (welcome) welcome.remove();

        appendChatUser(question);
        input.value = "";

        const loadingElem = appendChatLoading();

        try {
            const res = await fetch(`${API_BASE}/api/ask`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...getAuthHeader() },
                body: JSON.stringify({ question })
            });

            const data = await res.json();
            loadingElem.remove();

            if (!res.ok) {
                appendChatAi(`Error: ${data.detail || "Query failed."}`, []);
                return;
            }

            appendChatAi(data.answer, data.sources || []);
        } catch (err) {
            loadingElem.remove();
            appendChatAi(`Network error: ${err.message}`, []);
        }
    });

    clearBtn.addEventListener("click", async () => {
        if (!confirm("Clear conversation history?")) return;
        try {
            await fetch(`${API_BASE}/api/history`, { method: "DELETE", headers: getAuthHeader() });
            const container = document.getElementById("chatMessages");
            container.innerHTML = `
                <div id="chatWelcome" class="welcome-box">
                    <div class="welcome-icon">📄</div>
                    <h3>Ask something about your documents</h3>
                    <p>Upload your academic material and ask questions based on its contents.</p>
                </div>
            `;
        } catch (err) {
            alert(`Failed to clear: ${err.message}`);
        }
    });
}

function appendChatUser(text) {
    const container = document.getElementById("chatMessages");
    const item = document.createElement("div");
    item.className = "msg-item user";
    item.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

function appendChatLoading() {
    const container = document.getElementById("chatMessages");
    const item = document.createElement("div");
    item.className = "msg-item ai";
    item.innerHTML = `
        <div class="ai-card">
            <div class="section-label">System</div>
            <div class="answer-body">Retrieving relevant chunks & generating grounded answer...</div>
        </div>
    `;
    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
    return item;
}

function appendChatAi(answer, sources) {
    const container = document.getElementById("chatMessages");
    const item = document.createElement("div");
    item.className = "msg-item ai";

    let sourcesHtml = "";
    if (sources && sources.length > 0) {
        const sourceCards = sources.map(s => `
            <div class="source-item">
                <div class="source-header">
                    <span>📄 ${escapeHtml(s.filename || "Document")}</span>
                    <span>Page ${s.page || 1}</span>
                </div>
                ${s.snippet ? `<div class="source-snippet">"${escapeHtml(s.snippet)}"</div>` : ''}
            </div>
        `).join("");

        sourcesHtml = `
            <div class="sources-container">
                <div class="section-label">SOURCES (${sources.length})</div>
                ${sourceCards}
            </div>
        `;
    }

    item.innerHTML = `
        <div class="ai-card">
            <div>
                <div class="section-label">ANSWER</div>
                <div class="answer-body">${escapeHtml(answer)}</div>
            </div>
            ${sourcesHtml}
        </div>
    `;

    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

async function loadChatHistory() {
    try {
        const res = await fetch(`${API_BASE}/api/history`, { headers: getAuthHeader() });
        const history = await res.json();
        if (Array.isArray(history) && history.length > 0) {
            const welcome = document.getElementById("chatWelcome");
            if (welcome) welcome.remove();

            history.forEach(item => {
                appendChatUser(item.question);
                let parsedSources = [];
                try {
                    parsedSources = typeof item.sources === 'string' ? JSON.parse(item.sources) : item.sources;
                } catch(e) {}
                appendChatAi(item.answer, parsedSources);
            });
        }
    } catch(e) {}
}

function suggestChat(q) {
    const input = document.getElementById("chatInput");
    if (input) {
        input.value = q;
        input.focus();
    }
}

// --- 5. Documents Tab ---
function initDocuments() {
    const dropZone = document.getElementById("docDropZone");
    const fileInput = document.getElementById("docFileInput");

    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            uploadDoc(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            uploadDoc(e.target.files[0]);
        }
    });
}

async function uploadDoc(file) {
    const statusElem = document.getElementById("docUploadStatus");
    const fileInput = document.getElementById("docFileInput");

    const validExts = [".pdf", ".docx", ".txt"];
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!validExts.includes(ext)) {
        setDocStatus("Only PDF, DOCX, and TXT files are accepted.", "error");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setDocStatus(`Processing & embedding "${file.name}"...`, "loading");

    try {
        const res = await fetch(`${API_BASE}/api/upload`, {
            method: "POST",
            headers: getAuthHeader(),
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            setDocStatus(data.detail || "Upload failed.", "error");
            return;
        }

        setDocStatus(`Successfully indexed "${file.name}"`, "success");
        fileInput.value = "";
        loadDocuments();
    } catch (err) {
        setDocStatus(`Upload error: ${err.message}`, "error");
    }
}

function setDocStatus(msg, type) {
    const statusElem = document.getElementById("docUploadStatus");
    if (!statusElem) return;
    statusElem.textContent = msg;
    statusElem.className = `upload-status-msg ${type}`;
    if (type === "success") {
        setTimeout(() => {
            if (statusElem.textContent === msg) {
                statusElem.textContent = "";
                statusElem.className = "upload-status-msg";
            }
        }, 4000);
    }
}

async function loadDocuments() {
    const tbody = document.getElementById("documentsTableBody");
    try {
        const res = await fetch(`${API_BASE}/api/documents`, { headers: getAuthHeader() });
        const docs = await res.json();

        if (!Array.isArray(docs) || docs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No documents uploaded yet.</td></tr>';
            return;
        }

        tbody.innerHTML = docs.map(doc => {
            const sizeKB = Math.round((doc.file_size || 0) / 1024);
            const ext = doc.filename.split('.').pop().toUpperCase();
            const dateStr = doc.uploaded_at ? doc.uploaded_at.split(' ')[0] : '-';
            return `
                <tr>
                    <td><strong>${escapeHtml(doc.filename)}</strong></td>
                    <td><span class="badge">${ext}</span></td>
                    <td>${doc.total_pages || 1}</td>
                    <td>${doc.chunk_count || 0}</td>
                    <td>${sizeKB} KB</td>
                    <td>${dateStr}</td>
                    <td>
                        <button class="btn btn-outline btn-sm" onclick="openDocPreview('${doc.doc_id}')">Preview</button>
                        <button class="btn btn-outline btn-sm" style="color:#EF4444;" onclick="deleteDoc('${doc.doc_id}', '${escapeHtml(doc.filename)}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#EF4444;">Error: ${err.message}</td></tr>`;
    }
}

async function deleteDoc(docId, filename) {
    if (!confirm(`Are you sure you want to delete "${filename}" and its vector embeddings?`)) return;

    try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}`, { method: "DELETE", headers: getAuthHeader() });
        if (res.ok) {
            loadDocuments();
        } else {
            const err = await res.json();
            alert(`Delete failed: ${err.detail || "Error"}`);
        }
    } catch (err) {
        alert(`Delete error: ${err.message}`);
    }
}

// --- 6. Study Mode Tab ---
function initStudy() {
    const buttons = document.querySelectorAll(".study-btn");
    const form = document.getElementById("studyForm");
    const input = document.getElementById("studyTopicInput");
    const output = document.getElementById("studyOutput");

    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentStudyMode = btn.getAttribute("data-mode");
        });
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const topic = input.value.trim();

        output.innerHTML = '<div class="text-center text-muted">Analyzing document vectors and generating study notes...</div>';

        try {
            const res = await fetch(`${API_BASE}/api/study`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...getAuthHeader() },
                body: JSON.stringify({ mode: currentStudyMode, topic })
            });

            const data = await res.json();
            if (!res.ok) {
                output.innerHTML = `<div style="color:#EF4444;">Error: ${data.detail || "Generation failed."}</div>`;
                return;
            }

            output.textContent = data.answer;
        } catch (err) {
            output.innerHTML = `<div style="color:#EF4444;">Error: ${err.message}</div>`;
        }
    });
}

// --- 7. Search Tab (Semantic Search) ---
function initSearch() {
    const form = document.getElementById("searchForm");
    const input = document.getElementById("searchInput");
    const container = document.getElementById("searchResults");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if (!query) return;

        container.innerHTML = '<div class="text-center text-muted">Searching semantic vector index...</div>';

        try {
            const res = await fetch(`${API_BASE}/api/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...getAuthHeader() },
                body: JSON.stringify({ query, top_k: 4 })
            });

            const data = await res.json();
            if (!res.ok) {
                container.innerHTML = `<div style="color:#EF4444;">Error: ${data.detail || "Search failed."}</div>`;
                return;
            }

            const results = data.results || [];
            if (results.length === 0) {
                container.innerHTML = '<div class="text-center text-muted">No relevant passages found in your documents.</div>';
                return;
            }

            container.innerHTML = results.map((r, idx) => {
                const meta = r.metadata || {};
                const distanceStr = r.distance !== null ? `Cosine Dist: ${r.distance.toFixed(3)}` : '';
                return `
                    <div class="search-result-card">
                        <div class="search-result-header">
                            <span>📄 ${escapeHtml(meta.filename || "Document")} — Page ${meta.page || 1}</span>
                            <span class="search-result-distance">${distanceStr}</span>
                        </div>
                        <div class="search-result-snippet">"${escapeHtml(r.text)}"</div>
                    </div>
                `;
            }).join("");

        } catch (err) {
            container.innerHTML = `<div style="color:#EF4444;">Search error: ${err.message}</div>`;
        }
    });
}

// --- 8. Settings Tab ---
function initSettings() {
    const reindexBtn = document.getElementById("reindexBtn");
    const statusElem = document.getElementById("reindexStatus");

    reindexBtn.addEventListener("click", async () => {
        statusElem.textContent = "Reindexing ChromaDB from uploads...";
        statusElem.className = "upload-status-msg loading";

        try {
            const res = await fetch(`${API_BASE}/api/reindex`, { method: "POST", headers: getAuthHeader() });
            const data = await res.json();
            if (res.ok) {
                statusElem.textContent = `Reindex complete: ${data.documents_reindexed} documents (${data.total_chunks_indexed} chunks).`;
                statusElem.className = "upload-status-msg success";
                loadSettings();
            } else {
                statusElem.textContent = data.detail || "Reindex failed.";
                statusElem.className = "upload-status-msg error";
            }
        } catch (err) {
            statusElem.textContent = `Error: ${err.message}`;
            statusElem.className = "upload-status-msg error";
        }
    });
}

async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`, { headers: getAuthHeader() });
        if (!res.ok) return;
        const cfg = await res.json();

        document.getElementById("cfg-endpoint").textContent = cfg.ollama_endpoint || "-";
        document.getElementById("cfg-model").textContent = cfg.ollama_model || "-";
        document.getElementById("cfg-embedding").textContent = cfg.embedding_model || "-";
        document.getElementById("cfg-vectordb").textContent = cfg.vector_db || "-";
        document.getElementById("cfg-database").textContent = cfg.database || "-";
        document.getElementById("cfg-doc-count").textContent = `${cfg.user_documents_count} documents (${cfg.total_vectors_in_store} total vectors)`;
        document.getElementById("cfg-mode").textContent = cfg.processing_mode || "Local Processing Enabled";
        
        const statusModelElem = document.getElementById("statusModelName");
        if (statusModelElem && cfg.ollama_model) {
            statusModelElem.textContent = cfg.ollama_model;
        }
    } catch(e) {}
}

// --- 9. Document Preview Modal ---
function initModal() {
    const modal = document.getElementById("docPreviewModal");
    const closeBtn = document.getElementById("closeModalBtn");

    closeBtn.addEventListener("click", () => {
        modal.style.display = "none";
    });

    modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.style.display = "none";
    });
}

async function openDocPreview(docId) {
    const modal = document.getElementById("docPreviewModal");
    const title = document.getElementById("modalDocTitle");
    const meta = document.getElementById("modalDocMeta");
    const text = document.getElementById("modalDocText");

    title.textContent = "Loading preview...";
    meta.innerHTML = "";
    text.textContent = "Extracting text passages...";
    modal.style.display = "flex";

    try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}/preview`, { headers: getAuthHeader() });
        const data = await res.json();

        if (!res.ok) {
            text.textContent = data.detail || "Failed to load preview.";
            return;
        }

        const doc = data.document;
        const sizeKB = Math.round((doc.file_size || 0) / 1024);
        title.textContent = `Document Preview: ${doc.filename}`;
        meta.innerHTML = `
            <span><strong>Pages:</strong> ${doc.total_pages || 1}</span>
            <span><strong>Chunks:</strong> ${doc.chunk_count || 0}</span>
            <span><strong>Size:</strong> ${sizeKB} KB</span>
            <span><strong>Uploaded:</strong> ${doc.uploaded_at || '-'}</span>
        `;
        text.textContent = data.preview_text || "No readable text extracted.";
    } catch (err) {
        text.textContent = `Preview error: ${err.message}`;
    }
}

// Helper
function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
