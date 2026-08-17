"""
Telegram Bot Client - Abstraction for Telegram Bot API operations.

Provides a clean interface for:
- sendMessage
- getFile (resolve file_id to file_path)
- download_file (download file from Telegram servers)

Designed to be easily mockable for testing.
"""

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


@dataclass
class TelegramFile:
    """Represents a Telegram file ready for download."""

    file_id: str
    file_path: str
    file_size: int | None = None
    file_unique_id: str | None = None


@dataclass
class TelegramMessage:
    """Result of sending a message."""

    message_id: int
    chat_id: int
    date: int
    text: str | None = None


class TelegramClient:
    """
    Telegram Bot API client.

    Encapsulates all HTTP calls to Telegram Bot API.
    Uses TELEGRAM_BOT_TOKEN from settings for authentication.

    Methods:
        send_message: Send a text message to a chat
        get_file: Get file info (file_path) from file_id
        download_file: Download a file from Telegram servers
    """

    def __init__(self, bot_token: str | None = None):
        self.settings = get_settings()
        self.bot_token = bot_token or self.settings.TELEGRAM_BOT_TOKEN
        self._client: httpx.AsyncClient | None = None
        self._api_base = "https://api.telegram.org/bot"

        if not self.bot_token:
            logger.warning("telegram_client_no_token", message="TELEGRAM_BOT_TOKEN not configured")

    @property
    def base_url(self) -> str:
        """Full base URL for Telegram Bot API."""
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required but not configured")
        return f"{self._api_base}{self.bot_token}"

    async def start(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
            logger.info("telegram_client_started")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("telegram_client_closed")

    async def __aenter__(self) -> "TelegramClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TelegramClient not started. Call start() first or use async context manager.")
        return self._client

    # =========================================================================
    # CORE API METHODS
    # =========================================================================

    async def _post(self, method: str, **kwargs) -> dict[str, Any]:
        """Make a POST request to Telegram Bot API."""
        url = f"{self.base_url}/{method}"
        response = await self.client.post(url, json=kwargs)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(data.get("description", "Unknown Telegram API error"))
        return data.get("result", {})

    async def _get(self, method: str, **kwargs) -> dict[str, Any]:
        """Make a GET request to Telegram Bot API."""
        url = f"{self.base_url}/{method}"
        response = await self.client.get(url, params=kwargs)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(data.get("description", "Unknown Telegram API error"))
        return data.get("result", {})

    # =========================================================================
    # MESSAGE OPERATIONS
    # =========================================================================

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = "HTML",
        disable_web_page_preview: bool = True,
        reply_to_message_id: int | None = None,
        reply_markup: dict | None = None,
    ) -> TelegramMessage:
        """
        Send a text message to a chat.

        Args:
            chat_id: Target chat ID
            text: Message text (supports HTML/Markdown if parse_mode set)
            parse_mode: "HTML" or "Markdown" or None
            disable_web_page_preview: Disable link previews
            reply_to_message_id: Reply to specific message
            reply_markup: Inline keyboard markup dict

        Returns:
            TelegramMessage with message_id, chat_id, date
        """
        logger.info("telegram_send_message", chat_id=chat_id, text_length=len(text))

        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        result = await self._post("sendMessage", **payload)

        return TelegramMessage(
            message_id=result["message_id"],
            chat_id=result["chat"]["id"],
            date=result["date"],
            text=result.get("text"),
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
        cache_time: int = 0,
    ) -> bool:
        """
        Answer a callback query to stop the loading spinner on the client.

        Args:
            callback_query_id: Unique identifier for the query
            text: Text of the notification (0-200 chars)
            show_alert: Show alert instead of notification
            url: URL to open
            cache_time: Cache time in seconds

        Returns:
            True on success
        """
        payload = {
            "callback_query_id": callback_query_id,
        }
        if text is not None:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        if url:
            payload["url"] = url
        if cache_time:
            payload["cache_time"] = cache_time

        result = await self._post("answerCallbackQuery", **payload)
        return result

    async def send_photo(
        self,
        chat_id: int,
        photo: str,  # file_id or URL
        caption: str | None = None,
        parse_mode: str | None = "HTML",
    ) -> TelegramMessage:
        """Send a photo to a chat."""
        payload = {
            "chat_id": chat_id,
            "photo": photo,
        }
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode

        result = await self._post("sendPhoto", **payload)

        return TelegramMessage(
            message_id=result["message_id"],
            chat_id=result["chat"]["id"],
            date=result["date"],
            text=result.get("caption"),
        )

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    async def get_file(self, file_id: str) -> TelegramFile:
        """
        Get file info from Telegram servers.

        Resolves a file_id to a file_path that can be used for download.
        The file_path is valid for 1 hour after retrieval.

        Args:
            file_id: Telegram file identifier

        Returns:
            TelegramFile with file_path, file_size, etc.
        """
        logger.debug("telegram_get_file", file_id=file_id)

        result = await self._get("getFile", file_id=file_id)

        return TelegramFile(
            file_id=result["file_id"],
            file_path=result["file_path"],
            file_size=result.get("file_size"),
            file_unique_id=result.get("file_unique_id"),
        )

    async def download_file(self, file_path: str) -> bytes:
        """
        Download a file from Telegram servers.

        Args:
            file_path: Path returned by get_file (format: "path/to/file.ext")

        Returns:
            Raw file content as bytes
        """
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN required for file download")

        # Telegram file download URL format: https://api.telegram.org/file/bot{token}/{file_path}
        download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"

        logger.debug("telegram_download_file", file_path=file_path)

        response = await self.client.get(download_url, timeout=60.0)
        response.raise_for_status()

        content = response.content
        logger.info("telegram_file_downloaded", file_path=file_path, size=len(content))

        return content

    async def get_file_and_download(self, file_id: str) -> bytes:
        """
        Convenience method: get file info and download in one call.

        Args:
            file_id: Telegram file identifier

        Returns:
            Raw file content as bytes
        """
        file_info = await self.get_file(file_id)
        return await self.download_file(file_info.file_path)


