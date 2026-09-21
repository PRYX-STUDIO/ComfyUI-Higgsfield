"""Generate a validated catalog from the official Higgsfield documentation.

The generator is intentionally conservative: it only accepts official
documentation links and endpoint IDs found in the page source. It never
downloads a ComfyUI catalog through an authenticated request.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pryx_higgsfield.catalog.catalog import validate_catalog_payload


INDEX_URL = "https://docs.higgsfield.ai/docs/llms.txt"
MAX_PAGE_BYTES = 2 * 1024 * 1024
_TICK = chr(96)
ENDPOINT_RE = re.compile(r"Endpoint ID:\*\* " + _TICK + r"([^" + _TICK + r"]+)" + _TICK)
TITLE_RE = re.compile(r"^#\s+(.+?)\s+API", re.MULTILINE)
PARAM_RE = re.compile(
    r'<ParamField\s+body="([^"]+)"\s+type="([^"]+)"(?P<attrs>[^>]*)>(?P<body>.*?)</ParamField>',
    re.DOTALL,
)
DEFAULT_RE = re.compile(r'default="([^"]+)"')


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "PRYX-Higgsfield-Catalog-Sync/1.0"})
    with urlopen(request, timeout=30) as response:
        content = response.read(MAX_PAGE_BYTES + 1)
    if len(content) > MAX_PAGE_BYTES:
        raise RuntimeError(f"Documentation page is too large: {url}")
    return content.decode("utf-8")


def fetch_many(urls: list[str]) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=8) as executor:
        contents = executor.map(fetch, urls)
        return dict(zip(urls, contents))


def parse_page(url: str, content: str) -> dict[str, Any] | None:
    endpoint_match = ENDPOINT_RE.search(content)
    if not endpoint_match:
        return None
    endpoint = endpoint_match.group(1)
    page_path = url.removeprefix("https://docs.higgsfield.ai/docs/models/").removesuffix(".md")
    parts = page_path.split("/")
    slug = "-".join(re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-") for part in parts)
    if parts[-1] in {"generate", "generate-and-edit"} and len(parts) > 1:
        slug = re.sub(r"[^a-z0-9]+", "-", parts[-2].lower()).strip("-")
    capability = _capability(page_path)
    output = "image" if capability in {"image_generate", "image_edit"} else "video"
    parameters = [_parse_parameter(match) for match in PARAM_RE.finditer(content)]
    parameters = [item for item in parameters if item is not None]
    title_match = TITLE_RE.search(content)
    display_name = title_match.group(1).strip() if title_match else slug.replace("-", " ").title()
    input_media = sorted({
        media
        for parameter in parameters
        for media in parameter.get("media_types", [])
    })
    return {
        "id": slug,
        "display_name": display_name,
        "provider": endpoint.split("/", 1)[0].replace("-", " ").title(),
        "family": display_name.split(" · ", 1)[0],
        "endpoint": endpoint,
        "capability": capability,
        "output": output,
        "parameters": parameters,
        "input_media": input_media,
        # Per-field maxima are not a shared total limit.
        "max_references": None,
        "notes": [" ".join(re.sub(r"<[^>]+>", " ", note).split())
                  for note in re.findall(r"<Note>(.*?)</Note>", content, re.DOTALL)],
        "result_field": "images" if output == "image" else "video",
        "docs_source": url,
        "docs_checked": dt.date.today().isoformat(),
        "status": "active",
    }


def _parse_parameter(match: re.Match[str]) -> dict[str, Any]:
    name, type_name, attrs, body = match.groups()
    type_map = {"integer": "integer", "number": "number", "boolean": "boolean", "array": "array", "object": "object"}
    parameter: dict[str, Any] = {"name": name, "type": type_map.get(type_name, "string")}
    if "required" in attrs:
        parameter["required"] = True
    default_match = DEFAULT_RE.search(attrs)
    if default_match:
        parameter["default"] = _parse_scalar(default_match.group(1), parameter["type"])
    text = re.sub(r"<[^>]+>", " ", body)
    text = " ".join(text.split())
    if text:
        parameter["description"] = text
    choices = re.search(r"Supported values:\s*([^\n]+?)(?:\. |\.$|$)", text)
    if choices:
        parameter["choices"] = [_parse_scalar(value, parameter["type"])
                                for value in re.findall(r"`([^`]+)`", choices.group(1))]
    if name == "resolution" and "Recraft V4.1 Pro uses `2k`" in text:
        parameter["choices"] = ["2k"]
    ranges = re.search(r"Supported range:\s*" + _TICK + r"?(-?\d+(?:\.\d+)?)" + _TICK + r"?\s*[–-]\s*" + _TICK + r"?(-?\d+(?:\.\d+)?)" + _TICK + r"?", text)
    if ranges:
        lower, upper = ranges.groups()
        key = "minimum" if parameter["type"] in {"integer", "number"} else None
        if key:
            parameter["minimum"] = _parse_scalar(lower, parameter["type"])
            parameter["maximum"] = _parse_scalar(upper, parameter["type"])
    elif parameter["type"] in {"integer", "number"}:
        bounds = re.search(r"from `(-?\d+)` to `(-?\d+)`", text)
        if bounds:
            parameter["minimum"] = _parse_scalar(bounds.group(1), parameter["type"])
            parameter["maximum"] = _parse_scalar(bounds.group(2), parameter["type"])
    if parameter["type"] == "array":
        count = re.search(r"accepts\s+(?:up to\s+)?`?(\d+)`?(?:\s*[–-]\s*`?(\d+)`?)?", text, re.IGNORECASE)
        if count:
            if count.group(2):
                parameter["min_items"] = int(count.group(1))
                parameter["max_items"] = int(count.group(2))
            else:
                parameter["max_items"] = int(count.group(1))
    if name.endswith("_url") or name.endswith("_urls"):
        parameter["media_types"] = [_media_type(name)]
    return parameter


def _parse_scalar(value: str, type_name: str) -> Any:
    if type_name == "integer":
        return int(value)
    if type_name == "number":
        return float(value)
    if type_name == "boolean":
        return value.lower() == "true"
    return value


def _media_type(name: str) -> str:
    for candidate in ("image", "video", "audio", "file"):
        if candidate in name:
            return candidate
    return "url"


def _capability(path: str) -> str:
    if path.endswith("/text-to-video"):
        return "text_to_video"
    if path.endswith("/image-to-video"):
        return "image_to_video"
    if path.endswith("/reference-to-video"):
        return "reference_to_video"
    if path.endswith("/video-edit"):
        return "video_edit"
    if path.endswith("/video-extend"):
        return "video_extend"
    return "image_edit" if "generate-and-edit" in path else "image_generate"


def _discover_links(content: str, base_url: str) -> set[str]:
    candidates = set(re.findall(r"\]\(([^)]+\.md)\)", content))
    candidates.update(re.findall(r'href="([^"]+)"', content))
    result = set()
    for candidate in candidates:
        candidate = candidate.replace("\\n", "").strip()
        absolute = urljoin(base_url, candidate)
        parsed = urlparse(absolute)
        if parsed.netloc != "docs.higgsfield.ai" or "/docs/models/" not in parsed.path:
            continue
        path = parsed.path
        if not path.endswith(".md"):
            path += ".md"
        result.add(f"https://docs.higgsfield.ai{path}")
    return result


def discover_model_pages(index_url: str) -> list[str]:
    """Discover endpoint pages even when the shared index omits model links."""

    seed_urls = [
        index_url,
        "https://docs.higgsfield.ai/docs/models/image-generation.md",
        "https://docs.higgsfield.ai/docs/models/video-generation.md",
    ]
    seed_contents = fetch_many(seed_urls)
    model_links = {
        link
        for url, content in seed_contents.items()
        for link in _discover_links(content, url)
    }
    overview_contents = fetch_many(sorted(model_links))
    endpoint_links = {
        link
        for url, content in overview_contents.items()
        for link in _discover_links(content, url)
    }
    return sorted(model_links | endpoint_links)


def build_catalog(index_url: str = INDEX_URL) -> dict[str, Any]:
    links = discover_model_pages(index_url)
    models_by_endpoint: dict[str, tuple[int, dict[str, Any]]] = {}
    contents = fetch_many(links)
    for link, content in contents.items():
        model = parse_page(link, content)
        if model:
            previous = models_by_endpoint.get(model["endpoint"])
            depth = link.count("/")
            if previous is None or depth > previous[0]:
                models_by_endpoint[model["endpoint"]] = (depth, model)
    models = [item[1] for item in models_by_endpoint.values()]
    models.sort(key=lambda item: item["id"])
    payload = {
        "schema_version": 1,
        "catalog_version": dt.date.today().isoformat(),
        "source_date": dt.date.today().isoformat(),
        "models": models,
    }
    validate_catalog_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", default=INDEX_URL)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "pryx_higgsfield/catalog/models.json")
    parser.add_argument("--check", action="store_true", help="Fetch and validate without writing.")
    parser.add_argument("--existing", action="store_true", help="Audit existing model pages, preserving workflow IDs and order.")
    args = parser.parse_args()
    if args.existing:
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        pages = fetch_many([model["docs_source"] for model in payload["models"]])
        for model in payload["models"]:
            parsed = parse_page(model["docs_source"], pages[model["docs_source"]])
            if not parsed or parsed["endpoint"] != model["endpoint"]:
                raise RuntimeError(f"Endpoint changed or missing: {model['id']}")
            for key in ("parameters", "input_media", "max_references", "notes", "docs_checked"):
                model[key] = parsed[key]
        payload["catalog_version"] = dt.date.today().isoformat() + ".2"
        payload["source_date"] = dt.date.today().isoformat()
        validate_catalog_payload(payload)
    else:
        payload = build_catalog(args.index_url)
    if not args.check:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(payload['models'])} catalog model(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
