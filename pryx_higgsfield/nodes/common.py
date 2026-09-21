"""Shared generation execution for image and video nodes."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..catalog import Catalog, runtime_catalog
from ..client import HiggsfieldClient
from ..errors import APIError, HiggsfieldError, MediaError, ValidationError
from ..media import MediaArtifact, MediaStore, empty_image, extract_media_urls, upload_reference
from ..polling import PollingConfig, PollingInterrupted, RequestPoller
from ..server import emit_progress
from ..types import AcceptedRequest, Estimate, ModelSpec, Phase, ProgressEvent, RequestStatus, StatusSnapshot
from ..validation import normalize_arguments, references_to_arguments
from .references import Reference, ReferenceCollection


@dataclass
class GenerationOutcome:
    model: ModelSpec
    estimate: Estimate
    accepted: AcceptedRequest | None = None
    snapshot: StatusSnapshot | None = None
    urls: list[str] = field(default_factory=list)
    artifacts: list[MediaArtifact] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def request_id(self) -> str:
        return self.accepted.request_id if self.accepted else ""

    @property
    def status(self) -> str:
        if self.snapshot:
            return self.snapshot.status.value
        return "estimated"

    def status_json(self) -> str:
        payload: dict[str, Any] = {
            "status": self.status,
            "request_id": self.request_id or None,
            "status_url": self.accepted.status_url if self.accepted else None,
            "cancel_url": self.accepted.cancel_url if self.accepted else None,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "remote_urls": self.urls,
        }
        if self.snapshot:
            payload["provider_status"] = dict(self.snapshot.payload)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def execute_generation(
    model_id: str,
    arguments: Mapping[str, Any],
    *,
    mode: str,
    max_usd: float,
    auto_save: bool,
    timeout: float,
    references: ReferenceCollection | list[Reference] | None = None,
    client: HiggsfieldClient | None = None,
    catalog: Catalog | None = None,
    node_id: str | None = None,
    allow_unknown: bool = False,
) -> GenerationOutcome:
    if mode not in {"estimate_only", "generate"}:
        raise ValidationError("mode must be estimate_only or generate.")
    if max_usd < 0:
        raise ValidationError("max_usd must be zero or a positive value.")
    if timeout <= 0:
        raise ValidationError("timeout must be greater than zero.")

    active_catalog = catalog or runtime_catalog()
    model = active_catalog.get(model_id)
    if model.status.value == "unavailable":
        raise ValidationError(f"Model {model.display_name} is unavailable in the catalog.")
    ref_values = ReferenceCollection(references or ())
    # Validate counts, required media, and parameter combinations BEFORE uploading.
    preview = references_to_arguments(model, [
        {"kind": ref.kind, "url": ref.url or f"https://local-reference.invalid/{index}", "field": ref.field}
        for index, ref in enumerate(ref_values)
    ]) if ref_values else {}
    normalized = normalize_arguments(model, {**arguments, **preview}, allow_unknown=allow_unknown)
    start = time.monotonic()
    _progress(node_id, Phase.VALIDATE, None, start, message="Inputs validated.")

    owned_client = client is None
    hf_client = client or HiggsfieldClient.from_environment(timeout=timeout)
    try:
        if ref_values:
            uploaded: list[dict[str, Any]] = []
            for index, reference in enumerate(ref_values):
                _progress(node_id, Phase.UPLOAD, None, start, message=f"Uploading reference {index + 1}.")
                url = upload_reference(hf_client, reference)
                uploaded.append({"kind": reference.kind, "url": url, "field": reference.field})
            normalized.update(references_to_arguments(model, uploaded))
            normalized = normalize_arguments(model, normalized, allow_unknown=allow_unknown)

        _progress(node_id, Phase.ESTIMATE, None, start, message="Estimating request cost.")
        estimate = hf_client.estimate(model, normalized)
        if max_usd > 0:
            if estimate.usd is None:
                raise ValidationError("The provider returned no USD estimate; max_usd cannot be enforced.")
            if estimate.usd > max_usd:
                raise ValidationError(
                    f"Estimated cost {estimate.usd:.4f} USD exceeds max_usd {max_usd:.4f} USD; "
                    "no generation request was sent."
                )
        if mode == "estimate_only":
            outcome = GenerationOutcome(
                model=model,
                estimate=estimate,
                elapsed_seconds=time.monotonic() - start,
            )
            _progress(node_id, Phase.COMPLETED, None, start, estimate=estimate, message="Estimate completed.")
            return outcome

        _progress(node_id, Phase.QUEUED, None, start, estimate=estimate, message="Submitting generation.")
        accepted = hf_client.submit(model, normalized)
        latest = {"snapshot": StatusSnapshot(
            status=accepted.status,
            request_id=accepted.request_id,
            status_url=accepted.status_url,
            cancel_url=accepted.cancel_url,
            payload=accepted.raw,
        )}

        def on_status(snapshot: StatusSnapshot, elapsed: float) -> None:
            latest["snapshot"] = snapshot
            phase = Phase.QUEUED if snapshot.status == RequestStatus.QUEUED else Phase.GENERATING
            _progress(
                node_id,
                phase,
                accepted.request_id,
                start,
                estimate=estimate,
                status=snapshot.status,
                message=f"Provider status: {snapshot.status.value}.",
            )

        def cancel_if_queued(cancel_url: str) -> bool:
            if latest["snapshot"].status != RequestStatus.QUEUED:
                return False
            hf_client.cancel(cancel_url)
            return True

        snapshot = RequestPoller(PollingConfig(timeout=timeout)).poll(
            accepted,
            status_getter=hf_client.status,
            cancel=cancel_if_queued,
            interrupted=_comfy_interrupted,
            on_status=on_status,
        )
        if snapshot.status != RequestStatus.COMPLETED:
            billable = snapshot.status not in {
                RequestStatus.FAILED,
                RequestStatus.NSFW,
                RequestStatus.CANCELED,
            }
            raise APIError(
                status_code=None,
                message=(
                    f"Higgsfield request ended with status {snapshot.status.value}. "
                    "No replacement generation was submitted."
                ),
                request_id=accepted.request_id,
                billable=billable,
            )
        urls = extract_media_urls(snapshot.payload, model.result_field)
        if not urls:
            raise MediaError(
                f"Higgsfield completed request {accepted.request_id} without a downloadable {model.output.value} result."
            )
        _progress(node_id, Phase.DOWNLOAD, accepted.request_id, start, estimate=estimate, status=snapshot.status)
        store = MediaStore(hf_client)
        artifacts = [
            store.save(
                url,
                request_id=accepted.request_id,
                output=model.output.value,
                temporary=not auto_save,
                index=index,
            )
            for index, url in enumerate(urls)
        ]
        outcome = GenerationOutcome(
            model=model,
            estimate=estimate,
            accepted=accepted,
            snapshot=snapshot,
            urls=urls,
            artifacts=artifacts,
            elapsed_seconds=time.monotonic() - start,
        )
        _progress(
            node_id,
            Phase.COMPLETED,
            accepted.request_id,
            start,
            estimate=estimate,
            status=snapshot.status,
            message="Generation completed and media saved.",
        )
        return outcome
    except PollingInterrupted:
        raise
    except HiggsfieldError:
        _progress(node_id, Phase.FAILED, None, start, message="Higgsfield request failed.")
        raise
    finally:
        if owned_client:
            hf_client.close()


def _progress(
    node_id: str | None,
    phase: Phase,
    request_id: str | None,
    start: float,
    *,
    estimate: Estimate | None = None,
    status: RequestStatus | None = None,
    message: str = "",
) -> None:
    emit_progress(
        ProgressEvent(
            node_id=node_id,
            phase=phase,
            request_id=request_id,
            elapsed_seconds=time.monotonic() - start,
            estimate=estimate,
            status=status,
            message=message,
        )
    )


def _comfy_interrupted() -> bool:
    try:
        import comfy.model_management as model_management

        checker = getattr(model_management, "processing_interrupted", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def image_output(outcome: GenerationOutcome) -> Any:
    values = [artifact.native for artifact in outcome.artifacts if artifact.native is not None]
    if not values:
        return empty_image()
    if len(values) == 1:
        return values[0]
    try:
        import torch

        return torch.cat(values, dim=0)
    except Exception:
        return values[0]


def video_output(outcome: GenerationOutcome) -> Any:
    if not outcome.artifacts:
        return None
    return outcome.artifacts[0].native or str(outcome.artifacts[0].path)
