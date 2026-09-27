from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def watermark_position_for(source: Path) -> str:
    """Return the fixed operator-approved placement for a media file."""
    return "Bottom Left" if source.suffix.lower() in IMAGE_EXTENSIONS else "Top Right"


def collect_media(paths: list[str | Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        candidates = (
            path.rglob("*") if path.is_dir() else [path]
        )
        for candidate in candidates:
            if (
                candidate.is_file()
                and candidate.suffix.lower() in MEDIA_EXTENSIONS
            ):
                key = os.path.normcase(str(candidate.resolve()))
                if key not in seen:
                    seen.add(key)
                    found.append(candidate.resolve())
    return found


def unique_output_path(output_folder: Path, source: Path, output_suffix: str | None = None) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    suffix = output_suffix or source.suffix.lower()
    candidate = output_folder / f"{source.stem}_RGV{suffix}"
    counter = 2
    while candidate.exists():
        candidate = output_folder / f"{source.stem}_RGV_{counter}{suffix}"
        counter += 1
    return candidate


def _watermark_size(base_size: tuple[int, int], logo_size: tuple[int, int], percent: int) -> tuple[int, int]:
    target_width = max(1, round(base_size[0] * percent / 100))
    target_height = max(1, round(logo_size[1] * target_width / logo_size[0]))
    max_height = max(1, round(base_size[1] * 0.5))
    if target_height > max_height:
        target_height = max_height
        target_width = max(1, round(logo_size[0] * target_height / logo_size[1]))
    return target_width, target_height


def watermark_coordinates(
    canvas: tuple[int, int],
    overlay: tuple[int, int],
    position: str,
    margin: int,
) -> tuple[int, int]:
    left = margin
    top = margin
    right = max(0, canvas[0] - overlay[0] - margin)
    bottom = max(0, canvas[1] - overlay[1] - margin)
    return {
        "Top Left": (left, top),
        "Top Right": (right, top),
        "Bottom Left": (left, bottom),
        "Bottom Right": (right, bottom),
    }.get(position, (right, bottom))


def process_image(
    source: Path,
    logo_path: Path,
    destination: Path,
    position: str,
    size_percent: int,
    opacity_percent: int,
    margin: int,
) -> None:
    with Image.open(source) as original, Image.open(logo_path) as logo_original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
        logo = logo_original.convert("RGBA")
        # Image.thumbnail() never enlarges a small source logo. resize() is
        # intentional here because "Size" represents a percentage of the
        # output image width regardless of the logo's original pixel size.
        logo = logo.resize(
            _watermark_size(image.size, logo.size, size_percent),
            Image.Resampling.LANCZOS,
        )
        alpha = logo.getchannel("A")
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity_percent / 100)
        logo.putalpha(alpha)
        xy = watermark_coordinates(image.size, logo.size, position, margin)
        image.alpha_composite(logo, xy)

        destination.parent.mkdir(parents=True, exist_ok=True)
        extension = destination.suffix.lower()
        if extension in {".jpg", ".jpeg"}:
            image.convert("RGB").save(
                destination,
                quality=95,
                optimize=True,
                exif=original.getexif().tobytes(),
            )
        elif extension == ".webp":
            image.save(destination, quality=95, method=6)
        else:
            image.save(destination, optimize=True)


def find_ffmpeg() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "ffmpeg.exe")
    candidates.extend(
        [
            Path(__file__).resolve().parents[1] / "ffmpeg.exe",
            Path.cwd() / "ffmpeg.exe",
        ]
    )
    located = shutil.which("ffmpeg")
    if located:
        candidates.append(Path(located))
    try:
        import imageio_ffmpeg

        candidates.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except (ImportError, RuntimeError, OSError):
        pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _escape_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def process_video(
    source: Path,
    logo_path: Path,
    destination: Path,
    position: str,
    size_percent: int,
    opacity_percent: int,
    margin: int,
    progress: Callable[[float], None] | None = None,
) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg or place ffmpeg.exe in the "
            "RGV Operations Suite folder, then try again."
        )

    x, y = {
        "Top Left": (str(margin), str(margin)),
        "Top Right": (f"main_w-overlay_w-{margin}", str(margin)),
        "Bottom Left": (str(margin), f"main_h-overlay_h-{margin}"),
        "Bottom Right": (f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"),
    }.get(position, (f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"))
    opacity = opacity_percent / 100
    filter_graph = (
        f"[1:v]format=rgba,colorchannelmixer=aa={opacity:.2f}[logo];"
        # rw is the width of the reference input (the source video). main_w
        # refers to the logo itself in FFmpeg 7 and made video watermarks much
        # smaller than the equivalent percentage on photos.
        f"[logo][0:v]scale2ref=w=rw*{size_percent / 100:.4f}:h=ow/mdar[wm][base];"
        f"[base][wm]overlay={x}:{y}:format=auto:shortest=1[outv]"
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-loop",
        "1",
        "-i",
        str(logo_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[outv]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "FFmpeg could not export this video.")
    if progress:
        progress(1.0)
