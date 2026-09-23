"""Inspect the public Higgsfield model pages without account credentials.

The public Next.js page embeds an API reference, input JSON Schema, and the
model-family variants in its server-rendered flight data. A failed extraction
is an error, never a reason to publish a partial catalog.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HOST = "https://open.higgsfield.ai"
MIN_DISCOVERED_ENDPOINTS = 80  # A shrinking inventory needs manual review.
LEGACY_DOCUMENTED_ENDPOINTS = {"higgsfield-ai/soul/cinema"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pryx_comfyui_higgsfield.catalog.catalog import validate_catalog_payload
MAX_BYTES = 3 * 1024 * 1024
MODEL_LINK = re.compile(r'/models/([a-zA-Z0-9._~/-]+)/playground')
API_ENDPOINT = re.compile(r'https://api\.higgsfield\.ai/([a-zA-Z0-9._~/-]+)')
SCHEMA_BLOCK = re.compile(r'### Input JSON Schema\s+```json\s*(\{.*?\})\s*```', re.DOTALL)


class _FlightScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.in_script = tag == "script"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if self.in_script and "self.__next_f.push" in data:
            for match in re.finditer(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)', data):
                self.parts.append(json.loads(match.group(1)))


def fetch_public(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "open.higgsfield.ai":
        raise ValueError("Only public Higgsfield model pages may be fetched")
    request = Request(url, headers={"User-Agent": "PRYX-ComfyUI-Higgsfield-Catalog-Audit/1.0"})
    with urlopen(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"Public page exceeds maximum size: {url}")
    return data.decode("utf-8")


def flight_text(page: str) -> str:
    parser = _FlightScripts()
    parser.feed(page)
    if not parser.parts:
        raise ValueError("Higgsfield server-rendered model data is missing")
    return "\n".join(parser.parts)


def discover_models(page: str) -> set[str]:
    return {
        match.group(1)
        for match in MODEL_LINK.finditer(html.unescape(page))
        if not match.group(1).startswith("workflows/")
    }


def inspect_family(slug: str) -> tuple[set[str], dict]:
    page = fetch_public(f"{HOST}/models/{slug}/api-reference")
    data = flight_text(page)
    endpoints = {match.group(1) for match in API_ENDPOINT.finditer(data)}
    schema = SCHEMA_BLOCK.search(data)
    if slug not in endpoints or not schema:
        raise ValueError(f"Missing matching API reference or input schema: {slug}")
    input_schema = json.loads(schema.group(1))
    if not isinstance(input_schema.get("properties"), dict):
        raise ValueError(f"Invalid model input schema: {slug}")
    family_start = data.find('"family":[')
    if family_start == -1:
        raise ValueError(f"Model family variants are missing: {slug}")
    variants_data, _ = json.JSONDecoder().raw_decode(data[family_start + len('"family":'):])
    variants = {item["slug"] for item in variants_data if isinstance(item, dict) and item.get("slug")}
    variants.add(slug)
    current = next((item for item in variants_data if item.get("slug") == slug), {})
    return variants, {"slug": slug, "schema": input_schema,
                      "source": f"{HOST}/models/{slug}/api-reference",
                      "title": current.get("title") or slug,
                      "variant_title": current.get("variant_title") or "",
                      "operation_type": current.get("type") or ""}


def audit() -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        index_pages = list(pool.map(fetch_public, (f"{HOST}/explore/image", f"{HOST}/explore/video")))
    seeds = set().union(*(discover_models(page) for page in index_pages))
    if not seeds:
        raise ValueError("No model links found in Higgsfield explore pages")
    result: dict[str, dict] = {}
    pending = seeds
    for _ in range(3):
        pending -= result.keys()
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=6) as pool:
            inspected = pool.map(inspect_family, sorted(pending))
            next_pending: set[str] = set()
            for variants, model in inspected:
                result[model["slug"]] = model
                next_pending.update(variants)
        pending = next_pending
    if pending - result.keys():
        raise ValueError(f"Variant discovery did not converge: {sorted(pending - result.keys())}")
    if len(result) < MIN_DISCOVERED_ENDPOINTS:
        raise ValueError(f"Only {len(result)} endpoints found; refusing a partial platform catalog")
    return dict(sorted(result.items()))


def _capability(slug: str, operation: str) -> str:
    if slug.endswith("/text-to-video") or "/text-to-video/" in slug:
        return "text_to_video"
    if slug.endswith("/video-extend"):
        return "video_extend"
    if slug.endswith("/reference-to-video") or slug.endswith(("/image-reference", "/video-reference")):
        return "reference_to_video"
    if slug.endswith("/video-edit") or operation == "video2video":
        return "video_edit"
    if "motion-control" in slug or "motion-transfer" in slug or "object-swap" in slug:
        return "video_motion"
    if slug.endswith("/image-to-video") or "/image-to-video/" in slug or slug.endswith("/first-last-frame"):
        return "image_to_video"
    if operation in {"text2image", "image_edit"} or slug.startswith(("recraft/", "ideogram/", "z-image/", "marketing-studio/", "higgsfield-ai/", "alibaba/qwen-image-", "xai/grok-imagine-image-")):
        return "image_edit" if operation == "image_edit" or any(name in slug for name in ("/edit", "marketing-studio/", "grok-imagine-image")) else "image_generate"
    if slug.startswith("higgsfield/cinema-studio/"):
        return "reference_to_video"
    raise ValueError(f"No safe node capability mapping for {slug}: {operation}")


def _parameter(name: str, item: dict, required: set[str]) -> dict:
    parameter: dict = {"name": name, "type": item["type"], "required": name in required}
    for source, target in (("default", "default"), ("enum", "choices"),
                           ("minimum", "minimum"), ("maximum", "maximum"),
                           ("minItems", "min_items"), ("maxItems", "max_items"),
                           ("minLength", "min_length"), ("maxLength", "max_length"),
                           ("multipleOf", "multiple_of")):
        if source in item:
            parameter[target] = item[source]
    parameter["description"] = item.get("description") or item.get("title") or name
    if item.get("format") == "uri" or item.get("items", {}).get("format") == "uri":
        media = next((kind for kind in ("image", "video", "audio", "file") if kind in name), "url")
        if name in {"first_frame_url", "last_frame_url"}:
            media = "image"
        parameter["media_types"] = [media]
    return parameter


def build_catalog(snapshot: dict[str, dict], bundled: dict) -> dict:
    import datetime as dt

    existing = {model["endpoint"]: model for model in bundled["models"]}
    models = []
    for slug, item in snapshot.items():
        schema = item["schema"]
        properties = schema["properties"]
        required = set(schema.get("required", ()))
        parameters = [_parameter(name, prop, required) for name, prop in properties.items()]
        capability = _capability(slug, item["operation_type"])
        image_output = capability in {"image_generate", "image_edit"}
        previous = existing.pop(slug, None)
        title = schema.get("title", "").removesuffix(" Playground") or item["title"]
        display = previous["display_name"] if previous else title
        if not previous and item["variant_title"] and item["variant_title"].lower() not in display.lower():
            display += " · " + item["variant_title"]
        media = sorted({kind for parameter in parameters for kind in parameter.get("media_types", ())})
        models.append({
            "id": previous["id"] if previous else re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-"),
            "display_name": display,
            "provider": previous["provider"] if previous else slug.split("/")[0].replace("-", " ").title(),
            "family": previous["family"] if previous else item["title"],
            "endpoint": slug,
            "capability": capability,
            "output": "image" if image_output else "video",
            "parameters": parameters,
            "input_media": media,
            "max_references": None,
            "result_field": "images" if image_output else "video",
            "docs_source": item["source"],
            "docs_checked": dt.date.today().isoformat(),
            "status": "active",
            "notes": previous.get("notes", []) if previous else [],
            "input_schema": schema,
        })
    unknown_missing = set(existing) - LEGACY_DOCUMENTED_ENDPOINTS
    if unknown_missing:
        raise ValueError(f"Previously cataloged endpoints missing from platform inventory: {sorted(unknown_missing)}")
    # This one endpoint is documented separately, outside public Explore.
    models.extend(existing.values())
    if models == bundled["models"]:
        return bundled
    today = dt.date.today().isoformat()
    old_version = bundled["catalog_version"]
    suffix = int(old_version.rsplit(".", 1)[1]) + 1 if old_version.startswith(today + ".") else 1
    payload = {"schema_version": 1, "catalog_version": f"{today}.{suffix}",
               "source_date": dt.date.today().isoformat(), "models": models}
    validate_catalog_payload(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--snapshot", type=Path, help="Write a generated audit snapshot for local validation")
    parser.add_argument("--from-snapshot", type=Path, help="Use a previously audited local snapshot")
    parser.add_argument("--catalog", type=Path, help="Generate the validated bundled catalog")
    parser.add_argument("--check", action="store_true", help="Fail if the bundled catalog has drifted")
    args = parser.parse_args()
    result = json.loads(args.from_snapshot.read_text(encoding="utf-8")) if args.from_snapshot else audit()
    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.catalog:
        bundled = json.loads(args.catalog.read_text(encoding="utf-8"))
        payload = build_catalog(result, bundled)
        if args.check and payload != bundled:
            raise SystemExit("Catalog drift detected; regenerate and review the contract")
        if not args.check and payload != bundled:
            args.catalog.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Validated {len(payload['models'])} catalog endpoints")
    if args.summary:
        counts: dict[str, int] = {}
        for slug in result:
            counts[slug.split("/")[0]] = counts.get(slug.split("/")[0], 0) + 1
        print(json.dumps({"total": len(result), "by_provider": counts}, indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
