"""
Internal API Client - Centralized HTTP client for service-to-service communication.
Provides authentication, retries, timeouts, correlation IDs, and error handling.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class InternalAPIError(Exception):
    """Base exception for internal API errors."""

    def __init__(
        self, message: str, status_code: int | None = None, response: dict | None = None
    ):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class InternalAPIClient:
    """
    Centralized HTTP client for internal service-to-service communication.

    Features:
    - Automatic authentication with agent API key
    - Configurable timeouts
    - Retry logic for idempotent operations
    - Correlation ID propagation
    - Structured logging
    - Proper error handling with typed exceptions
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        agent_name: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_on_status: tuple = (429, 500, 502, 503, 504),
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.agent_name = agent_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_on_status = retry_on_status
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Agent-Name": self.agent_name,
                    "Content-Type": "application/json",
                },
            )
            logger.info(
                "internal_api_client_started",
                agent=self.agent_name,
                base_url=self.base_url,
            )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("internal_api_client_closed", agent=self.agent_name)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "InternalAPIClient not started. Use async context manager or call start() first."
            )
        return self._client

    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for request tracing."""
        return str(uuid.uuid4())

    def _should_retry(self, method: str, response: httpx.Response) -> bool:
        """Determine if a request should be retried based on method and response status.

        Only retry idempotent methods (GET, PUT, DELETE, HEAD, OPTIONS) to avoid
        duplicate resource creation on POST/PATCH retries.
        """
        idempotent_methods = {"GET", "PUT", "DELETE", "HEAD", "OPTIONS"}
        return (
            method.upper() in idempotent_methods
            and response.status_code in self.retry_on_status
        )

    async def _request_with_retry(
        self, method: str, path: str, correlation_id: str, **kwargs
    ) -> httpx.Response:
        """Execute HTTP request with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            headers = kwargs.pop("headers", {})
            headers["X-Correlation-ID"] = correlation_id

            try:
                response = await self.client.request(
                    method=method, url=path, headers=headers, **kwargs
                )

                # Log request
                logger.debug(
                    "internal_api_request",
                    agent=self.agent_name,
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    correlation_id=correlation_id,
                    attempt=attempt + 1,
                )

                # Check if we should retry
                if self._should_retry(method, response) and attempt < self.max_retries:
                    logger.warning(
                        "internal_api_retry",
                        agent=self.agent_name,
                        method=method,
                        path=path,
                        status_code=response.status_code,
                        correlation_id=correlation_id,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                    )
                    continue

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(
                    "internal_api_timeout",
                    agent=self.agent_name,
                    method=method,
                    path=path,
                    correlation_id=correlation_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt >= self.max_retries:
                    raise InternalAPIError(
                        f"Request timeout after {self.max_retries + 1} attempts",
                        status_code=504,
                    )

            except httpx.RequestError as e:
                last_exception = e
                logger.error(
                    "internal_api_request_error",
                    agent=self.agent_name,
                    method=method,
                    path=path,
                    correlation_id=correlation_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt >= self.max_retries:
                    raise InternalAPIError(
                        f"Request failed after {self.max_retries + 1} attempts: {e}",
                        status_code=502,
                    )

        # Should not reach here, but just in case
        if last_exception:
            raise InternalAPIError(f"Request failed: {last_exception}", status_code=502)
        raise InternalAPIError("Request failed unexpectedly", status_code=500)

    async def get(
        self, path: str, params: dict | None = None, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """GET request."""
        cid = correlation_id or self._generate_correlation_id()
        response = await self._request_with_retry("GET", path, cid, params=params)
        return self._handle_response(response, cid)

    async def post(
        self, path: str, json: dict | None = None, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """POST request."""
        cid = correlation_id or self._generate_correlation_id()
        response = await self._request_with_retry("POST", path, cid, json=json)
        return self._handle_response(response, cid)

    async def put(
        self, path: str, json: dict | None = None, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """PUT request."""
        cid = correlation_id or self._generate_correlation_id()
        response = await self._request_with_retry("PUT", path, cid, json=json)
        return self._handle_response(response, cid)

    async def patch(
        self, path: str, json: dict | None = None, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """PATCH request."""
        cid = correlation_id or self._generate_correlation_id()
        response = await self._request_with_retry("PATCH", path, cid, json=json)
        return self._handle_response(response, cid)

    async def delete(
        self, path: str, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """DELETE request."""
        cid = correlation_id or self._generate_correlation_id()
        response = await self._request_with_retry("DELETE", path, cid)
        return self._handle_response(response, cid)

    def _handle_response(
        self, response: httpx.Response, correlation_id: str
    ) -> dict[str, Any]:
        """Handle response and raise appropriate exceptions."""
        if response.status_code >= 400:
            try:
                error_data = response.json()
            except Exception:
                error_data = {"message": response.text}

            error_msg = (
                error_data.get("detail")
                or error_data.get("message")
                or f"HTTP {response.status_code}"
            )

            logger.error(
                "internal_api_error_response",
                agent=self.agent_name,
                status_code=response.status_code,
                correlation_id=correlation_id,
                error=error_msg,
            )

            if response.status_code == 401:
                raise InternalAPIError(
                    "Unauthorized - invalid or missing API key", status_code=401
                )
            elif response.status_code == 403:
                raise InternalAPIError(
                    "Forbidden - insufficient permissions", status_code=403
                )
            elif response.status_code == 404:
                raise InternalAPIError("Resource not found", status_code=404)
            elif response.status_code == 409:
                raise InternalAPIError(
                    "Conflict - resource already exists", status_code=409
                )
            elif response.status_code == 422:
                raise InternalAPIError(
                    f"Validation error: {error_msg}", status_code=422
                )
            elif response.status_code >= 500:
                raise InternalAPIError(
                    f"Server error: {error_msg}", status_code=response.status_code
                )
            else:
                raise InternalAPIError(error_msg, status_code=response.status_code)

        if response.status_code == 204:
            return {}

        try:
            return response.json()
        except Exception:
            return {"raw_response": response.text}


# Factory function for easy creation
async def create_internal_api_client(
    agent_name: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> InternalAPIClient:
    """
    Create an InternalAPIClient with configuration from settings.

    Args:
        agent_name: Name of the agent (must match AGENT_API_KEYS key)
        base_url: Optional override for base URL
        api_key: Optional override for API key

    Returns:
        Configured InternalAPIClient instance (not started)
    """
    from app.core.config import get_settings

    settings = get_settings()

    # Use provided values or get from settings
    final_base_url = base_url or getattr(
        settings, "INTERNAL_API_URL", "http://localhost:8000"
    )
    final_api_key = api_key or settings.AGENT_API_KEYS.get(agent_name)

    if not final_api_key:
        raise ValueError(f"No API key found for agent: {agent_name}")

    return InternalAPIClient(
        base_url=final_base_url,
        api_key=final_api_key,
        agent_name=agent_name,
    )


# Context manager for easy use
@asynccontextmanager
async def internal_api_client(agent_name: str, **kwargs):
    """Async context manager for InternalAPIClient."""
    client = await create_internal_api_client(agent_name, **kwargs)
    await client.start()
    try:
        yield client
    finally:
        await client.close()
