"""Model Router for selecting between local (Ollama) and cloud (NVIDIA) providers based on privacy scope."""
from __future__ import annotations

import httpx
import structlog
from typing import Any, Dict, Optional

logger = structlog.get_logger()


class ModelProvider:
    """Base class for model providers."""
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    async def vision(self, image_path: str, prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(ModelProvider):
    """Provider that talks to a local Ollama instance."""
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.endpoint, timeout=60.0)
        return self._client

    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        client = await self._get_client()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **kwargs
        }
        resp = await client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Ollama returns {"response": "...", ...}
        return {"text": data.get("response", ""), "raw": data}

    async def vision(self, image_path: str, prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        # Ollama vision models expect a base64 image; we'll read file and send.
        import base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        payload = {
            "model": self.model,
            "prompt": prompt or "",
            "images": [b64],
            "stream": False,
        }
        client = await self._get_client()
        resp = await client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"text": data.get("response", ""), "raw": data}

    async def aclose(self):
        if self._client:
            await self._client.aclose()


class NvidiaProvider(ModelProvider):
    """Provider that calls NVIDIA API (placeholder)."""
    def __init__(self, api_key: str, base_url: str = "https://api.nvidia.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._client

    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        # Placeholder endpoint; actual NVIDIA API may differ.
        client = await self._get_client()
        payload = {
            "model": "nemotron-3-super",  # example; should be configurable
            "prompt": prompt,
            **kwargs
        }
        resp = await client.post("/infer", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"text": data.get("generated_text", ""), "raw": data}

    async def vision(self, image_path: str, prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        # Placeholder: assume endpoint accepts image upload.
        import base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        client = await self._get_client()
        payload = {
            "model": "nemotron-vision",
            "prompt": prompt or "",
            "image": b64,
            **kwargs
        }
        resp = await client.post("/vision/infer", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"text": data.get("generated_text", ""), "raw": data}

    async def aclose(self):
        if self._client:
            await self._client.aclose()


class ModelRouter:
    """Routes requests to the appropriate provider based on privacy scope."""
    def __init__(self, ollama: OllamaProvider, nvidia: NvidiaProvider):
        self.ollama = ollama
        self.nvidia = nvidia
        self.logger = logger.bind(component="ModelRouter")

    async def generate(self, *, privacy_scope: str, prompt: str, **kwargs) -> Dict[str, Any]:
        self.logger.debug("routing generate", privacy_scope=privacy_scope, prompt_len=len(prompt))
        if privacy_scope == "LOCAL_ONLY":
            return await self.ollama.generate(prompt, **kwargs)
        elif privacy_scope == "CLOUD_ALLOWED":
            return await self.nvidia.generate(prompt, **kwargs)
        else:
            raise ValueError(f"Unknown privacy scope: {privacy_scope}")

    async def vision(self, *, privacy_scope: str, image_path: str, prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        self.logger.debug("routing vision", privacy_scope=privacy_scope, image_path=image_path)
        if privacy_scope == "LOCAL_ONLY":
            return await self.ollama.vision(image_path, prompt, **kwargs)
        elif privacy_scope == "CLOUD_ALLOWED":
            return await self.nvidia.vision(image_path, prompt, **kwargs)
        else:
            raise ValueError(f"Unknown privacy scope: {privacy_scope}")

    async def aclose(self):
        await self.ollama.aclose()
        await self.nvidia.aclose()


# Factory helpers
def create_ollama_provider(endpoint: str, model: str) -> OllamaProvider:
    return OllamaProvider(endpoint=endpoint, model=model)


def create_nvidia_provider(api_key: str, base_url: str = "https://api.nvidia.com/v1") -> NvidiaProvider:
    return NvidiaProvider(api_key=api_key, base_url=base_url)


def create_model_router(ollama_endpoint: str, ollama_model: str, nvidia_api_key: str, nvidia_base_url: str = "https://api.nvidia.com/v1") -> ModelRouter:
    ollama = create_ollama_provider(ollama_endpoint, ollama_model)
    nvidia = create_nvidia_provider(nvidia_api_key, nvidia_base_url)
    return ModelRouter(ollama=ollama, nvidia=nvidia)