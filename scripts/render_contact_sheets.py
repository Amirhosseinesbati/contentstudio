"""Create compact visual QA sheets from already rendered demo output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from verify_media import ROOT, ffmpeg_path


OUTPUT = ROOT / "output" / "render-qa"


def sheet(paths: list[Path], columns: int, thumb: tuple[int, int], target: Path) -> None:
    gap, label_height = 24, 36
    rows = (len(paths) + columns - 1) // columns
    background = Image.new("RGB", (columns * (thumb[0] + gap) + gap,
                                   rows * (thumb[1] + label_height + gap) + gap), "#EEE8DF")
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype("C:/Windows/Fonts/DejaVuSans.ttf", 18)
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            image = source.convert("RGB")
        image.thumbnail(thumb)
        column, row = index % columns, index // columns
        x = gap + column * (thumb[0] + gap)
        y = gap + row * (thumb[1] + label_height + gap)
        background.paste(image, (x + (thumb[0] - image.width) // 2, y))
        draw.text((x, y + thumb[1] + 5), path.parent.name + " / " + path.stem, font=font, fill="#201D19")
    target.parent.mkdir(parents=True, exist_ok=True)
    background.save(target, "PNG")


def main() -> None:
    slides = sorted((OUTPUT / "carousel").glob("slide-*.png"))
    if len(slides) != 7:
        raise RuntimeError("Expected seven rendered carousel slides")
    sheet(slides, 4, (350, 438), OUTPUT / "carousel-contact-sheet.png")
    ffmpeg = ffmpeg_path()
    frames = []
    for clip_index in (1, 2, 3):
        clip = OUTPUT / f"clip-{clip_index:02d}" / "clip.mp4"
        for seconds, label in ((0.5, "title"), (6, "caption"), (22, "context")):
            frame = OUTPUT / f"clip-{clip_index:02d}-{label}.png"
            result = subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds),
                                     "-i", str(clip), "-frames:v", "1", str(frame)], capture_output=True, text=True, timeout=30)
            if result.returncode or not frame.is_file():
                raise RuntimeError(f"Cannot inspect clip {clip_index} at {seconds}s: {result.stderr}")
            frames.append(frame)
    sheet(frames, 3, (270, 480), OUTPUT / "clips-contact-sheet.png")
    print(OUTPUT / "carousel-contact-sheet.png")
    print(OUTPUT / "clips-contact-sheet.png")


if __name__ == "__main__":
    main()
