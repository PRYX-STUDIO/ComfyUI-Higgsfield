"""Safe status polling with backoff, timeout, interrupt, and cancel semantics."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

from .errors import APIError, PollingTimeoutError
from .types import AcceptedRequest, RequestStatus, StatusSnapshot


@dataclass(frozen=True)
class PollingConfig:
    initial_delay: float = 2.0
    maximum_delay: float = 10.0
    backoff: float = 1.5
    jitter_fraction: float = 0.10
    timeout: float = 1800.0


class PollingInterrupted(RuntimeError):
    def __init__(self, request_id: str, remote_continues: bool) -> None:
        self.request_id = request_id
        self.remote_continues = remote_continues
        message = (
            f"Local wait interrupted for Higgsfield request {request_id}; "
            + (
                "the queued request was canceled."
                if not remote_continues
                else "the remote generation may continue and may be charged."
            )
        )
        super().__init__(message)


class RequestPoller:
    def __init__(
        self,
        config: PollingConfig | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or PollingConfig()
        self.sleep = sleep
        self.clock = clock
        self.jitter = jitter or (lambda: random.uniform(-1.0, 1.0))

    def poll(
        self,
        accepted: AcceptedRequest,
        *,
        status_getter: Callable[[str], StatusSnapshot],
        cancel: Callable[[str], None] | None = None,
        interrupted: Callable[[], bool] | None = None,
        on_status: Callable[[StatusSnapshot, float], None] | None = None,
    ) -> StatusSnapshot:
        started = self.clock()
        delay = self.config.initial_delay
        cancel_sent = False
        while True:
            elapsed = self.clock() - started
            if elapsed >= self.config.timeout:
                raise PollingTimeoutError(
                    f"Higgsfield request {accepted.request_id} exceeded the local timeout "
                    f"of {self.config.timeout:.0f} seconds."
                )
            if interrupted and interrupted():
                if not cancel_sent and cancel is not None:
                    canceled = bool(cancel(accepted.cancel_url))
                    cancel_sent = True
                    raise PollingInterrupted(accepted.request_id, remote_continues=not canceled)
                raise PollingInterrupted(accepted.request_id, remote_continues=True)

            wait = delay
            if self.config.jitter_fraction:
                wait += delay * self.config.jitter_fraction * self.jitter()
                wait = max(0.0, wait)
            self.sleep(wait)

            try:
                snapshot = status_getter(accepted.status_url)
            except APIError as error:
                if not error.retryable:
                    raise
                if self.clock() - started >= self.config.timeout:
                    raise PollingTimeoutError(
                        f"Could not read Higgsfield request status before the local timeout "
                        f"for {accepted.request_id}."
                    ) from error
                delay = min(delay * self.config.backoff, self.config.maximum_delay)
                continue

            elapsed = self.clock() - started
            if on_status:
                on_status(snapshot, elapsed)
            if snapshot.status.terminal:
                return snapshot
            delay = min(delay * self.config.backoff, self.config.maximum_delay)
