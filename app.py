"""
SOVARA Offline Industrial AI Assistant - Core Backend Server
Zero external network calls - completely offline, private, and self-contained.
FastAPI replaces the inbuilt Chainlit frontend and serves custom HTML pages:
- /       -> sovara_scroll_animation_login.html (Scroll Animation Landing Page)
- /login  -> login.html (Secure On-Premise Authentication)
- /chat   -> chat.html (Interactive Industrial Chat Workspace)
"""

import os
import json
import time
import uuid
import base64
import urllib.request
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import existing backend modules
from database import (
    init_db, authenticate_user, save_message, get_history,
    create_session, get_user_sessions, get_session, get_session_messages,
    rename_session, delete_session, edit_message, delete_message
)
from llm_utils import (
    classify_intent, generate_response, OLLAMA_API_URL, 
    MODEL_MAP, DEFAULT_MODEL
)
from file_utils import (
    extract_text_from_pdf, extract_text_from_docx, export_to_excel, export_to_pdf,
    process_uploaded_document, is_image_file, render_pdf_to_image
)

# 1. Initialize SQLite Database
init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title="SOVARA Industrial AI Assistant",
    description="Offline on-premise security-first AI assistant backend with LLaVA Vision/OCR and Turbo Qwen/DeepSeek models",
    version="2.1.0"
)

# Enable CORS for local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount public directory for static files / uploads / logo
public_dir = os.path.join(BASE_DIR, "public")
os.makedirs(public_dir, exist_ok=True)
app.mount("/public", StaticFiles(directory=public_dir), name="public")

# In-memory session store (token -> user dict)
SESSIONS = {}

SYSTEM_PROMPT = """You are a highly capable, offline AI assistant designed for industrial use, similar in your helpfulness, reasoning, and capabilities to Claude. You are currently running locally and securely. 
You have perfect memory of the user's provided Document Context and Chat History. Always base your answers on the provided Document Context if applicable. 
If the user asks for a summary or title of the document, use the context. Be concise, highly professional, and extremely accurate."""

# ----------------- Request Models -----------------
class LoginRequest(BaseModel):
    username: str
    password: str

class ChatMessageRequest(BaseModel):
    content: str
    session_id: Optional[str] = None
    doc_context: Optional[str] = ""
    image_path: Optional[str] = None
    model_override: Optional[str] = None
    skip_save_user_message: Optional[bool] = False

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Conversation"
    session_id: Optional[str] = None

class RenameSessionRequest(BaseModel):
    title: str

class ExportRequest(BaseModel):
    text: str

class EditMessageRequest(BaseModel):
    content: str
    remove_response: Optional[bool] = False


