#!/bin/bash

echo "🚀 Starting automatic model download for Offline Industrial Chatbot..."
echo "Please make sure the Ollama App is running in the background."
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null
then
    echo "❌ Ollama is not installed!"
    echo "Please download and install it from https://ollama.com/download first, open the app, and then run this script again."
    exit 1
fi

echo "✅ Ollama found. Proceeding to download models. This may take some time depending on your internet speed..."
echo ""

echo "----------------------------------------"
echo "📥 1/4 Downloading Router Model (qwen2.5:0.5b)..."
ollama pull qwen2.5:0.5b

echo "----------------------------------------"
echo "📥 2/4 Downloading Technical/Logical Model (qwen3.8)..."
ollama pull qwen3.8

echo "----------------------------------------"
echo "📥 3/4 Downloading Reasoning Model (deepseek-r1:7b)..."
ollama pull deepseek-r1:7b

echo "----------------------------------------"
echo "📥 4/4 Downloading Vision Model (llava) for Images..."
ollama pull llava

echo "----------------------------------------"
echo "🎉 All models have been downloaded successfully!"
echo "You are ready to use the offline chatbot."
