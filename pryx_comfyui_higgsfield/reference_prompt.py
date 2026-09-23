"""Deterministic reference manifests and conservative prompt alias expansion."""

from __future__ import annotations

import re
from collections import Counter

from .errors import ValidationError
from .validation import references_to_arguments


ALIAS = re.compile(r"\{\{ref:([^{}]+)\}\}")
KINDS = {"image": "Image", "video": "Video", "audio": "Audio", "file": "Document", "url": "Web page"}


def reference_prompt(model, references, prompt):
    """Use the actual payload mapper, never a separate guess at media ordering."""
    markers = [f"https://reference.invalid/{i}" for i in range(len(references))]
    mapped = references_to_arguments(model, [
        {"kind": ref.kind, "url": markers[i], "field": ref.field}
        for i, ref in enumerate(references)
    ])
    targets = {}
    for field, values in mapped.items():
        for index, marker in enumerate(values if isinstance(values, list) else [values], 1):
            targets[marker] = (field, index)
    verified = model.id == "wan-3-reference-to-video"
    counts = Counter(ref.label for ref in references if ref.label)
    entries = []
    for i, ref in enumerate(references):
        field, index = targets[markers[i]]
        token = f"{KINDS[ref.kind]} {index}" if field.endswith("_urls") else {
            "image_url": "Start/source image", "end_image_url": "End image",
            "first_frame_url": "Start/source image", "last_frame_url": "End image",
            "last_image_url": "End image", "video_url": "Source video",
            "audio_url": "Audio track", "file_url": "Document", "link_url": "Web page",
        }.get(field, field)
        entries.append({"position": i + 1, "kind": ref.kind, "label": ref.label,
                        "source": ref.source,
                        "input": token, "prompt_token": token if verified and ref.kind in {"image", "video", "audio"} else None})

    def replace(match):
        label = match.group(1).strip()
        if not counts[label]:
            raise ValidationError(f"Unknown reference label: {label}. Check Reference Preview.")
        if counts[label] != 1:
            raise ValidationError(f"Ambiguous reference label: {label}. Assign one unique label per media item.")
        entry = next(item for item in entries if item["label"] == label)
        if not entry["prompt_token"]:
            raise ValidationError(f"Named prompt references are not documented for {model.display_name} / {entry['input']}. No upload or request was sent.")
        return entry["prompt_token"]

    resolved = ALIAS.sub(replace, prompt)
    if "{{ref:" in resolved:
        raise ValidationError("Malformed reference alias. Use {{ref:label}}.")
    if verified:
        available = {entry["prompt_token"] for entry in entries}
        for mention in re.findall(r"\b(?:Image|Video|Audio)\s+\d+\b", resolved):
            if mention not in available:
                raise ValidationError(f"Prompt references missing media: {mention}.")
    lines = [f"{model.display_name} — reference mapping",
             "Numbering is separate for images, videos and audio.",
             "Direct inputs come first; collector inputs follow. Collector slots use numeric order; batches keep their order."]
    if not verified:
        lines.append("Prompt reference syntax is NOT confirmed for this endpoint. Numbered entries below identify payload order only, not supported prompt tokens.")
    for entry in entries:
        label = entry["label"] or "unlabelled"
        suffix = " (duplicate label; cannot use as alias)" if counts[label] > 1 else ""
        origin = f" ({entry['source']})" if entry["source"] else ""
        lines.append(f"{entry['input']} ← {label}{origin}{suffix}")
    if not entries:
        lines.append("No connected reference media.")
    lines.extend(["", "Resolved prompt:", resolved])
    return resolved, entries, "\n".join(lines)
