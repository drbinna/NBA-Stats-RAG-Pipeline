import requests
from backend.config import OLLAMA_HOST


def ollama_embed(model: str, text: str, timeout: int = 180):
    r = requests.post(f"{OLLAMA_HOST}/api/embeddings", json={"model": model, "prompt": text}, timeout=timeout)
    r.raise_for_status()
    return r.json()["embedding"]


def ollama_generate(model: str, prompt: str, timeout: int = 300):
    r = requests.post(f"{OLLAMA_HOST}/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    r.raise_for_status()
    return r.json()["response"]


def ollama_chat(model: str, prompt: str, timeout: int = 10):
    """
    Optimized chat using Ollama chat API with fast timeout and minimal token generation.
    """
    r = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "num_predict": 50,  # Reduced from 100 for faster responses
                "temperature": 0.1,  # Slight temperature for naturalness but still deterministic
                "top_p": 0.9,  # Nucleus sampling for faster generation
            }
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()
