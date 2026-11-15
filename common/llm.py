"""Small provider-agnostic LLM client shared by Version 1 and Version 2.

Supported providers (selected with the LLM_PROVIDER environment variable):

* ``gemini``  - Google Gemini API through the ``google-genai`` SDK.
* ``openai``  - any OpenAI-compatible ``/chat/completions`` endpoint
                (Groq, OpenRouter, a local Ollama server, ...).
* ``none``    - no LLM. ``generate`` raises ``LLMError``; Version 2 catches this
                and falls back to its deterministic code paths.

The rest of the project only ever calls ``LLMClient.generate``, so swapping the
model/provider never touches game logic.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


class LLMError(RuntimeError):
    """Raised when the LLM is unavailable, misconfigured or keeps failing."""


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str


_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "resource_exhausted", "unavailable", "timeout")


class LLMClient:
    def __init__(
        self,
        provider: str = "none",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        self.provider = (provider or "none").lower()
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._gemini_client = None

    # ------------------------------------------------------------------ setup
    @classmethod
    def from_env(cls) -> "LLMClient":
        """Build a client from environment variables (and a local .env file)."""
        if load_dotenv is not None:
            load_dotenv()
        provider = os.getenv("LLM_PROVIDER", "none").lower()
        if provider == "gemini":
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key or key.startswith("your-"):
                provider = "none"  # not configured -> behave as "no LLM"
            return cls(provider, os.getenv("GEMINI_MODEL", "gemini-flash-latest"), api_key=key)
        if provider == "openai":
            return cls(
                provider,
                os.getenv("OPENAI_MODEL", "llama3.2"),
                api_key=os.getenv("OPENAI_API_KEY") or None,
                base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            )
        return cls("none")

    @property
    def is_configured(self) -> bool:
        return self.provider in ("gemini", "openai")

    @property
    def description(self) -> str:
        if not self.is_configured:
            return "no LLM configured"
        return f"{self.provider}:{self.model}"

    # --------------------------------------------------------------- generate
    def generate(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """Return the model's text reply. Retries transient errors with backoff."""
        if not self.is_configured:
            raise LLMError("No LLM configured (set LLM_PROVIDER and credentials in .env).")

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if self.provider == "gemini":
                    return self._gemini(system, messages, temperature, json_mode, max_tokens)
                return self._openai_compatible(system, messages, temperature, json_mode, max_tokens)
            except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
                last_exc = exc
                text = str(exc).lower()
                transient = any(marker in text for marker in _TRANSIENT_MARKERS)
                if not transient or attempt == self.max_retries - 1:
                    break
                time.sleep(2**attempt)  # 1s, 2s, ...
        raise LLMError(f"{self.description} request failed: {last_exc}") from last_exc

    # -------------------------------------------------------------- providers
    def _gemini(self, system, messages, temperature, json_mode, max_tokens) -> str:
        from google import genai
        from google.genai import types

        if self._gemini_client is None:
            # HttpOptions.timeout is in milliseconds. Without it a stuck request
            # blocks forever and V2's fallbacks never get a chance to run.
            self._gemini_client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),
            )

        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
        ]
        # Newer Gemini models "think" first and thinking tokens count against
        # max_output_tokens, so a tight cap can leave no room for the answer.
        cap = max(max_tokens, 2048) if max_tokens else None
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=cap,
            response_mime_type="application/json" if json_mode else None,
        )
        response = self._gemini_client.models.generate_content(
            model=self.model, contents=contents, config=config
        )
        text = response.text
        if not text:
            reason = None
            try:
                reason = response.candidates[0].finish_reason
            except Exception:  # noqa: BLE001
                pass
            raise LLMError(f"Gemini returned an empty response (finish_reason={reason}).")
        return text.strip()

    def _openai_compatible(self, system, messages, temperature, json_mode, max_tokens) -> str:
        import requests

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/chat/completions"

        if json_mode:
            resp = requests.post(
                url, headers=headers, timeout=self.timeout,
                json={**payload, "response_format": {"type": "json_object"}},
            )
            if resp.status_code == 400:  # some servers/models reject response_format
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        else:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected response format: {resp.text[:300]}") from exc
