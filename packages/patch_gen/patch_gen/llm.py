"""Optional local-LLM client with graceful degradation.

Candidate generation works in two modes:

* **LLM mode** — when a local Ollama server is reachable (e.g. the user's own
  machine), the generator asks the model for a richer root-cause narrative.
* **Offline/template mode** — when the LLM is unreachable (no Ollama, or a VPN
  blocks ``localhost:11434``, or a cold-load timeout), generation falls back to
  deterministic templates. NOTHING is fabricated by the model in this mode.

The client never raises on a transport error: :meth:`generate` returns ``None``
so callers cleanly fall back. :func:`probe` reports availability for bootup /
health checks so the app can tell the user up front whether the LLM is live.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("patch_gen.llm")

DEFAULT_URL = os.environ.get("CAREERFORGE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("CAREERFORGE_PATCH_LLM_MODEL", "qwen2.5:7b")


class LocalLLM:
    """Thin, failure-tolerant wrapper over Ollama's ``/api/generate``."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.name = f"ollama:{model}"

    async def available(self) -> bool:
        """Return True if the Ollama server responds to ``/api/tags`` quickly."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                models = {m.get("name", "") for m in resp.json().get("models", [])}
                # Accept an exact match or the same repo (":latest" etc.).
                base = self.model.split(":", 1)[0]
                return any(m == self.model or m.split(":", 1)[0] == base for m in models)
        except Exception as exc:
            logger.debug("LLM availability probe failed: %s", exc)
            return False

    async def generate(self, prompt: str, *, num_predict: int = 512) -> str | None:
        """Return the model's completion, or ``None`` on any failure.

        Uses a low temperature (deterministic-leaning) since patch reasoning
        should be conservative, not creative.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": num_predict},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                text = resp.json().get("response")
                return str(text) if text else None
        except Exception as exc:
            logger.info("LLM generate unavailable (%s); using template fallback.", type(exc).__name__)
            return None


async def probe(base_url: str = DEFAULT_URL, model: str = DEFAULT_MODEL) -> dict[str, object]:
    """Bootup/health probe: is the patch-generation LLM reachable?

    Returns ``{"available": bool, "model": str, "url": str, "mode": str}`` where
    ``mode`` is ``"llm"`` when reachable, else ``"template"``.
    """
    llm = LocalLLM(base_url, model)
    ok = await llm.available()
    return {
        "available": ok,
        "model": model,
        "url": base_url,
        "mode": "llm" if ok else "template",
    }
