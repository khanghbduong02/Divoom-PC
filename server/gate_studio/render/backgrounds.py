"""Background images from the media folder, fitted to a 128x128 panel."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..models import Background

RGB = tuple[int, int, int]


@lru_cache(maxsize=48)
def _open_cached(path: str, _mtime: float) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return image.convert("RGB")


def load_media(media_dir: Path | None, name: str | None) -> Image.Image | None:
    if media_dir is None or not name:
        return None
    path = Path(media_dir) / Path(name).name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    try:
        return _open_cached(str(path), mtime)
    except (OSError, ValueError):
        return None


def fit_image(
    image: Image.Image,
    size: tuple[int, int],
    mode: str,
    background: RGB = (0, 0, 0),
) -> Image.Image:
    target_w, target_h = size
    width, height = image.size
    if width <= 0 or height <= 0:
        return Image.new("RGB", size, background)

    if mode == "stretch":
        return image.resize((target_w, target_h), Image.LANCZOS)

    if mode == "fit":
        ratio = min(target_w / width, target_h / height)
        resized = image.resize(
            (max(1, round(width * ratio)), max(1, round(height * ratio))),
            Image.LANCZOS,
        )
        canvas = Image.new("RGB", size, background)
        canvas.paste(resized, ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
        return canvas

    ratio = max(target_w / width, target_h / height)
    resized = image.resize(
        (max(1, round(width * ratio)), max(1, round(height * ratio))),
        Image.LANCZOS,
    )
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def dim(image: Image.Image, amount: int) -> Image.Image:
    if amount <= 0:
        return image
    overlay = Image.new("RGB", image.size, (0, 0, 0))
    return Image.blend(image, overlay, min(100, amount) / 100)
