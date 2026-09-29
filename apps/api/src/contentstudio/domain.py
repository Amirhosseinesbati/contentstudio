import hashlib
import json
import re
from collections.abc import Iterable

QUOTE_PATTERN = re.compile(r"[“\"]([^”\"]{3,})[”\"]")
NUMBER_PATTERN = re.compile(r"(?<!\w)\d[\d,.%]*")
WORD_PATTERN = re.compile(r"\b\w+(?:[-'’]\w+)*\b")


def _word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def _paragraph_count(text: str) -> int:
    return sum(bool(part.strip()) for part in re.split(r"\n\s*\n", text.strip()))


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def content_hash(
    title: str, text: str, slides: list, clip_range: dict | None, source_ids: list[str]
) -> str:
    return canonical_hash(
        {
            "title": title,
            "text": text,
            "slides": slides,
            "clip_range": clip_range,
            "source_segment_ids": source_ids,
        }
    )


def validate_asset(
    asset: dict, segments: Iterable[dict], prohibited_phrases: list[str] | None = None
) -> list[str]:
    """Check cited spans; deterministic evidence checks cannot establish overall truth."""
    segment_list = list(segments)
    by_id = {s["id"]: s for s in segment_list}
    source_ids = asset.get("source_segment_ids") or []
    slides = asset.get("slides") if isinstance(asset.get("slides"), list) else []
    warnings: list[str] = []
    if not source_ids:
        warnings.append("Missing source segment evidence")
    if any(sid not in by_id for sid in source_ids):
        warnings.append("Unknown source segment evidence")
    cited = " ".join(by_id[sid]["text"] for sid in source_ids if sid in by_id)
    rendered = " ".join(
        [asset.get("title") or "", asset.get("text") or ""]
        + [
            f"{slide.get('heading', '')} {slide.get('body', '')}"
            for slide in slides if isinstance(slide, dict)
        ]
    )
    for quote in QUOTE_PATTERN.findall(rendered):
        if quote not in cited:
            warnings.append(f"Quote not found verbatim in cited transcript: {quote[:60]}")
    source_numbers = set(NUMBER_PATTERN.findall(cited))
    for number in set(NUMBER_PATTERN.findall(rendered)):
        if number not in source_numbers:
            warnings.append(f"Number lacks cited transcript evidence: {number}")
    if asset.get("asset_type") == "carousel":
        for index, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                warnings.append(f"Slide {index} must contain heading, body, and source evidence")
                continue
            if not all(isinstance(slide.get(field), str) and slide[field].strip() for field in ("heading", "body")):
                warnings.append(f"Slide {index} needs nonempty heading and body text")
            slide_ids = slide.get("source_segment_ids") or []
            if not isinstance(slide_ids, list) or any(not isinstance(sid, str) for sid in slide_ids):
                warnings.append(f"Slide {index} source evidence must be a list of segment IDs")
                slide_ids = []
            if not slide_ids:
                warnings.append(f"Slide {index} is missing source segment evidence")
            if any(sid not in by_id for sid in slide_ids):
                warnings.append(f"Slide {index} has unknown source segment evidence")
            if any(sid not in source_ids for sid in slide_ids):
                warnings.append(f"Slide {index} cites evidence outside the asset source map")
            slide_source = " ".join(by_id[sid]["text"] for sid in slide_ids if sid in by_id)
            slide_text = f"{slide.get('heading', '')} {slide.get('body', '')}"
            for quote in QUOTE_PATTERN.findall(slide_text):
                if quote not in slide_source:
                    warnings.append(f"Slide {index} quote is absent from its cited transcript: {quote[:60]}")
            slide_numbers = set(NUMBER_PATTERN.findall(slide_source))
            for number in set(NUMBER_PATTERN.findall(slide_text)):
                if number not in slide_numbers:
                    warnings.append(f"Slide {index} number lacks its cited transcript evidence: {number}")
    for phrase in prohibited_phrases or []:
        if phrase and phrase.lower() in rendered.lower():
            warnings.append(f"Brand rule prohibits phrase: {phrase}")
    asset_type = asset.get("asset_type")
    if asset_type in {"article", "newsletter", "social"}:
        label = asset_type.capitalize()
        title = asset.get("title")
        body = asset.get("text")
        if not isinstance(title, str) or not title.strip():
            warnings.append(f"{label} needs a nonempty title")
        if not isinstance(body, str) or not body.strip():
            warnings.append(f"{label} needs a nonempty body")
        else:
            words = _word_count(body)
            if asset_type in {"article", "newsletter"}:
                minimum, maximum = (700, 1000) if asset_type == "article" else (250, 450)
                source_words = _word_count(" ".join(s.get("text", "") for s in segment_list))
                cited_words = _word_count(
                    " ".join(by_id[sid]["text"] for sid in source_ids if sid in by_id)
                )
                # A short source cannot support a full-length draft. Its cited material
                # sets the floor; substantial sources keep the normal channel target.
                effective_minimum = minimum if source_words >= minimum else min(minimum, cited_words)
                if words < effective_minimum:
                    warnings.append(
                        f"{label} body is too short: {words} words; minimum {effective_minimum} for this source"
                    )
                if words > maximum:
                    warnings.append(f"{label} body exceeds {maximum} words")
                if len(segment_list) >= 2 and _paragraph_count(body) < 2:
                    warnings.append(f"{label} body needs at least two paragraphs")
            else:
                if len(body.strip()) > 500:
                    warnings.append("Social post exceeds 500 characters")
                if words > 100:
                    warnings.append("Social post exceeds 100 words")
    if asset.get("asset_type") == "clip":
        clip = asset.get("clip_range") or {}
        start, end = clip.get("start_ms", -1), clip.get("end_ms", -1)
        if start < 0 or end <= start or not 20_000 <= end - start <= 60_000:
            warnings.append("Clip must be 20–60 seconds with a valid range")
        overlapping = [
            s
            for s in segment_list
            if s["id"] in source_ids and s["start_ms"] < end and s["end_ms"] > start
        ]
        if not overlapping:
            warnings.append("Clip range does not overlap cited source")
        elif start != min(s["start_ms"] for s in overlapping) or end != max(
            s["end_ms"] for s in overlapping
        ):
            warnings.append("Clip cuts through a cited transcript segment; review full context")
    if asset.get("asset_type") == "carousel" and not 6 <= len(slides) <= 8:
        warnings.append("Carousel requires 6–8 slides")
    return warnings


def csv_safe(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
