"""Validated, local rendering of approved editorial assets.

The caller authorizes the asset and chooses a workspace-scoped output directory.
This module accepts content data, never model-generated commands or HTML.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .config import get_settings


class RenderValidationError(ValueError):
    """An asset cannot be rendered safely or legibly."""


class RendererUnavailable(RuntimeError):
    """A required local renderer or codec is unavailable."""


PAPER = "#F7F2E9"
INK = "#201D19"
MUTED = "#6D675F"
ORANGE = "#D26634"
FONT_CANDIDATES = {
    "serif": [os.getenv("CONTENTSTUDIO_FONT_SERIF", ""),
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/DejaVuSerif.ttf"],
    "sans": [os.getenv("CONTENTSTUDIO_FONT_SANS", ""),
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/DejaVuSans.ttf"],
}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES[kind]:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RendererUnavailable(f"No {kind} TrueType font found; install DejaVu fonts or set CONTENTSTUDIO_FONT_{kind.upper()}")


def _wrapped(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                if font.getlength(word) > max_width:
                    raise RenderValidationError("A word is too wide for the slide layout")
                current = word
        lines.append(current)
    return lines


def _draw_wrapped(draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.FreeTypeFont,
                  x: int, y: int, line_height: int, fill: str) -> None:
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


def _plain(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise RenderValidationError(f"{label} must be text")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()
    if not text or len(text) > limit:
        raise RenderValidationError(f"{label} must contain 1-{limit} characters")
    return text


def _brand_tokens(brand: dict[str, Any] | None) -> tuple[str, str, str]:
    """Use only validated presentation tokens from the batch's pinned brand."""
    brand = brand or {}
    name = brand.get("name", "ContentStudio")
    name = _plain(name, 45, "brand name")
    rules = brand.get("rules") or {}
    accent = rules.get("accent", ORANGE) if isinstance(rules, dict) else ORANGE
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise RenderValidationError("brand accent must be a six-digit hex color")
    footer = ("Synthetic demo dataset · Review source context before publishing"
              if get_settings().mode == "demo" else "Review source context before publishing")
    return name, accent, footer


def _draw_slide(slide: dict, index: int, count: int, title: str,
                brand_name: str, accent: str, footer: str) -> Image.Image:
    image = Image.new("RGB", (1080, 1350), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, 1350), fill=accent)
    draw.text((86, 76), f"{brand_name.upper()}  /  FIELD NOTES", font=_font("sans", 26), fill=accent)
    draw.text((86, 126), _plain(title, 180, "carousel title").upper()[:62], font=_font("sans", 20), fill=MUTED)
    draw.line((86, 186, 994, 186), fill="#D5CFC3", width=2)

    heading = _plain(slide.get("heading"), 170, f"slide {index} heading")
    body = _plain(slide.get("body"), 900, f"slide {index} body")
    heading_lines: list[str] = []
    heading_font = _font("serif", 70)
    for size in range(70, 43, -2):
        candidate_font = _font("serif", size)
        candidate_lines = _wrapped(heading, candidate_font, 900)
        if len(candidate_lines) <= 4:
            heading_font, heading_lines = candidate_font, candidate_lines
            break
    if not heading_lines:
        raise RenderValidationError(f"slide {index} heading will not fit")
    heading_line_height = round(heading_font.size * 1.22)
    _draw_wrapped(draw, heading_lines, heading_font, 86, 270, heading_line_height, INK)
    body_top = 270 + len(heading_lines) * heading_line_height + 75
    available_height = 1040 - body_top
    body_font = _font("sans", 42)
    body_lines: list[str] = []
    for size in range(42, 29, -2):
        candidate_font = _font("sans", size)
        candidate_lines = _wrapped(body, candidate_font, 900)
        if len(candidate_lines) * round(size * 1.5) <= available_height:
            body_font, body_lines = candidate_font, candidate_lines
            break
    if not body_lines:
        raise RenderValidationError(f"slide {index} body will not fit")
    _draw_wrapped(draw, body_lines, body_font, 86, body_top, round(body_font.size * 1.5), INK)

    draw.line((86, 1162, 994, 1162), fill="#D5CFC3", width=2)
    source_ids = slide.get("source_segment_ids") or []
    if not isinstance(source_ids, list) or not source_ids:
        raise RenderValidationError(f"slide {index} has no source segment mapping")
    source_label = "SOURCE  " + ", ".join(str(item) for item in source_ids[:3])
    if len(source_label) > 72:
        source_label = source_label[:69] + "..."
    draw.text((86, 1194), source_label, font=_font("sans", 22), fill=MUTED)
    draw.text((86, 1240), footer, font=_font("sans", 18), fill=MUTED)
    draw.text((945, 1205), f"{index:02d}/{count:02d}", font=_font("sans", 24), fill=accent)
    return image


