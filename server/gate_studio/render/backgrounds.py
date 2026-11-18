"""Background images from the media folder, fitted to a 128x128 panel."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..models import Background

RGB = tuple[int, int, int]


@lru_cache(maxsize=16)
def _open_animation_cached(path: str, _mtime: float) -> tuple[tuple[Image.Image, ...], tuple[int, ...]]:
    """Decode a still or animated GIF once, with per-frame delays."""
    with Image.open(path) as image:
        image.load()
        frames: list[Image.Image] = []
        delays: list[int] = []
        count = max(1, int(getattr(image, "n_frames", 1)))
        for index in range(count):
            image.seek(index)
            frames.append(image.convert("RGB"))
            try:
                delay = int(image.info.get("duration") or 100)
            except (TypeError, ValueError):
                delay = 100
            delays.append(max(30, min(1000, delay)))
        return tuple(frames), tuple(delays)


def load_animation(
    media_dir: Path | None,
    name: str | None,
    *,
    max_frames: int = 40,
) -> list[tuple[Image.Image, int]]:
    """Return ``(RGB frame, delay_ms)`` pairs for a still or animated image."""
    if media_dir is None or not name:
        return []
    path = Path(media_dir) / Path(name).name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    try:
        frames, delays = _open_animation_cached(str(path), mtime)
    except (OSError, ValueError):
        return []
    if len(frames) > max_frames:
        # Sample across the animation rather than dropping the end.
        if max_frames <= 1:
            indexes = [0]
        else:
            indexes = [
                round(index * (len(frames) - 1) / (max_frames - 1))
                for index in range(max_frames)
            ]
        frames = tuple(frames[index] for index in indexes)
        delays = tuple(delays[index] for index in indexes)
    return list(zip(frames, delays))


def load_media(media_dir: Path | None, name: str | None) -> Image.Image | None:
    frames = load_animation(media_dir, name, max_frames=1)
    return frames[0][0] if frames else None


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