class TelegramAPIError(Exception):
    """Exception raised for Telegram API errors."""

    pass


# =========================================================================
# FACTORY & MOCK FOR TESTING
# =========================================================================


class MockTelegramClient(TelegramClient):
    """
    Mock Telegram client for testing.

    Records calls instead of making real HTTP requests.
    """

    def __init__(self):
        # Don't call parent __init__ to avoid requiring settings
        self.bot_token = "mock-token"
        self._client = None
        self._api_base = "https://api.telegram.org/bot"

        # Call tracking for assertions
        self.calls: list[dict[str, Any]] = []
        self._send_message_results: list[TelegramMessage] = []
        self._get_file_results: dict[str, TelegramFile] = {}
        self._download_results: dict[str, bytes] = {}

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def mock_send_message(self, result: TelegramMessage) -> None:
        """Pre-define result for next send_message call."""
        self._send_message_results.append(result)

    def mock_get_file(self, file_id: str, result: TelegramFile) -> None:
        """Pre-define result for get_file call."""
        self._get_file_results[file_id] = result

    def mock_download(self, file_path: str, content: bytes) -> None:
        """Pre-define result for download_file call."""
        self._download_results[file_path] = content

    async def send_message(self, chat_id: int, text: str, **kwargs) -> TelegramMessage:
        self.calls.append(
            {
                "method": "send_message",
                "chat_id": chat_id,
                "text": text,
                "kwargs": kwargs,
            }
        )

        if self._send_message_results:
            return self._send_message_results.pop(0)

        # Default mock response
        return TelegramMessage(
            message_id=len(self.calls),
            chat_id=chat_id,
            date=0,
            text=text,
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
        cache_time: int = 0,
    ) -> bool:
        self.calls.append(
            {
                "method": "answer_callback_query",
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
                "url": url,
                "cache_time": cache_time,
            }
        )
        return True

    async def get_file(self, file_id: str) -> TelegramFile:
        self.calls.append({"method": "get_file", "file_id": file_id})

        if file_id in self._get_file_results:
            return self._get_file_results[file_id]

        # Default mock
        return TelegramFile(
            file_id=file_id,
            file_path=f"photos/{file_id}.jpg",
            file_size=1024,
        )

    async def download_file(self, file_path: str) -> bytes:
        self.calls.append({"method": "download_file", "file_path": file_path})

        if file_path in self._download_results:
            return self._download_results[file_path]

        # Default mock - return fake image data
        return b"fake-image-data"

    async def get_file_and_download(self, file_id: str) -> bytes:
        self.calls.append({"method": "get_file_and_download", "file_id": file_id})
        file_info = await self.get_file(file_id)
        return await self.download_file(file_info.file_path)


# Factory function
async def create_telegram_client(bot_token: str | None = None) -> TelegramClient:
    """
    Create and start a TelegramClient.

    Args:
        bot_token: Optional override for bot token

    Returns:
        Started TelegramClient instance
    """
    client = TelegramClient(bot_token)
    await client.start()
    return client
