#!/bin/bash
echo "=========================================="
echo "    SOVARA AI Chatbot - Auto Installer"
echo "=========================================="

echo "[1/4] Checking Ollama installation..."
if ! command -v ollama &> /dev/null
then
    echo "[ERROR] Ollama could not be found!"
    echo "Please download and install Ollama from https://ollama.com before running this script."
    exit 1
fi

echo "[2/4] Downloading AI Models..."
ollama pull qwen2.5:3b
ollama pull deepseek-r1:1.5b

echo "[3/4] Installing Python Requirements..."
pip install -r requirements.txt

echo "[4/4] Setting up Databases and Starting SOVARA..."
python -c "import database; database.init_db()"

echo "Starting SOVARA! Opening at http://localhost:8000..."
python app.py
