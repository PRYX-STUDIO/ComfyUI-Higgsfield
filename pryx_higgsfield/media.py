"""ComfyUI media encoding, upload preparation, download, and persistence."""

from __future__ import annotations

import io
import mimetypes
import os
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .client import HiggsfieldClient
from .errors import MediaError
from .nodes.references import Reference


def image_to_png_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    try:
        from PIL import Image
    except ImportError as error:
        raise MediaError("Pillow is required to upload IMAGE inputs.") from error
    array = _to_numpy(value)
    if array is not None:
        if getattr(array, "ndim", 0) == 4:
            array = array[0]
        if array.ndim != 3 or array.shape[-1] not in (1, 3, 4):
            raise MediaError("IMAGE input must have shape [height, width, channels].")
        if array.dtype.kind == "f":
            array = (array.clip(0, 1) * 255).round().astype("uint8")
        else:
            array = array.clip(0, 255).astype("uint8")
        if array.shape[-1] == 1:
            array = array[:, :, 0]
        image = Image.fromarray(array)
    elif isinstance(value, Image.Image):
        image = value
    else:
        raise MediaError("Unsupported IMAGE input.")
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def audio_to_wav_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if not isinstance(value, Mapping):
        raise MediaError("AUDIO input must be a ComfyUI audio mapping.")
    waveform = value.get("waveform")
    sample_rate = int(value.get("sample_rate", 44100))
    array = _to_numpy(waveform)
    if array is None:
        raise MediaError("Could not convert AUDIO waveform to samples.")
    if getattr(array, "ndim", 0) == 3:
        array = array[0]
    if getattr(array, "ndim", 0) == 1:
        array = array[None, :]
    if array.ndim != 2:
        raise MediaError("AUDIO waveform must have channel and sample dimensions.")
    if array.shape[0] > array.shape[1]:
        array = array.T
    array = array.clip(-1, 1)
    try:
        import numpy as np

        pcm = (array.T * 32767).astype(np.int16).tobytes()
    except ImportError as error:
        raise MediaError("NumPy is required to upload AUDIO inputs.") from error
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(int(array.shape[0]))
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return buffer.getvalue()


def video_to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (str, os.PathLike)):
        return Path(value).read_bytes()
    for method_name in ("save_to", "export", "write"):
        method = getattr(value, method_name, None)
        if callable(method):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
                temporary = Path(handle.name)
            try:
                method(str(temporary))
                return temporary.read_bytes()
            finally:
                temporary.unlink(missing_ok=True)
    path = getattr(value, "path", None) or getattr(value, "filename", None)
    if path:
        return Path(path).read_bytes()
    raise MediaError("Could not serialize the VIDEO input to MP4.")


def upload_reference(client: HiggsfieldClient, reference: Reference) -> str:
    if reference.url:
        return reference.url
    if reference.value is None:
        raise MediaError("A local reference does not contain media data.")
    if reference.kind == "image":
        return client.upload_bytes(image_to_png_bytes(reference.value), "image/png")
    if reference.kind == "video":
        return client.upload_bytes(video_to_bytes(reference.value), "video/mp4")
    if reference.kind == "audio":
        return client.upload_bytes(audio_to_wav_bytes(reference.value), "audio/wav")
    raise MediaError(f"Unsupported local reference type: {reference.kind}")


def extract_media_urls(payload: Mapping[str, Any], field: str) -> list[str]:
    value: Any = payload.get(field)
    if value is None:
        return []
    candidates = value if isinstance(value, list) else [value]
    result: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            url = candidate
        elif isinstance(candidate, Mapping):
            url = candidate.get("url") or candidate.get("download_url")
        else:
            url = None
        if isinstance(url, str) and url.startswith("https://"):
            result.append(url)
    return result


def media_extension(url: str, output: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".avif", ".mp4", ".mov", ".webm"}:
        return suffix
    return ".png" if output == "image" else ".mp4"


def _to_numpy(value: Any) -> Any:
    try:
        detached = value.detach().cpu() if hasattr(value, "detach") else value
        return detached.numpy() if hasattr(detached, "numpy") else _numpy_array(detached)
    except Exception:
        return _numpy_array(value)


def _numpy_array(value: Any) -> Any:
    try:
        import numpy as np

        return np.asarray(value)
    except Exception:
        return None


def output_directory(temporary: bool) -> Path:
    try:
        import folder_paths

        getter = (
            getattr(folder_paths, "get_temp_directory", None)
            if temporary
            else getattr(folder_paths, "get_output_directory", None)
        )
        if callable(getter):
            directory = Path(getter())
        else:
            directory = Path(getattr(folder_paths, "temp_directory" if temporary else "output_directory"))
    except Exception:
        directory = Path.cwd() / ("temp" if temporary else "output")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@dataclass(frozen=True)
class MediaArtifact:
    path: Path
    url: str
    kind: str
    native: Any = None


class MediaStore:
    def __init__(self, client: HiggsfieldClient, *, node_prefix: str = "pryx_higgsfield") -> None:
        self.client = client
        self.node_prefix = node_prefix

    def save(
        self,
        url: str,
        *,
        request_id: str,
        output: str,
        temporary: bool,
        index: int = 0,
    ) -> MediaArtifact:
        extension = media_extension(url, output)
        folder = output_directory(temporary)
        path = folder / f"{self.node_prefix}_{request_id}_{index}{extension}"
        self.client.download_to_file(url, path)
        native = _load_native_image(path) if output == "image" else _load_native_video(path)
        return MediaArtifact(path=path, url=url, kind=output, native=native)


def _load_native_image(path: Path) -> Any:
    try:
        from PIL import Image
        import numpy as np
        import torch

        image = Image.open(path).convert("RGB")
        array = np.asarray(image).astype("float32") / 255.0
        return torch.from_numpy(array)[None, ...]
    except Exception:
        return None


def _load_native_video(path: Path) -> Any:
    candidates = (
        ("comfy_api.latest._video_types", "VideoFromFile"),
        ("comfy_api.latest.video_types", "VideoFromFile"),
        ("comfy.utils", "VideoFromFile"),
    )
    for module_name, class_name in candidates:
        try:
            module = __import__(module_name, fromlist=[class_name])
            constructor = getattr(module, class_name)
            return constructor(str(path))
        except Exception:
            continue
    return str(path)


def empty_image() -> Any:
    try:
        import torch

        return torch.empty((0, 64, 64, 3), dtype=torch.float32)
    except Exception:
        return []
