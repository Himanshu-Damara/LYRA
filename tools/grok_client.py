import os
import json
import requests
from urllib.parse import urljoin

class GrokClient:
    """Simple wrapper for Grok API calls.

    The API key is expected in a .env file at the project root under the
    variable ``GROK_API_KEY``. The client loads the key on initialization.
    """

    BASE_URL = "https://api.grok.ai/v1/"

    def __init__(self, env_path: str = None):
        env_path = env_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
        self.api_key = self._load_api_key(env_path)
        if not self.api_key:
            raise ValueError("GROK_API_KEY not found in .env file")

    def _load_api_key(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GROK_API_KEY"):
                    return line.split("=", 1)[1].strip()
        return ""

    def query(self, prompt: str, model: str = "grok-beta") -> str:
        """Send a prompt to Grok and return the text response.

        Parameters
        ----------
        prompt: str
            The user query.
        model: str, optional
            The model identifier – defaults to ``grok-beta``.
        """
        endpoint = urljoin(self.BASE_URL, "completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": 256,
            "temperature": 0.7,
        }
        response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("text", "").strip()