def render_carousel(slides: list[dict], title: str, output_dir: Path,
                    brand: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create one 1080x1350 PNG per slide and a matching multi-page PDF."""
    if not isinstance(slides, list) or not 6 <= len(slides) <= 8 or not all(isinstance(s, dict) for s in slides):
        raise RenderValidationError("A carousel requires 6-8 structured slides")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    brand_name, accent, footer = _brand_tokens(brand)
    images = [_draw_slide(slide, index + 1, len(slides), title, brand_name, accent, footer)
              for index, slide in enumerate(slides)]
    png_paths: list[str] = []
    for index, image in enumerate(images, start=1):
        path = output_dir / f"slide-{index:02d}.png"
        temp = output_dir / f"slide-{index:02d}.tmp.png"
        image.save(temp, "PNG", optimize=True)
        temp.replace(path)
        png_paths.append(str(path.resolve()))
    pdf_path = output_dir / "carousel.pdf"
    temp_pdf = output_dir / "carousel.tmp.pdf"
    document = canvas.Canvas(str(temp_pdf), pagesize=(540, 675), pageCompression=1)
    document.setTitle(title)
    document.setAuthor(brand_name)
    for image in images:
        document.drawImage(ImageReader(image), 0, 0, width=540, height=675)
        document.showPage()
    document.save()
    temp_pdf.replace(pdf_path)
    return {"png_paths": png_paths, "pdf_path": str(pdf_path.resolve())}


def _srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, fraction = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{fraction:03d}"


def _caption_chunks(text: str, max_words: int = 5) -> list[str]:
    tokens = text.split()
    return [" ".join(tokens[start:start + max_words]) for start in range(0, len(tokens), max_words)]


def _write_subtitles(segments: list[dict], start_ms: int, end_ms: int, target: Path) -> int:
    cues: list[tuple[int, int, str]] = []
    for segment in segments:
        try:
            begin = max(start_ms, int(segment["start_ms"]))
            finish = min(end_ms, int(segment["end_ms"]))
            text = _plain(segment["text"], 20_000, "transcript segment")
        except (KeyError, TypeError, ValueError) as exc:
            raise RenderValidationError("Segments need start_ms, end_ms, and text") from exc
        if finish <= begin:
            continue
        chunks = _caption_chunks(text)
        if not chunks:
            continue
        chunk_words = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = sum(chunk_words)
        cursor = begin
        for index, chunk in enumerate(chunks):
            next_cursor = finish if index == len(chunks) - 1 else begin + round((finish - begin) * sum(chunk_words[:index + 1]) / total_words)
            if next_cursor - cursor >= 300:
                cues.append((cursor - start_ms, next_cursor - start_ms, chunk))
            cursor = next_cursor
    if not cues:
        raise RenderValidationError("No transcript text overlaps the requested clip range")
    with target.open("w", encoding="utf-8") as stream:
        for index, (begin, finish, text) in enumerate(cues, start=1):
            stream.write(f"{index}\n{_srt_time(begin)} --> {_srt_time(finish)}\n{text}\n\n")
    return len(cues)


def _ffmpeg_binary() -> str:
    configured = os.getenv("CONTENTSTUDIO_FFMPEG")
    binary = configured or shutil.which("ffmpeg")
    if not binary or not Path(binary).exists():
        raise RendererUnavailable("FFmpeg is unavailable; set CONTENTSTUDIO_FFMPEG or install ffmpeg")
    return binary


def _has_video(ffmpeg: str, source_media: Path) -> bool:
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source_media)], capture_output=True, text=True, timeout=20)
    return bool(re.search(r"Stream #.*Video:", probe.stderr))


def _title_card(title: str, size: tuple[int, int], target: Path,
                brand_name: str, accent: str, footer: str) -> None:
    width, height = size
    image = Image.new("RGBA", size, INK)
    draw = ImageDraw.Draw(image)
    margin = round(width * .095)
    draw.rectangle((0, 0, round(width * .019), height), fill=accent)
    draw.text((margin, round(height * .20)), f"{brand_name.upper()}  /  VIDEO EXCERPT"[:48],
              font=_font("sans", round(width * .035)), fill=accent)
    heading = _plain(title, 180, "clip title")
    font = _font("serif", round(width * .080))
    lines = _wrapped(heading, font, width - 2 * margin)
    if len(lines) > 5:
        font = _font("serif", round(width * .065))
        lines = _wrapped(heading, font, width - 2 * margin)
    if len(lines) > 6:
        raise RenderValidationError("Clip title will not fit the title card")
    _draw_wrapped(draw, lines, font, margin, round(height * .32), round(font.size * 1.3), PAPER)
    draw.text((margin, round(height * .78)), footer,
              font=_font("sans", round(width * .025)), fill="#E7D8C8")
    image.save(target, "PNG")


def render_clip(source_media: Path, clip_range: dict, segments: list[dict], title: str,
                output_dir: Path, aspect_ratio: str = "9:16",
                brand: dict[str, Any] | None = None) -> dict[str, str]:
    """Render a 20-60 second MP4 with burned subtitles and a two-second title card.

    Caption timing is interpolated inside transcript segments. It is not word-level
    forced alignment, so editorial review remains required for final publication.
    """
    source_media = Path(source_media).resolve()
    if not source_media.is_file() or source_media.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a"}:
        raise RenderValidationError("Source media is missing or has an unsupported type")
    try:
        start_ms, end_ms = int(clip_range["start_ms"]), int(clip_range["end_ms"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderValidationError("Clip range needs integer start_ms and end_ms") from exc
    if start_ms < 0 or not 20_000 <= end_ms - start_ms <= 60_000:
        raise RenderValidationError("Clip duration must be 20-60 seconds")
    sizes = {"9:16": (720, 1280), "1:1": (1080, 1080), "16:9": (1280, 720)}
    if aspect_ratio not in sizes:
        raise RenderValidationError("Aspect ratio must be 9:16, 1:1, or 16:9")
    width, height = sizes[aspect_ratio]
    ffmpeg = _ffmpeg_binary()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = output_dir / "captions.srt"
    _write_subtitles(segments, start_ms, end_ms, subtitle_path)
    title_path = output_dir / "title-card.png"
    brand_name, accent, footer = _brand_tokens(brand)
    _title_card(title, (width, height), title_path, brand_name, accent, footer)
    output_path = output_dir / "clip.mp4"
    temp_path = output_dir / "clip.tmp.mp4"
    duration_s = (end_ms - start_ms) / 1000
    source_is_video = _has_video(ffmpeg, source_media)
    if source_is_video:
        inputs = ["-ss", f"{start_ms / 1000:.3f}", "-i", str(source_media), "-loop", "1", "-i", title_path.name]
        # Keep the full source frame visible. Cropping a slide can remove a caveat or negation.
        base = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x201d19,setsar=1[base];")
        title_input = "[1:v]"
        audio_map = "0:a:0?"
    else:
        inputs = ["-f", "lavfi", "-i", f"color=c=0x201d19:s={width}x{height}:r=25",
                  "-ss", f"{start_ms / 1000:.3f}", "-i", str(source_media), "-loop", "1", "-i", title_path.name]
        base = "[0:v]format=yuv420p[base];"
        title_input = "[2:v]"
        audio_map = "1:a:0"
    # Burn captions after the opening card. Otherwise the card obscures the first
    # spoken words while audio is already playing.
    filter_graph = (
        f"{base}[base]{title_input}overlay=0:0:enable='lt(t,2)'[with_title];"
        f"[with_title]subtitles=captions.srt:force_style='FontName=DejaVu Sans,FontSize=11,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,"
        f"MarginV=25,Alignment=2',format=yuv420p[video]"
    )
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
               "-filter_complex", filter_graph, "-map", "[video]", "-map", audio_map,
               "-t", f"{duration_s:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temp_path)]
    try:
        result = subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RendererUnavailable(f"FFmpeg could not finish the clip: {exc}") from exc
    if result.returncode != 0 or not temp_path.is_file() or temp_path.stat().st_size == 0:
        raise RendererUnavailable(f"FFmpeg failed: {result.stderr[-800:]}")
    temp_path.replace(output_path)
    return {"mp4_path": str(output_path.resolve()), "subtitle_path": str(subtitle_path.resolve())}
