# Industrial Offline Secure AI Assistant (SOVARA)

This project is a completely offline, secure chatbot designed for industrial use. 
Zero cloud data egress. All processing is strictly confined to your local workstation/server.

## Features
- **Frontend Landing:** Interactive scroll-driven landing page (`sovara_scroll_animation_login.html`).
- **Dedicated Authentication:** Secure local login (`/login`) backed by SQLite (`chatbot.db`).
- **Saved Session Management:** Full conversation history by session, with right-click Rename & Delete actions and zero chat loss.
- **File Parsing:** Reads PDFs and DOCX files securely using local libraries.
- **Vision:** Uses `llava` to read and understand Images (PNG/JPG), pdf scan, files scanning etc ...
- **Dynamic Model Routing:** Automatically chooses between Technical (`qwen2.5:7b`), Logical (`qwen2.5:7b`), and Reasoning (`deepseek-r1:7b`) models using a fast router model (`qwen2.5:0.5b`).
- **Zero-Latency Intent Router:** Instant heuristic classifier eliminates the 5-10 second LLM pre-routing delay.
- **Format Export:** Automatically exports LLM output and tables to Excel (`.xlsx`) or PDF (`.pdf`).
- **Voice Input:** Web Speech API integration for hands-free operation.

## Pre-requisites
1. Install [Ollama](https://ollama.com/)
2. Ensure the required models are pulled:
   ```bash
   ollama pull qwen2.5:0.5b
   ollama pull qwen2.5:7b
   ollama pull deepseek-r1:7b
   ollama pull llava
   ```

## How to Run
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the SOVARA Server:
   ```bash
   python app.py
   ```
   *(Or double-click `start.bat` on Windows)*

3. Open your browser:
   - **Landing Page:** http://localhost:8000/
   - **Login Page:**   http://localhost:8000/login
   - **Chat Room:**    http://localhost:8000/chat

4. Log in using default credentials:
   - **Username:** `admin`
   - **Password:** `admin123`
   *(Or click "Continue as Guest")*
