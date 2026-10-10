@echo off
echo ==========================================
echo     SOVARA AI Chatbot - Auto Installer
echo ==========================================

echo [1/4] Checking Ollama installation...
where ollama >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Ollama could not be found!
    echo Please download and install Ollama from https://ollama.com before running this script.
    pause
    exit /b 1
)

echo [2/4] Downloading AI Models (this may take a few minutes)...
ollama pull qwen2.5:3b
ollama pull deepseek-r1:1.5b

echo [3/4] Installing Python Requirements...
pip install -r requirements.txt

echo [4/4] Setting up Databases and Starting SOVARA...
python -c "import database; database.init_db()"

echo Starting SOVARA! Opening in browser...
python app.py
pause