# ----------------- Auth Helpers -----------------
def get_current_user(request: Request, authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif "sovara_token" in request.cookies:
        token = request.cookies.get("sovara_token")
        
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    user = SESSIONS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


# ----------------- Frontend HTML Routes -----------------
@app.get("/")
def serve_landing_page():
    """Serves the custom scroll animation landing page as the frontend."""
    landing_path = os.path.join(BASE_DIR, "sovara_scroll_animation_login.html")
    if os.path.exists(landing_path):
        return FileResponse(landing_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="sovara_scroll_animation_login.html not found")

@app.get("/login")
def serve_login_page():
    """Serves the dedicated SOVARA dark-mode login page."""
    login_path = os.path.join(BASE_DIR, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="login.html not found")

@app.get("/chat")
def serve_chat_page():
    """Serves the industrial chat workspace."""
    chat_path = os.path.join(BASE_DIR, "chat.html")
    if os.path.exists(chat_path):
        return FileResponse(chat_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="chat.html not found")


# ----------------- Authentication Endpoints -----------------
@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    """
    Authenticates user with SQLite database.
    Supports default admin/admin123, guest, and auto-registration for new users.
    """
    user_id = authenticate_user(req.username, req.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = f"sovara_{req.username}_{int(time.time())}"
    is_guest = (user_id == "guest" or str(req.username).lower() == "guest")

    user_data = {
        "user_id": user_id,
        "username": req.username,
        "is_guest": is_guest,
        "token": token
    }
    SESSIONS[token] = user_data

    response = JSONResponse({
        "status": "success",
        "user": user_data,
        "token": token
    })
    response.set_cookie(key="sovara_token", value=token, max_age=86400, httponly=False)
    return response

@app.get("/api/auth/verify")
def api_verify(user: dict = Depends(get_current_user)):
    return {"status": "authenticated", "user": user}

@app.post("/api/auth/logout")
def api_logout(request: Request, authorization: Optional[str] = Header(None)):
    token = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
    elif "sovara_token" in request.cookies:
        token = request.cookies.get("sovara_token")
    if token:
        SESSIONS.pop(token, None)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("sovara_token")
    return response


# ----------------- Chat Sessions CRUD Endpoints -----------------
@app.get("/api/chat/sessions")
def api_get_sessions(user: dict = Depends(get_current_user)):
    """Returns all saved sessions for the authenticated user."""
    sessions = get_user_sessions(user["user_id"])
    return {"sessions": sessions}

@app.post("/api/chat/sessions")
def api_create_session(req: CreateSessionRequest, user: dict = Depends(get_current_user)):
    """Explicitly creates a new chat session."""
    sess_id = req.session_id or f"sess_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    title = (req.title.strip() if req.title else "New Conversation")
    sess = create_session(sess_id, user["user_id"], title)
    return {"status": "created", "session": sess}

@app.get("/api/chat/sessions/{session_id}/messages")
def api_get_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    """Returns all messages belonging to the requested session."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_session_messages(session_id)
    return {"session": sess, "messages": messages}

@app.put("/api/chat/sessions/{session_id}/rename")
@app.post("/api/chat/sessions/{session_id}/rename")
def api_rename_session(session_id: str, req: RenameSessionRequest, user: dict = Depends(get_current_user)):
    """Renames an existing saved session."""
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    ok = rename_session(session_id, user["user_id"], new_title)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found or permission denied")
    return {"status": "renamed", "session_id": session_id, "title": new_title}

@app.delete("/api/chat/sessions/{session_id}")
def api_delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """Deletes a saved session and all its messages."""
    ok = delete_session(session_id, user["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found or permission denied")
    return {"status": "deleted", "session_id": session_id}

@app.put("/api/chat/messages/{message_id}")
def api_edit_message(message_id: int, req: EditMessageRequest, user: dict = Depends(get_current_user)):
    """Edits the text of a specific prompt or message in the SQLite database."""
    new_content = req.content.strip()
    if not new_content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    ok, deleted_bot_id = edit_message(message_id, user["user_id"], new_content, remove_response=req.remove_response)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found or permission denied")
    return {
        "status": "updated", 
        "message_id": message_id, 
        "content": new_content,
        "deleted_bot_id": deleted_bot_id
    }

@app.delete("/api/chat/messages/{message_id}")
def api_delete_message(message_id: int, include_response: bool = True, user: dict = Depends(get_current_user)):
    """Deletes a specific prompt and its corresponding response from SQLite database."""
    ok, deleted_bot_id = delete_message(message_id, user["user_id"], include_response=include_response)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found or permission denied")
    return {
        "status": "deleted", 
        "message_id": message_id,
        "deleted_bot_id": deleted_bot_id
    }


# ----------------- Chat Streaming & AI Endpoints -----------------
@app.get("/api/chat/history")
def api_history(user: dict = Depends(get_current_user)):
    """Fetches user chat history from SQLite database (backward compatibility)."""
    raw_history = get_history(user["user_id"])
    formatted = []
    for idx, item in enumerate(raw_history):
        formatted.append({
            "id": f"msg_{idx}_{int(time.time())}",
            "role": item[0],
            "content": item[1],
            "timestamp": item[2] if len(item) > 2 else None
        })
    return {"history": formatted}

@app.post("/api/chat/send")
def api_chat_send(req: ChatMessageRequest, user: dict = Depends(get_current_user)):
    """
    Streams response from local Ollama LLM via Server-Sent Events (SSE).
    Uses high-speed routing:
    - If image attached or scanning requested -> LLaVA Vision/OCR
    - If deep reasoning -> DeepSeek-R1 (7B)
    - Default fast -> Qwen 2.5 (0.5B) Router model
    """
    user_id = user["user_id"]
    content = req.content.strip()

    # Determine or generate session_id
    session_id = req.session_id
    is_new_session = False
    if not session_id:
        session_id = f"sess_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        is_new_session = True
        prompt_preview = content.replace("\n", " ").strip()
        auto_title = (prompt_preview[:32] + "...") if len(prompt_preview) > 32 else prompt_preview
        create_session(session_id, user_id, auto_title or "New Conversation")
    else:
        existing = get_session(session_id)
        if not existing:
            prompt_preview = content.replace("\n", " ").strip()
            auto_title = (prompt_preview[:32] + "...") if len(prompt_preview) > 32 else prompt_preview
            create_session(session_id, user_id, auto_title or "New Conversation")

    # 1. Save user question to database under this session (unless skipped during prompt regeneration)
    user_msg_id = None
    if not req.skip_save_user_message:
        user_msg_id = save_message(user_id, "user", content, session_id=session_id)

    # 2. High-speed intent classification & model routing
    has_image = bool(req.image_path and os.path.exists(req.image_path))
    intent = classify_intent(content, has_image=has_image)

    if req.model_override:
        selected_model = req.model_override
    elif has_image or intent == 'vision':
        selected_model = MODEL_MAP['vision']
    else:
        selected_model = MODEL_MAP.get(intent, DEFAULT_MODEL)

    # 3. Assemble prompt with conversation memory & document context
    full_prompt = ""
    if req.doc_context:
        full_prompt += f"[Document Context]:\n{req.doc_context}\n\n"

    session_msgs = get_session_messages(session_id)
    past_turns = session_msgs[:-1][-6:] if len(session_msgs) > 1 else []
    if past_turns:
        history_str = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in past_turns])
        full_prompt += f"[Previous Conversation]:\n{history_str}\n\n"

    full_prompt += f"User Question: {content}"

    sess_obj = get_session(session_id)
    session_title = sess_obj["title"] if sess_obj else "Conversation"

    def event_generator():
        # First send routing metadata event including model and session
        meta_event = {
            "type": "meta",
            "intent": intent,
            "model": selected_model,
            "session_id": session_id,
            "session_title": session_title,
            "user_message_id": user_msg_id,
            "has_image": has_image,
            "is_new_session": is_new_session
        }
        yield f"data: {json.dumps(meta_event)}\n\n"

        full_bot_response = ""
        try:
            for chunk in generate_response(
                full_prompt, 
                selected_model, 
                image_path=req.image_path, 
                system_prompt=SYSTEM_PROMPT
            ):
                full_bot_response += chunk
                chunk_event = {"type": "token", "chunk": chunk}
                yield f"data: {json.dumps(chunk_event)}\n\n"
        except Exception as e:
            err_msg = f"❌ Error: {str(e)}"
            yield f"data: {json.dumps({'type': 'token', 'chunk': err_msg})}\n\n"
            full_bot_response += f"\n{err_msg}"

        # Save bot response to database under this session
        bot_msg_id = save_message(user_id, "bot", full_bot_response, session_id=session_id, model_name=selected_model)

        # Done event
        done_event = {
            "type": "done", 
            "full_content": full_bot_response, 
            "session_id": session_id,
            "session_title": session_title,
            "bot_message_id": bot_msg_id
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/chat/upload")
async def api_upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """
    Uploads and processes documents (PDF, DOCX, JPG, PNG, WEBP).
    Automatically prepares images and scanned documents for LLaVA Vision/OCR.
    """
    if user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Guest Mode Restriction: File uploads disabled in Guest Mode.")

    upload_dir = os.path.join(BASE_DIR, "public", "files")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Process document using our enhanced pipeline
    proc_result = process_uploaded_document(file_path)

    img_rel_url = None
    if proc_result.get("image_path"):
        img_rel_url = f"/public/files/{os.path.basename(proc_result['image_path'])}"

    return {
        "filename": file.filename,
        "file_path": file_path,
        "image_path": proc_result.get("image_path"),
        "image_url": img_rel_url,
        "is_image": proc_result.get("is_scanned", False),
        "ocr_ready": proc_result.get("ocr_ready", False),
        "extracted_text_preview": proc_result.get("text", "")[:350],
        "full_text": proc_result.get("text", ""),
        "size_bytes": len(content)
    }

@app.post("/api/export/excel")
def api_export_excel(req: ExportRequest):
    """Exports provided text/table data into an Excel spreadsheet."""
    path = export_to_excel(req.text, "sovara_export.xlsx")
    return FileResponse(
        path, 
        filename="sovara_export.xlsx", 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.post("/api/export/pdf")
def api_export_pdf(req: ExportRequest):
    """Exports provided text/table data into a formatted PDF document."""
    path = export_to_pdf(req.text, "sovara_export.pdf")
    return FileResponse(
        path, 
        filename="sovara_export.pdf", 
        media_type="application/pdf"
    )

@app.get("/api/llm/status")
def api_llm_status():
    """Checks Ollama connection status and available local models."""
    ollama_online = False
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                ollama_online = True
    except Exception:
        ollama_online = False

    return {
        "status": "active" if ollama_online else "offline",
        "data_type": "Confidential",
        "ollama_connected": ollama_online,
        "models": MODEL_MAP,
        "available": [
            {"id": "qwen2.5:0.5b", "name": "⚡ Qwen 2.5 (0.5B) - Fast Router", "speed": "Ultra Fast (~1s)"},
            {"id": "qwen2.5:7b", "name": "⚖️ Qwen 2.5 (7B) - Technical/Logical", "speed": "Medium (~5-10s)"},
            {"id": "deepseek-r1:7b", "name": "🧠 DeepSeek R1 (7B) - Reasoning", "speed": "High Reasoning"},
            {"id": "llava:latest", "name": "👁️ LLaVA - Vision & Document OCR", "speed": "Multimodal Scan"}
        ]
    }


# ----------------- Server Launcher -----------------
if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    print("\n" + "=" * 62)
    print("  🚀 SOVARA INDUSTRIAL AI ASSISTANT IS ONLINE")
    print("  ------------------------------------------------------------")
    print("  Landing Page (Scroll Intro): http://localhost:8000/")
    print("  Login Authentication:       http://localhost:8000/login")
    print("  Chat Workspace:             http://localhost:8000/chat")
    print("  Default Models:             Qwen 2.5 (0.5B, 7B) & DeepSeek R1 (7B)")
    print("  Vision & OCR Engine:        LLaVA (Image & Scanned PDF OCR)")
    print("=" * 62 + "\n")

    uvicorn.run(app, host="127.0.0.1", port=8000)
