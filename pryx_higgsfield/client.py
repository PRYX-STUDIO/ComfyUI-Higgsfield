"""Higgsfield transport wrapper used by the ComfyUI nodes.

The official SDK remains a package dependency for compatibility with the
Higgsfield ecosystem. This wrapper owns the extra estimate, safe-download, and
ComfyUI lifecycle rules required by the node pack.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import httpx

from .credentials import Credentials, resolve_credentials
from .errors import APIError, CredentialError, MediaError, api_error_from_response
from .types import AcceptedRequest, Estimate, ModelSpec, StatusSnapshot


DEFAULT_TIMEOUT = 1800.0
DEFAULT_BASE_URL = "https://api.higgsfield.ai"
USER_AGENT = "pryx-higgsfield-comfyui/1.0"
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024


class HiggsfieldClient:
    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
        upload_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not credentials.authorization_key:
            raise CredentialError("Higgsfield credentials are empty.")
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._client = http_client or httpx.Client(
            headers=self._headers(),
            timeout=self.timeout,
            follow_redirects=False,
        )
        if http_client is not None:
            self._client.headers.update(self._headers())
        self._upload_client = upload_client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
        )
        self._sleep = sleep

    @classmethod
    def from_environment(cls, *, timeout: float = DEFAULT_TIMEOUT, **kwargs: Any) -> "HiggsfieldClient":
        return cls(resolve_credentials(), timeout=timeout, **kwargs)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Key {self.credentials.authorization_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def close(self) -> None:
        self._client.close()
        self._upload_client.close()

    def estimate(self, model: ModelSpec, arguments: Mapping[str, Any]) -> Estimate:
        response = self._request(
            "POST",
            f"/estimate/{model.endpoint.lstrip('/')}",
            json=dict(arguments),
        )
        return Estimate.from_payload(response.json())

    def get_json(self, path: str, *, attempts: int = 4) -> Mapping[str, Any]:
        response = self._request_with_retry("GET", path, attempts=attempts)
        try:
            payload = response.json()
        except ValueError as error:
            raise APIError(
                status_code=response.status_code,
                message="Higgsfield returned invalid JSON.",
            ) from error
        if not isinstance(payload, Mapping):
            raise APIError(
                status_code=response.status_code,
                message="Higgsfield returned an invalid JSON object.",
            )
        return payload

    def submit(self, model: ModelSpec, arguments: Mapping[str, Any]) -> AcceptedRequest:
        """Submit exactly once.

        A timeout after the POST may mean the provider accepted the request.
        It is surfaced as ambiguous_submission and is never retried here.
        """

        try:
            response = self._client.post(
                self._path(f"/{model.endpoint.lstrip('/')}"),
                json=dict(arguments),
                timeout=self.timeout,
            )
        except httpx.TimeoutException as error:
            raise APIError(
                status_code=None,
                message="The generation submission timed out after it was sent; it was not retried.",
                retryable=False,
                ambiguous_submission=True,
            ) from error
        except httpx.RequestError as error:
            raise APIError(
                status_code=None,
                message="The generation submission could not be sent; it was not retried.",
                retryable=False,
                ambiguous_submission=True,
            ) from error
        if response.is_error:
            raise api_error_from_response(response)
        try:
            return AcceptedRequest.from_payload(response.json())
        except (TypeError, KeyError, ValueError) as error:
            raise APIError(
                status_code=response.status_code,
                message="Higgsfield returned an invalid generation acceptance response.",
            ) from error

    def status(self, status_url: str, *, attempts: int = 4) -> StatusSnapshot:
        response = self._request_with_retry("GET", status_url, attempts=attempts)
        try:
            return StatusSnapshot.from_payload(response.json())
        except (TypeError, KeyError, ValueError) as error:
            raise APIError(
                status_code=response.status_code,
                message="Higgsfield returned an invalid request status.",
            ) from error

    def cancel(self, cancel_url: str) -> None:
        response = self._request("POST", cancel_url)
        if response.status_code not in {200, 202, 204}:
            raise api_error_from_response(response)

    def upload_bytes(self, data: bytes, content_type: str) -> str:
        if not isinstance(data, bytes) or not data:
            raise MediaError("Cannot upload an empty media buffer.")
        response = self._request(
            "POST",
            "/files/generate-upload-url",
            json={"content_type": content_type},
        )
        try:
            payload = response.json()
            public_url = str(payload["public_url"])
            upload_url = str(payload["upload_url"])
            upload_headers = dict(payload.get("upload_headers") or {"Content-Type": content_type})
        except (TypeError, KeyError, ValueError) as error:
            raise MediaError("Higgsfield returned an invalid upload response.") from error
        _validate_https_url(upload_url, "upload URL")
        _validate_https_url(public_url, "public media URL")
        upload_headers.pop("Authorization", None)
        upload_headers.pop("authorization", None)
        try:
            uploaded = self._upload_client.put(
                upload_url,
                content=data,
                headers=upload_headers,
                timeout=self.timeout,
            )
        except httpx.RequestError as error:
            raise MediaError("The media upload failed before generation was submitted.") from error
        if uploaded.is_error:
            raise api_error_from_response(uploaded)
        return public_url

    def download_to_file(
        self,
        url: str,
        path: str | os.PathLike[str],
        *,
        max_bytes: int = MAX_DOWNLOAD_BYTES,
    ) -> Path:
        _validate_https_url(url, "download URL")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.part")
        total = 0
        try:
            with self._upload_client.stream("GET", url, timeout=self.timeout) as response:
                if response.is_error:
                    raise api_error_from_response(response)
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise MediaError("The remote media file exceeds the configured size limit.")
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise MediaError("The remote media file exceeds the configured size limit.")
                        handle.write(chunk)
            os.replace(temporary, destination)
            return destination
        except (httpx.RequestError, OSError, ValueError) as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, MediaError):
                raise
            raise MediaError("The result media download failed.") from error
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def validate_credentials(self, model: ModelSpec) -> Estimate:
        return self.estimate(
            model,
            {
                "prompt": "credential validation",
                "aspect_ratio": "1:1",
                "resolution": "720p",
            },
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        request_url = self._path(url)
        try:
            response = self._client.request(method, request_url, **kwargs)
        except httpx.TimeoutException as error:
            raise APIError(
                status_code=None,
                message=f"Higgsfield {method} request timed out.",
                retryable=method.upper() == "GET",
            ) from error
        except httpx.RequestError as error:
            raise APIError(
                status_code=None,
                message=f"Higgsfield {method} request failed.",
                retryable=method.upper() == "GET",
            ) from error
        if response.is_error:
            raise api_error_from_response(response)
        return response

    def _request_with_retry(self, method: str, url: str, *, attempts: int = 4) -> httpx.Response:
        delay = 1.0
        for attempt in range(1, attempts + 1):
            try:
                response = self._request(method, url)
            except APIError as error:
                if not error.retryable or attempt >= attempts:
                    raise
                self._sleep(delay)
                delay = min(delay * 2.0, 10.0)
                continue
            if response.is_error:
                error = api_error_from_response(response)
                if not error.retryable or attempt >= attempts:
                    raise error
                self._sleep(delay)
                delay = min(delay * 2.0, 10.0)
                continue
            return response
        raise APIError(status_code=None, message="Higgsfield status request failed.", retryable=True)

    def _path(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            parsed = urlsplit(url)
            base = urlsplit(self.base_url)
            if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
                raise APIError(
                    status_code=None,
                    message="Higgsfield returned a status or cancel URL on an unexpected host.",
                )
            return url
        if not url.startswith("/"):
            url = f"/{url}"
        return f"{self.base_url}{url}"


def _validate_https_url(value: str, label: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise MediaError(f"Higgsfield returned an invalid {label}.")
