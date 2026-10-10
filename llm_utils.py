import requests
import json
import base64
import os
import re

OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Optimized model map prioritizing speed on CPU
MODEL_MAP = {
    'fast': 'qwen2.5:0.5b',          # ⚡ Fast router model (0.5B)
    'technical': 'qwen2.5:7b',       # ⚡ Technical engine (7B)
    'logical': 'qwen2.5:7b',         # ⚖️ Logical engine (7B)
    'reasoning': 'deepseek-r1:7b',   # 🧠 Deep Reasoning & Logic (7B)
    'vision': 'llava:latest'         # 👁️ Vision OCR & Document Scanner
}
DEFAULT_MODEL = 'qwen2.5:0.5b'

# Fast heuristic keywords for zero-latency instant routing
REASONING_PATTERNS = re.compile(
    r'\b(reason|reasoning|think\s+step\s+by\s+step|step\s*-\s*by\s*-\s*step|prove|proof|logic\s+puzzle|why\s+does|why\s+is|root\s+cause|deduce|derive|solve\s+math|equation)\b',
    re.IGNORECASE
)

VISION_PATTERNS = re.compile(
    r'\b(ocr|scan|scanned|image|picture|photo|transcribe\s+image|extract\s+from\s+image|read\s+this\s+image|receipt\s+scan|document\s+image)\b',
    re.IGNORECASE
)

def classify_intent(prompt: str, has_image: bool = False) -> str:
    """
    Instant zero-latency intent classification.
    Replaces slow 5-10 second LLM classifier roundtrips with instant heuristic pattern matching.
    """
    if has_image:
        return 'vision'

    p_clean = prompt.strip()
    if VISION_PATTERNS.search(p_clean):
        return 'vision'
    if REASONING_PATTERNS.search(p_clean):
        return 'reasoning'

    return 'fast'

def generate_response(prompt, model_name, image_path=None, system_prompt=None, max_context=2048):
    """
    Streams response from Ollama.
    Supports LLaVA vision/OCR when an image is attached.
    Optimized for fast CPU inference with tuned context window and multi-threading.
    """
    # If image provided, force vision model to llava
    actual_model = model_name
    images_payload = []
    
    if image_path and os.path.exists(image_path):
        actual_model = 'llava'
        try:
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                images_payload.append(encoded)
        except Exception as e:
            print(f"Error encoding image for LLaVA: {e}")

    # Dynamically scale context window based on prompt length, capped for CPU efficiency
    prompt_len = len(prompt)
    ctx_size = 4096 if prompt_len > 3000 else max_context

    payload = {
        "model": actual_model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "1h",
        "options": {
            "num_ctx": ctx_size,
            "num_thread": min(os.cpu_count() or 4, 4),
            "temperature": 0.6,
            "top_p": 0.95
        }
    }

    if images_payload:
        payload["images"] = images_payload

    if system_prompt and actual_model != 'llava':
        payload["system"] = system_prompt

    try:
        # Generous timeout: 15s to establish connection, 180s for stream reading
        response = requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=(15, 180))
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                decoded_line = json.loads(line.decode('utf-8'))
                if 'response' in decoded_line:
                    yield decoded_line['response']
    except requests.exceptions.ConnectionError:
        yield "❌ Error: Could not connect to Ollama. Please ensure Ollama is running locally (`ollama serve`)."
    except requests.exceptions.ReadTimeout:
        yield "❌ Error: Ollama inference timed out. Try asking with a shorter document or using the Fast Qwen model."
    except Exception as e:
        yield f"❌ Error generating response: {str(e)}"
