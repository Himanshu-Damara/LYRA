"""
grok_client.py — Grok API integration for question answering.
API key loaded from .env file, never hardcoded.
"""

import os
import json
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class GrokClient:
    """
    Client for Grok / Groq LLM API for fast question-answering.
    Supports both Groq keys (gsk_...) and xAI keys (xai-...).
    """

    def __init__(self, backend: Optional[str] = None):
        self.backend = backend
        self._load_key()

    def _load_key(self):
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        
        # Read the QA_BACKEND or default to ollama
        qa_backend = os.getenv("QA_BACKEND", "ollama").strip().lower()
        current_backend = self.backend if self.backend else qa_backend

        if current_backend == "ollama":
            self.api_url = "http://localhost:11434/v1/chat/completions"
            self.model = "qwen3:8b"
            self.api_key = "local"
            self.enabled = True
        else:
            self.api_key = os.getenv("GROK_API_KEY", "").strip()
            self.enabled = bool(self.api_key) and self.api_key != "your_api_key_here"

            if self.api_key.startswith("gsk_"):
                self.api_url = "https://api.groq.com/openai/v1/chat/completions"
                self.model = "llama-3.3-70b-versatile"
            else:
                self.api_url = "https://api.x.ai/v1/chat/completions"
                self.model = "grok-2"

    def ask(self, question: str, system_prompt: Optional[str] = None) -> str:
        """
        Sends a question to the LLM API and returns the text response.
        """
        if not self.enabled:
            self._load_key()

        if not self.enabled:
            return (
                "I don't have an API key configured for answering questions. "
                "Please set GROK_API_KEY in your .env file to enable Q&A."
            )

        if system_prompt is None:
            system_prompt = (
                "You are LYRA, an AI phone assistant. Answer questions concisely and helpfully. "
                "Keep answers under 80 words."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            return f"Sorry, I couldn't reach the AI API: {e}"
        except (KeyError, IndexError):
            return "Sorry, I received an unexpected response from the AI API."


# Singleton instance
grok = GrokClient()

