"""Model Router for selecting between local (Ollama) and cloud (NVIDIA) providers based on privacy scope."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class ModelProvider:
    """Base class for model providers."""

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def vision(self, image_path: str, prompt: str | None = None, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(ModelProvider):
    """Provider that talks to a local Ollama instance."""

    def __init__(self, endpoint: str, model: str, vision_model: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.vision_model = vision_model or model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.endpoint, timeout=60.0)
        return self._client

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        client = await self._get_client()
        payload = {"model": self.model, "prompt": prompt, "stream": False, **kwargs}
        resp = await client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Ollama returns {"response": "...", ...}
        return {"text": data.get("response", ""), "raw": data}

    async def vision(self, image_path: str, prompt: str | None = None, **kwargs: Any) -> dict[str, Any]:
        # Ollama vision models expect a base64 image; we'll read file and send.
        import base64

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        payload = {
            "model": self.vision_model,
            "prompt": prompt or "",
            "images": [b64],
            "stream": False,
        }
        client = await self._get_client()
        resp = await client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"text": data.get("response", ""), "raw": data}

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()


class NvidiaProvider(ModelProvider):
    """Provider that calls NVIDIA NIM API using OpenAI-compatible Chat Completions format."""

    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._client

    async def generate(self, prompt: str, model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Generate text using NVIDIA NIM Chat Completions API."""
        client = await self._get_client()
        payload = {
            "model": model or "meta/llama-3.1-70b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": False,
        }
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # OpenAI format: choices[0].message.content
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": text, "raw": data}

    async def vision(
        self,
        image_path: str,
        prompt: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate text from image using NVIDIA NIM Vision model (OpenAI-compatible)."""
        import base64

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        client = await self._get_client()
        # Use data URL format for image
        image_url = f"data:image/png;base64,{b64}"
        payload = {
            "model": model or "meta/llama-3.2-90b-vision-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Describe this image."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": False,
        }
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": text, "raw": data}

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()


class ModelRouter:
    """Routes requests to the appropriate provider based on privacy scope."""

    def __init__(self, ollama: OllamaProvider, nvidia: NvidiaProvider) -> None:
        self.ollama = ollama
        self.nvidia = nvidia
        self.logger = logger.bind(component="ModelRouter")

    async def generate(
        self,
        *,
        privacy_scope: str,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.logger.debug("routing generate", privacy_scope=privacy_scope, prompt_len=len(prompt))
        if privacy_scope == "LOCAL_ONLY":
            return await self.ollama.generate(prompt, **kwargs)
        elif privacy_scope == "CLOUD_ALLOWED":
            return await self.nvidia.generate(prompt, model=model, **kwargs)
        else:
            raise ValueError(f"Unknown privacy scope: {privacy_scope}")

    async def vision(
        self,
        *,
        privacy_scope: str,
        image_path: str,
        prompt: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.logger.debug("routing vision", privacy_scope=privacy_scope, image_path=image_path)
        if privacy_scope == "LOCAL_ONLY":
            return await self.ollama.vision(image_path, prompt, **kwargs)
        elif privacy_scope == "CLOUD_ALLOWED":
            return await self.nvidia.vision(image_path, prompt, model=model, **kwargs)
        else:
            raise ValueError(f"Unknown privacy scope: {privacy_scope}")

    async def aclose(self) -> None:
        await self.ollama.aclose()
        await self.nvidia.aclose()


# Factory helpers
def create_ollama_provider(endpoint: str, model: str, vision_model: str | None = None) -> OllamaProvider:
    return OllamaProvider(endpoint=endpoint, model=model, vision_model=vision_model)


def create_nvidia_provider(api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1") -> NvidiaProvider:
    return NvidiaProvider(api_key=api_key, base_url=base_url)


def create_model_router(
    ollama_endpoint: str,
    ollama_model: str,
    ollama_vision_model: str,
    nvidia_api_key: str,
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1",
) -> ModelRouter:
    ollama = create_ollama_provider(ollama_endpoint, ollama_model, ollama_vision_model)
    nvidia = create_nvidia_provider(nvidia_api_key, nvidia_base_url)
    return ModelRouter(ollama=ollama, nvidia=nvidia)
