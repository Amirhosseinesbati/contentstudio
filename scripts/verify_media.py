"""Render and inspect one complete synthetic media batch without external services."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from contentstudio.rendering import render_carousel, render_clip  # noqa: E402


def ffmpeg_path() -> Path:
    configured = os.getenv("CONTENTSTUDIO_FFMPEG")
    local = ROOT / "tmp" / "ffmpeg-package" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"
    candidate = configured or shutil.which("ffmpeg") or (str(local) if local.is_file() else None)
    if not candidate:
        raise RuntimeError("FFmpeg missing; set CONTENTSTUDIO_FFMPEG")
    return Path(candidate).resolve()


def inspect_media(ffmpeg: Path, path: Path, decode: bool = True) -> dict:
    info = subprocess.run([str(ffmpeg), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", info.stderr)
    dimensions = re.search(r"Video: .*?(\d{3,4})x(\d{3,4})", info.stderr)
    if not match or not dimensions or "Audio:" not in info.stderr:
        raise RuntimeError(f"Media metadata incomplete: {path}")
    duration_ms = round((int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])) * 1000)
    if decode:
        result = subprocess.run([str(ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"],
                                capture_output=True, text=True, timeout=180)
        if result.returncode or result.stderr.strip():
            raise RuntimeError(f"Media decode failed: {path}: {result.stderr[-500:]}")
    return {"path": str(path.resolve()), "duration_ms": duration_ms,
            "width": int(dimensions[1]), "height": int(dimensions[2]), "bytes": path.stat().st_size,
            "audio_present": True, "full_decode_ok": decode}


def main(output_dir: Path) -> None:
    ffmpeg = ffmpeg_path()
    os.environ["CONTENTSTUDIO_FFMPEG"] = str(ffmpeg)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    presentations = []
    for key in ("onboarding", "privacy", "energy"):
        media_path = ROOT / "fixtures" / "media" / key / "presentation.mp4"
        presentations.append(inspect_media(ffmpeg, media_path))
        if not 480_000 <= presentations[-1]["duration_ms"] <= 720_000:
            raise RuntimeError(f"Presentation duration outside 8-12 minutes: {key}")
    source = json.loads((ROOT / "fixtures" / "sources" / "01-onboarding.json").read_text(encoding="utf-8"))
    source_media = ROOT / "fixtures" / source["media_path"]
    selected = [source["segments"][index] for index in (1, 4, 7, 10, 13, 16, 18)]
    slides = [{"heading": f"Decision {index + 1}: inspect the source",
               "body": segment["text"].split(". ")[1][:225] if ". " in segment["text"] else segment["text"][:225],
               "source_segment_ids": [f"onboarding-{source['segments'].index(segment):02d}"]}
              for index, segment in enumerate(selected)]
    carousel_started = time.perf_counter()
    carousel = render_carousel(slides, "A calmer first 30 days", output_dir / "carousel")
    carousel_wall_ms = round((time.perf_counter() - carousel_started) * 1000)
    clips = []
    for ordinal, segment_index in enumerate((1, 4, 7), start=1):
        segment = source["segments"][segment_index]
        clip_started = time.perf_counter()
        rendered = render_clip(source_media,
                               {"start_ms": segment["start_ms"], "end_ms": segment["end_ms"]},
                               source["segments"], f"Source decision {ordinal}", output_dir / f"clip-{ordinal:02d}")
        metadata = inspect_media(ffmpeg, Path(rendered["mp4_path"]))
        if not 20_000 <= metadata["duration_ms"] <= 60_000 or (metadata["width"], metadata["height"]) != (720, 1280):
            raise RuntimeError(f"Clip duration or dimensions invalid: {ordinal}")
        clips.append({**metadata, "subtitle_path": rendered["subtitle_path"],
                      "render_wall_ms": round((time.perf_counter() - clip_started) * 1000)})
    result = {"label": "Synthetic demo render verification", "presentations": presentations,
              "carousel": {"slide_count": len(carousel["png_paths"]), "png_paths": carousel["png_paths"],
                           "pdf_path": carousel["pdf_path"], "render_wall_ms": carousel_wall_ms},
              "clips": clips, "total_wall_ms": round((time.perf_counter() - started) * 1000),
              "environment": "Windows local; FFmpeg 7.1 binary from temporary imageio-ffmpeg 0.6.0 install",
              "limits": "Decode and metadata verified. Human review of every slide/frame and audible boundaries is separate."}
    results_path = ROOT / "evals" / "results" / "render_qa.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"presentation_count": len(presentations), "slide_count": len(carousel["png_paths"]),
                      "clip_count": len(clips), "total_wall_ms": result["total_wall_ms"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "render-qa")
    args = parser.parse_args()
    main(args.output_dir)
