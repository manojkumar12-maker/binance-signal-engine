"""Optional Grok AI client. Disabled by default."""
import os
import httpx


class GrokClient:
    def __init__(self):
        self.api_key = os.getenv("GROK_API_KEY", "")
        self.base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")
        self.enabled = bool(self.api_key)
        self.timeout = float(os.getenv("GROK_TIMEOUT", "10"))

    def available(self):
        return self.enabled

    def explain_signal(self, signal: dict) -> str | None:
        if not self.enabled:
            return None
        try:
            prompt = f"Explain this trading signal in one sentence: {signal}"
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": "grok-2-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 80},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    def summarize_market(self, context: dict) -> str | None:
        if not self.enabled:
            return None
        try:
            prompt = f"Summarize market conditions: {context}"
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": "grok-2-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 120},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None