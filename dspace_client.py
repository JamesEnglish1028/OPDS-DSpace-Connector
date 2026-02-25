import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOGGER = logging.getLogger(__name__)


class UpstreamServiceError(Exception):
    """Raised when DSpace upstream requests fail."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DSpaceClient:
    """Thin HTTP client wrapper for DSpace with retries, timeouts, and JSON parsing."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0, retry_total: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

        retry_policy = Retry(
            total=retry_total,
            connect=retry_total,
            read=retry_total,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_json(
        self,
        path: str,
        params: dict | None = None,
        absolute_url: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict:
        url = path if absolute_url else f"{self.base_url}{path}"
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            LOGGER.warning("DSpace request failed", extra={"url": url, "error": str(exc)})
            raise UpstreamServiceError(f"DSpace request failed for {url}: {exc}") from exc
        except ValueError as exc:
            LOGGER.warning("Invalid JSON from DSpace", extra={"url": url, "error": str(exc)})
            raise UpstreamServiceError(f"Invalid JSON from DSpace for {url}") from exc
