"""Join locally synthesized segment WAVs and render an authored slide presentation.

Windows SAPI creates the narration; this script measures each actual WAV boundary.
It does not claim word-level forced alignment or natural human speech.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from generate_demo_data import TOPICS


TOPIC_BY_KEY = {topic[0]: topic for topic in TOPICS}
PAPER, INK, ORANGE, MUTED = "#F7F2E9", "#201D19", "#D26634", "#6D675F"


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    names = ("DejaVuSerif.ttf", "DejaVuSans.ttf")
    name = names[0 if kind == "serif" else 1]
    for path in (Path("C:/Windows/Fonts") / name, Path("/usr/share/fonts/truetype/dejavu") / name):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("DejaVu fonts are required to generate demo slides")


def wrap(text: str, chosen: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if chosen.getlength(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def slide(path: Path, eyebrow: str, heading: str, body: str, number: int, count: int) -> None:
    image = Image.new("RGB", (1280, 720), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 14, 720), fill=ORANGE)
    draw.text((84, 62), "CONTENTSTUDIO  /  SYNTHETIC PRESENTATION", font=font("sans", 24), fill=ORANGE)
    draw.text((84, 113), eyebrow.upper()[:80], font=font("sans", 22), fill=MUTED)
    draw.line((84, 164, 1196, 164), fill="#D2CCC1", width=2)
    heading_font = font("serif", 60)
    heading_lines = wrap(heading, heading_font, 1040)
    if len(heading_lines) > 3:
        heading_font = font("serif", 50)
        heading_lines = wrap(heading, heading_font, 1040)
    if len(heading_lines) > 3:
        raise ValueError(f"Slide heading does not fit: {heading}")
    y = 225
    for line in heading_lines:
        draw.text((84, y), line, font=heading_font, fill=INK)
        y += round(heading_font.size * 1.20)
    y += 20
    body_font = font("sans", 29)
    body_lines = wrap(body, body_font, 1060)
    if len(body_lines) > 4:
        body_font = font("sans", 25)
        body_lines = wrap(body, body_font, 1060)
    if y + len(body_lines) * round(body_font.size * 1.4) > 625:
        raise ValueError(f"Slide body does not fit: {heading}")
    for line in body_lines:
        draw.text((84, y), line, font=body_font, fill=INK)
        y += round(body_font.size * 1.4)
    draw.line((84, 652, 1196, 652), fill="#D2CCC1", width=2)
    draw.text((84, 673), "Fictional source · locally synthesized narration", font=font("sans", 18), fill=MUTED)
    draw.text((1110, 668), f"{number:02d}/{count:02d}", font=font("sans", 22), fill=ORANGE)
    image.save(path, "PNG", optimize=True)


def main(source_path: Path, wav_dir: Path, ffmpeg: Path, voice: str, rate: int) -> None:
    if not ffmpeg.is_file():
        raise FileNotFoundError(ffmpeg)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    key = source["source_key"]
    topic = TOPIC_BY_KEY[key]
    segments = source["segments"]
    media_dir = source_path.parents[1] / "media" / key
    media_dir.mkdir(parents=True, exist_ok=True)
    narration = media_dir / "narration.wav"
    position_frames = 0
    with wave.open(str(narration), "wb") as combined:
        for index, segment in enumerate(segments):
            path = wav_dir / f"segment-{index:02d}.wav"
            with wave.open(str(path), "rb") as part:
                params = part.getparams()
                if index == 0:
                    combined.setparams(params)
                    frame_rate, channels, sample_width = params.framerate, params.nchannels, params.sampwidth
                elif (params.framerate, params.nchannels, params.sampwidth) != (frame_rate, channels, sample_width):
                    raise ValueError("Speech WAV formats differ across segments")
                segment["start_ms"] = round(position_frames / frame_rate * 1000)
                frames = part.readframes(params.nframes)
                combined.writeframes(frames)
                position_frames += params.nframes
                segment["end_ms"] = round(position_frames / frame_rate * 1000)
            pause_frames = round(frame_rate * 0.18)
            combined.writeframes(b"\x00" * pause_frames * channels * sample_width)
            position_frames += pause_frames
    duration_ms = round(position_frames / frame_rate * 1000)
    if not 480_000 <= duration_ms <= 720_000:
        raise ValueError(f"Narration is {duration_ms / 60_000:.2f} minutes; expected 8-12. Adjust synthesis rate and retry.")

    slide_specs = [(source["title"], topic[3])]
    for area, observation, _example, decision, _caveat in topic[4]:
        slide_specs.append((area.capitalize(), f"In {topic[2]}, {observation}. A practical next step: {decision}."))
    slide_specs.append(("Check the source context", "Every example is fictional. Verify quotations, caveats, and corrections before publication."))
    for index, (heading, body) in enumerate(slide_specs):
        slide(media_dir / f"slide-{index:02d}.png", source["title"], heading, body, index + 1, len(slide_specs))

    boundaries = [0, segments[1]["start_ms"]]
    for facet in range(1, 6):
        boundaries.append(segments[1 + facet * 3]["start_ms"])
    boundaries.append(segments[-1]["start_ms"])
    boundaries.append(duration_ms)
    if len(boundaries) != len(slide_specs) + 1:
        raise AssertionError("Slide timing and slide count differ")
    concat = media_dir / "slides.ffconcat"
    with concat.open("w", encoding="utf-8") as stream:
        stream.write("ffconcat version 1.0\n")
        for index in range(len(slide_specs)):
            stream.write(f"file slide-{index:02d}.png\n")
            stream.write(f"duration {(boundaries[index + 1] - boundaries[index]) / 1000:.3f}\n")
        stream.write(f"file slide-{len(slide_specs) - 1:02d}.png\n")

    output = media_dir / "presentation.mp4"
    temp_output = media_dir / "presentation.tmp.mp4"
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-safe", "0", "-f", "concat",
               "-i", concat.name, "-i", narration.name, "-vf", "fps=2,format=yuv420p",
               "-t", f"{duration_ms / 1000:.3f}", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(temp_output)]
    result = subprocess.run(command, cwd=media_dir, capture_output=True, text=True, timeout=600)
    if result.returncode or not temp_output.is_file() or not temp_output.stat().st_size:
        raise RuntimeError(f"FFmpeg presentation render failed: {result.stderr[-1000:]}")
    temp_output.replace(output)
    probe = subprocess.run([str(ffmpeg), "-hide_banner", "-i", str(output)], capture_output=True, text=True, timeout=30)
    if "Video:" not in probe.stderr or "Audio:" not in probe.stderr:
        raise RuntimeError("Rendered presentation is missing video or audio")
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not match:
        raise RuntimeError("Could not verify presentation duration")
    measured_ms = round((int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])) * 1000)
    if abs(measured_ms - duration_ms) > 1000:
        raise RuntimeError(f"Presentation duration mismatch: audio {duration_ms}, video {measured_ms}")
    narration.unlink()
    source.update({
        "kind": "owned_media", "rights_status": "owned_synthetic_media",
        "provenance": "Authored fictional script, locally synthesized Windows SAPI narration and code-generated slides; no third-party footage",
        "media_path": f"media/{key}/presentation.mp4", "duration_ms": measured_ms,
        "timestamp_method": "Measured per-segment WAV boundaries; caption words remain estimated inside each segment",
    })
    source_path.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (media_dir / "provenance.json").write_text(json.dumps({
        "label": "Synthetic demo presentation", "source_key": key, "narrator_voice": voice,
        "speech_rate_setting": rate, "duration_ms": measured_ms, "width": 1280, "height": 720,
        "segment_count": len(segments), "media_sha256": digest, "method": "Windows SAPI + Pillow slides + FFmpeg",
        "limitations": "Synthetic narration, not a human webinar; transcript timing measured at segment boundaries only",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{key}: {measured_ms / 60_000:.2f} min, {output.stat().st_size / 1_000_000:.1f} MB, sha256 {digest[:16]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--wav-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--rate", type=int, required=True)
    args = parser.parse_args()
    main(args.source.resolve(), args.wav_dir.resolve(), args.ffmpeg.resolve(), args.voice, args.rate)
