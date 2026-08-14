"""Media Generation Agent
Uses ModelRouter to select between Ollama (local) and NVIDIA (cloud) providers.
"""
import os
import structlog
from typing import Dict, Any, Optional
from pathlib import Path

from app.core.model_router import ModelRouter, create_ollama_provider, create_nvidia_provider

logger = structlog.get_logger()


class MediaGenerationAgent:
    """
    Media generation agent for image, video, and TTS.
    Delegates to appropriate provider based on privacy scope.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "media_generation"
        self.agent_name = "Media Generation Agent"

        # Initialize providers
        ollama_endpoint = config.get("OLLAMA_ENDPOINT", "http://ollama:11434")
        ollama_model = config.get("OLLAMA_MODEL", "qwen4b:latest")
        nvidia_api_key = config.get("NVIDIA_API_KEY", "")
        nvidia_base_url = config.get("NVIDIA_BASE_URL", "https://api.nvidia.com/v1")

        ollama_provider = create_ollama_provider(ollama_endpoint, ollama_model)
        nvidia_provider = create_nvidia_provider(nvidia_api_key, nvidia_base_url)
        self.router = ModelRouter(ollama=ollama_provider, nvidia=nvidia_provider)

        self.capabilities = [
            "generate_image",
            "generate_video",
            "synthesize_speech",
        ]
        self.restrictions = [
            "provider_optional",  # The agent works even if providers fail (will return error)
        ]

    def _validate_output_file(self, output_path: str) -> Dict[str, Any]:
        """Validate that the output file exists, has size > 0, and is a valid format."""
        path = Path(output_path)
        if not path.exists():
            return {"valid": False, "error": f"Output file does not exist: {output_path}"}
        if path.stat().st_size == 0:
            return {"valid": False, "error": f"Output file is empty: {output_path}"}
        
        # Check file extension for valid format
        valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".wav", ".mp3", ".ogg"}
        ext = path.suffix.lower()
        if ext not in valid_extensions:
            return {"valid": False, "error": f"Invalid file format: {ext}"}
        
        return {"valid": True}

    async def generate_image(self, prompt: str, output_path: str, *, privacy_scope: str = "LOCAL_ONLY", **kwargs) -> Dict[str, Any]:
        """Generate an image from a prompt."""
        logger.info("generating_image", prompt=prompt, output_path=output_path, privacy_scope=privacy_scope)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            # For image generation we may need a vision-capable model; we'll call generate with prompt.
            result = await self.router.generate(privacy_scope=privacy_scope, prompt=prompt, **kwargs)
            
            # Check if the provider returned a valid result
            if not result or not result.get("success", False):
                return {
                    "success": False,
                    "error": "provider_not_implemented",
                    "detail": "No image generation provider available or provider returned error",
                    "privacy_scope": privacy_scope
                }
            
            # The provider should have written the file to output_path
            # Validate the output file
            validation = self._validate_output_file(output_path)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "generation_failed",
                    "detail": validation["error"],
                    "privacy_scope": privacy_scope
                }
            
            logger.info("image_generated_successfully", output_path=output_path)
            return {"success": True, "output_path": output_path, "result": result}
        except NotImplementedError:
            return {
                "success": False,
                "error": "provider_not_implemented",
                "detail": "Image generation not implemented for the selected provider",
                "privacy_scope": privacy_scope
            }
        except Exception as e:
            logger.error("image_generation_failed", error=str(e))
            return {"success": False, "error": str(e), "privacy_scope": privacy_scope}

    async def generate_video(self, prompt: str, output_path: str, *, privacy_scope: str = "LOCAL_ONLY", **kwargs) -> Dict[str, Any]:
        """Generate a video from a prompt."""
        logger.info("generating_video", prompt=prompt, output_path=output_path, privacy_scope=privacy_scope)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            result = await self.router.generate(privacy_scope=privacy_scope, prompt=prompt, **kwargs)
            
            if not result or not result.get("success", False):
                return {
                    "success": False,
                    "error": "provider_not_implemented",
                    "detail": "No video generation provider available or provider returned error",
                    "privacy_scope": privacy_scope
                }
            
            validation = self._validate_output_file(output_path)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "generation_failed",
                    "detail": validation["error"],
                    "privacy_scope": privacy_scope
                }
            
            logger.info("video_generated_successfully", output_path=output_path)
            return {"success": True, "output_path": output_path, "result": result}
        except NotImplementedError:
            return {
                "success": False,
                "error": "provider_not_implemented",
                "detail": "Video generation not implemented for the selected provider",
                "privacy_scope": privacy_scope
            }
        except Exception as e:
            logger.error("video_generation_failed", error=str(e))
            return {"success": False, "error": str(e), "privacy_scope": privacy_scope}

    async def synthesize_speech(self, text: str, output_path: str, *, privacy_scope: str = "LOCAL_ONLY", **kwargs) -> Dict[str, Any]:
        """Synthesize speech from text."""
        logger.info("synthesizing_speech", text=text, output_path=output_path, privacy_scope=privacy_scope)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            result = await self.router.generate(privacy_scope=privacy_scope, prompt=text, **kwargs)
            
            if not result or not result.get("success", False):
                return {
                    "success": False,
                    "error": "provider_not_implemented",
                    "detail": "No TTS provider available or provider returned error",
                    "privacy_scope": privacy_scope
                }
            
            validation = self._validate_output_file(output_path)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "generation_failed",
                    "detail": validation["error"],
                    "privacy_scope": privacy_scope
                }
            
            logger.info("tts_synthesized_successfully", output_path=output_path)
            return {"success": True, "output_path": output_path, "result": result}
        except NotImplementedError:
            return {
                "success": False,
                "error": "provider_not_implemented",
                "detail": "TTS synthesis not implemented for the selected provider",
                "privacy_scope": privacy_scope
            }
        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e))
            return {"success": False, "error": str(e), "privacy_scope": privacy_scope}

    async def close(self):
        await self.router.aclose()


# Factory function
def create_media_generation_agent(config: Dict) -> MediaGenerationAgent:
    return MediaGenerationAgent(config)