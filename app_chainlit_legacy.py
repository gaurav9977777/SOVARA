import chainlit as cl
from database import init_db, authenticate_user, save_message, get_history
from llm_utils import classify_intent, generate_response
from file_utils import extract_text_from_pdf, extract_text_from_docx, export_to_excel, export_to_pdf
import os

# 1. Initialize Database
init_db()

import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from local_storage import LocalStorageClient

# Enable Native UI Sidebar History
cl_data._data_layer = SQLAlchemyDataLayer(
    conninfo="sqlite+aiosqlite:///chainlit_history.db",
    storage_provider=LocalStorageClient()
)

# 2. Model Configuration 
MODEL_MAP = {
    'technical': 'qwen2.5:3b',
    'logical': 'qwen2.5:3b',
    'reasoning': 'deepseek-r1:1.5b' # Ultra-fast offline reasoning model
}

SYSTEM_PROMPT = """You are a highly capable, offline AI assistant designed for industrial use, similar in your helpfulness, reasoning, and capabilities to Claude. You are currently running locally and securely. 
You have perfect memory of the user's provided Document Context and Chat History. Always base your answers on the provided Document Context if applicable. 
If the user asks for a summary or title of the document, use the context. Be concise, highly professional, and extremely accurate."""

# 3. Setup Authentication (Login Form)
@cl.password_auth_callback
def auth_callback(username, password):
    user_id = authenticate_user(username, password)
    if user_id:
        # User valid, create a session
        return cl.User(identifier=username, metadata={"id": user_id})
    return None

@cl.on_chat_start
async def on_chat_start():
    user = cl.user_session.get("user")
    
    # Initialize session memory
    cl.user_session.set("doc_context", "")
    cl.user_session.set("chat_history", [])

@cl.on_chat_resume
async def on_chat_resume(thread):
    # Initialize session memory
    cl.user_session.set("doc_context", "")
    
    # Reconstruct history from the loaded thread steps
    chat_history = []
    if "steps" in thread:
        for step in thread["steps"]:
            if step["type"] == "user_message":
                chat_history.append({"role": "user", "content": step["output"]})
            elif step["type"] == "assistant_message" or step["type"] == "run" or step["type"] == "message":
                if step.get("author") != "Router" and step.get("author") != "System":
                    role = "user" if step["type"] == "user_message" else "bot"
                    chat_history.append({"role": role, "content": step["output"]})
                    
    cl.user_session.set("chat_history", chat_history)

@cl.on_chat_end
async def on_chat_end():
    user = cl.user_session.get("user")
    if user and user.metadata.get("id") == "guest":
        try:
            thread_id = cl.context.session.thread_id
            await cl_data._data_layer.delete_thread(thread_id)
        except Exception as e:
            pass

@cl.on_message
async def main(message: cl.Message):
    user = cl.user_session.get("user")
    user_id = user.metadata["id"] if user and "id" in user.metadata else 1
    
    # Load session memory
    doc_context = cl.user_session.get("doc_context", "")
    chat_history = cl.user_session.get("chat_history", [])
    
    # Save user message to history DB
    save_message(user_id, "user", message.content)
    
    # Process Attachments (PDF, DOCX, Images)
    image_path = None
    
    if message.elements:
        if user_id == "guest":
            await cl.Message(content="⚠️ **Guest Mode Restriction:** File and image uploads are not supported in Guest Mode. Please login to use this feature.").send()
            return
            
        for element in message.elements:
            if element.mime.startswith("image/"):
                image_path = element.path
            elif element.name.lower().endswith(".pdf") or element.mime == "application/pdf":
                extracted = extract_text_from_pdf(element.path)
                if not extracted.strip():
                    pass # OCR not yet fully integrated or just ignore
                else:
                    doc_context += extracted + "\n"
            elif element.name.lower().endswith(".docx"):
                doc_context += extract_text_from_docx(element.path) + "\n"
                
    cl.user_session.set("doc_context", doc_context)
                
    # Compile prompt with memory
    full_prompt = ""
    if doc_context:
        full_prompt += f"[Document Context]:\n{doc_context}\n\n"
        
    if chat_history:
        history_str = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history[-6:]])
        full_prompt += f"[Previous Conversation]:\n{history_str}\n\n"
        
    full_prompt += f"User Question: {message.content}"
    chat_history.append({"role": "user", "content": message.content})
        
    msg_lower = message.content.lower()
    export_excel = "export to excel" in msg_lower or "export as excel" in msg_lower
    export_pdf = "export to pdf" in msg_lower or "export as pdf" in msg_lower

    # Smart Routing Classification
    intent = classify_intent(message.content)
    selected_model = MODEL_MAP.get(intent, 'qwen2.5:7b')
    
    # Streaming Response
    msg = cl.Message(content="")
    await msg.send()
    
    full_response = ""
    for chunk in generate_response(full_prompt, selected_model, image_path, system_prompt=SYSTEM_PROMPT):
        full_response += chunk
        await msg.stream_token(chunk)
    
    await msg.update()
    
    # Update session memory
    chat_history.append({"role": "bot", "content": full_response})
    cl.user_session.set("chat_history", chat_history)
    
    # Save bot message to DB
    save_message(user_id, "bot", full_response)
    
    # Process Output Exports
    if export_excel:
        excel_path = export_to_excel(full_response)
        await cl.Message(
            content="Here is your requested Excel file:", 
            elements=[cl.File(name="export.xlsx", path=excel_path, display="inline")]
        ).send()
        
    if export_pdf:
        pdf_path = export_to_pdf(full_response)
        await cl.Message(
            content="Here is your requested PDF file:", 
            elements=[cl.File(name="export.pdf", path=pdf_path, display="inline")]
        ).send()
