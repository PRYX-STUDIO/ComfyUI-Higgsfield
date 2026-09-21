"""User-facing errors with request context and secret-safe messages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class HiggsfieldError(RuntimeError):
    """Base class for errors raised by the node pack."""


class CatalogError(HiggsfieldError):
    pass


class CatalogUnavailableError(CatalogError):
    pass


class CredentialError(HiggsfieldError):
    pass


class ValidationError(HiggsfieldError):
    pass


class MediaError(HiggsfieldError):
    pass


class PollingTimeoutError(HiggsfieldError):
    pass


@dataclass
class APIError(HiggsfieldError):
    status_code: int | None
    message: str
    request_id: str | None = None
    correlation_id: str | None = None
    retryable: bool = False
    ambiguous_submission: bool = False
    billable: bool | None = None

    def __post_init__(self) -> None:
        self.message = redact_secrets(self.message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.insert(0, f"Higgsfield API {self.status_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        if self.correlation_id:
            parts.append(f"correlation_id={self.correlation_id}")
        return " — ".join(parts)


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:key|bearer)\s+)[^\s,;]+"),
    re.compile(r"(?i)(hf_(?:api_key|api_secret|key)\s*[:=]\s*)[^\s,;]+"),
)


def redact_secrets(value: Any, secrets: Iterable[str] = ()) -> str:
    """Return text safe for ComfyUI logs and node error messages."""

    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def _message_from_payload(payload: Any, fallback: str) -> str:
    if isinstance(payload, Mapping):
        for key in ("detail", "details", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        errors = payload.get("errors")
        if errors:
            return str(errors)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return fallback


def api_error_from_response(response: Any, *, request_id: str | None = None) -> APIError:
    """Translate an httpx-like response without echoing request secrets."""

    try:
        payload = response.json()
    except Exception:
        payload = getattr(response, "text", "")
    status_code = getattr(response, "status_code", None)
    message = _message_from_payload(payload, f"HTTP {status_code or 'error'}")
    headers = getattr(response, "headers", {}) or {}
    correlation = headers.get("X-Correlation-ID") or headers.get("x-correlation-id")
    status = int(status_code) if status_code is not None else None
    return APIError(
        status_code=status,
        message=_friendly_api_message(status, message),
        request_id=request_id,
        correlation_id=correlation,
        retryable=status is not None and (status >= 500 or status == 429),
        billable=False if status in {400, 401, 404, 422, 423, 500, 503} else None,
    )


def _friendly_api_message(status_code: int | None, detail: str) -> str:
    actions = {
        400: "Check the model parameters and account concurrency limit.",
        401: "Configure a valid Higgsfield API key and secret in ComfyUI Settings.",
        403: "Check the Higgsfield account balance and model access.",
        404: "Check the model ID or request ID.",
        422: "Check the request schema and required media inputs.",
        423: "The selected model is temporarily unavailable; try again later.",
        500: "Higgsfield reported a temporary server error; retry the status request later.",
        503: "The selected model is disabled or not ready; try again later.",
    }
    action = actions.get(status_code)
    if action and action.lower() not in detail.lower():
        return f"{detail} {action}"
    return detail


def exception_without_secret(error: BaseException, secrets: Iterable[str] = ()) -> str:
    return redact_secrets(f"{type(error).__name__}: {error}", secrets)


def json_without_secrets(value: Any, secrets: Iterable[str] = ()) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        encoded = str(value)
    return redact_secrets(encoded, secrets)
