"""Simple integration test for publishing agent."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path dynamically
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "integration-api"))

from agents.publishing.agent import PublishingAgent

async def test_assisted_publish():
    config = {
        "INTERNAL_API_URL": "http://localhost:8000/api/v1",
        "PLATFORMS": {
            "milanuncios": {},
            "facebook": {}
        }
    }
    agent = PublishingAgent(config)
    result = await agent.assist_publish(listing_id=1, platform="milanuncios")
    assert result["success"] is True
    assert "instructions" in result
    print("Assisted publish test passed")

async def test_auto_publish_no_playwright():
    # Simulate playwright not available by patching the flag
    config = {
        "INTERNAL_API_URL": "http://localhost:8000/api/v1",
        "PLATFORMS": {
            "milanuncios": {"username": "u", "password": "p"}
        }
    }
    agent = PublishingAgent(config)
    # Patch the module-level flag
    with patch('agents.publishing.agent.PLAYWRIGHT_AVAILABLE', False):
        result = await agent.auto_publish(listing_id=1, platform="milanuncios")
        assert result["success"] is False
        assert result["error"] == "playwright_not_installed"
        print("Auto publish without playwright test passed")

async def test_auto_publish_other_platforms():
    config = {"INTERNAL_API_URL": "http://localhost:8000/api/v1", "PLATFORMS": {}}
    agent = PublishingAgent(config)
    for platform in ["facebook", "instagram", "tiktok"]:
        result = await agent.auto_publish(listing_id=1, platform=platform)
        assert result["success"] is False
        assert result["error"] == "publishing_provider_not_implemented"
    print("Other platforms auto publish test passed")

async def main():
    await test_assisted_publish()
    await test_auto_publish_no_playwright()
    await test_auto_publish_other_platforms()
    print("All publishing integration tests passed!")

if __name__ == "__main__":
    asyncio.run(main())