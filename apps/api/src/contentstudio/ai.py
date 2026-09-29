"""Bounded AI task. n8n controls the surrounding business workflow."""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from typing import TypedDict

from pydantic import BaseModel, Field

from .config import get_settings
from .domain import validate_asset


class GeneratedAsset(BaseModel):
    asset_type: str
    title: str = Field(max_length=250)
    text: str = ""
    slides: list[dict] = Field(default_factory=list)
    clip_range: dict | None = None
    source_segment_ids: list[str]
    warnings: list[str] = Field(default_factory=list)


class GeneratedBundle(BaseModel):
    claims: list[dict]
    assets: list[GeneratedAsset]


class AIState(TypedDict, total=False):
    segments: list[dict]
    brand: dict
    topic: str
    claims: list[dict]
    plan: list[dict]
    assets: list[dict]
    warnings: list[str]
    revision_count: int


def _excerpt(segment: dict, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", segment["text"]).strip()
    return text[:limit].rsplit(" ", 1)[0] if len(text) > limit else text


def _select_segments(segments: list[dict], count: int) -> list[dict]:
    if not segments:
        return []
    if len(segments) <= count:
        return segments
    indexes = sorted(set(round(i * (len(segments) - 1) / (count - 1)) for i in range(count)))
    return [segments[i] for i in indexes]


def _fixture_asset(kind: str, ordinal: int, segments: list[dict], topic: str) -> dict:
    selected = _select_segments(segments, 8)
    if not selected:
        raise ValueError("Cannot generate from an empty transcript")
    anchor = selected[min(ordinal, len(selected) - 1)]
    headline = _excerpt(anchor, 75).rstrip(".,;: ")
    if kind == "article":
        article_segments = selected[:6]
        return GeneratedAsset(
            asset_type=kind,
            title=f"{topic}: an evidence-led perspective",
            text="\n\n".join(s["text"].strip() for s in article_segments),
            source_segment_ids=[s["id"] for s in article_segments],
        ).model_dump()
    if kind == "newsletter":
        newsletter_segments = selected[:3]
        return GeneratedAsset(
            asset_type=kind,
            title=f"Field notes on {topic}",
            text="Hello,\n\n"
            + "\n\n".join(s["text"].strip() for s in newsletter_segments)
            + "\n\nWhat should we examine next?",
            source_segment_ids=[s["id"] for s in newsletter_segments],
        ).model_dump()
    if kind == "social":
        return GeneratedAsset(
            asset_type=kind,
            title=f"Field note: {headline}",
            text=_excerpt(anchor, 400),
            source_segment_ids=[anchor["id"]],
        ).model_dump()
    if kind == "carousel":
        slides = [
            {
                "heading": _excerpt(s, 70).rstrip(".,;: "),
                "body": _excerpt(s, 230),
                "source_segment_ids": [s["id"]],
            }
            for s in selected[:7]
        ]
        return GeneratedAsset(
            asset_type=kind,
            title=f"A practical guide to {topic}",
            slides=slides,
            source_segment_ids=[s["id"] for s in selected[:7]],
        ).model_dump()
    if kind == "clip":
        eligible = [s for s in segments if 20_000 <= s["end_ms"] - s["start_ms"] <= 60_000]
        if not eligible:
            raise ValueError(
                "No whole transcript segment fits a 20–60 second clip; manual selection is required"
            )
        choices = _select_segments(eligible, min(3, len(eligible)))
        clip_segment = choices[min(ordinal, len(choices) - 1)]
        return GeneratedAsset(
            asset_type=kind,
            title=f"Excerpt: {_excerpt(clip_segment, 55)}",
            text=clip_segment["text"].strip(),
            clip_range={
                "start_ms": clip_segment["start_ms"],
                "end_ms": clip_segment["end_ms"],
                "aspect_ratio": "9:16",
            },
            source_segment_ids=[clip_segment["id"]],
        ).model_dump()
    raise ValueError(f"Unsupported asset type: {kind}")


def _connected_asset(
    kind: str, ordinal: int, segments: list[dict], topic: str, brand: dict, feedback: str = ""
) -> dict:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key or not settings.model_id:
        raise RuntimeError("Connected model requires OPENAI_API_KEY and MODEL_ID")
    model = ChatOpenAI(
        model=settings.model_id,
        api_key=settings.openai_api_key,
        timeout=45,
        max_retries=2,
        temperature=0,
    )
    structured = model.with_structured_output(GeneratedAsset)
    selected = _select_segments(segments, 12)
    prompt = {
        "task": "Create exactly one review draft from owned transcript. Use only the supplied segment IDs for evidence. Any quoted string must occur exactly in a cited segment. Never invent numbers, speaker identities, or factual attributions. The output is untrusted and will be checked deterministically.",
        "asset_type": kind,
        "ordinal": ordinal,
        "topic": topic,
        "brand": brand,
        "segments": selected,
        "format": {
            "article": "700-1000 words",
            "newsletter": "250-450 words",
            "social": "one concise post",
            "carousel": "6-8 slides with heading, body, source_segment_ids",
            "clip": "20-60 second range in milliseconds with 9:16 aspect_ratio",
        }[kind],
        "feedback": feedback,
    }
    import json

    result = structured.invoke(json.dumps(prompt, ensure_ascii=False))
    data = (
        result.model_dump()
        if isinstance(result, GeneratedAsset)
        else GeneratedAsset.model_validate(result).model_dump()
    )
    if data["asset_type"] != kind:
        raise ValueError("Model returned a different asset type")
    return data


def build_graph():
    from langgraph.graph import END, START, StateGraph

    def analyze(state: AIState) -> dict:
        first = state["segments"][0]["text"]
        words = re.findall(r"[\w-]+", first)
        topic = " ".join(words[:5]).strip() or "the discussion"
        return {"topic": topic[:70]}

    def build_claims(state: AIState) -> dict:
        claims = []
        for segment in state["segments"]:
            if re.search(r"\d", segment["text"]):
                claims.append(
                    {
                        "text": _excerpt(segment, 350),
                        "source_segment_ids": [segment["id"]],
                        "verification_status": "verified",
                    }
                )
            if len(claims) >= 16:
                break
        if not claims:
            for segment in _select_segments(state["segments"], 5):
                claims.append(
                    {
                        "text": _excerpt(segment, 350),
                        "source_segment_ids": [segment["id"]],
                        "verification_status": "verified",
                    }
                )
        return {"claims": claims}

    def plan(state: AIState) -> dict:
        specs = (
            [("article", 0), ("newsletter", 0)]
            + [("social", i) for i in range(5)]
            + [("carousel", 0)]
            + [("clip", i) for i in range(3)]
        )
        return {"plan": [{"asset_type": kind, "ordinal": ordinal} for kind, ordinal in specs]}

    def generate(state: AIState) -> dict:
        settings = get_settings()

        def one(item: dict) -> dict:
            kind, ordinal = item["asset_type"], item["ordinal"]
            if settings.model_provider == "fixture":
                return _fixture_asset(kind, ordinal, state["segments"], state["topic"])
            if settings.model_provider == "openai":
                return _connected_asset(
                    kind, ordinal, state["segments"], state["topic"], state["brand"]
                )
            raise RuntimeError(f"Unsupported model provider: {settings.model_provider}")

        with ThreadPoolExecutor(max_workers=3) as pool:
            assets = list(pool.map(one, state["plan"]))
        return {"assets": assets}

    def check(state: AIState) -> dict:
        prohibited = state["brand"].get("rules", {}).get("prohibited_phrases", [])
        checked = []
        all_warnings = []
        for asset in state["assets"]:
            warnings = validate_asset(asset, state["segments"], prohibited)
            checked.append({**asset, "warnings": warnings})
            all_warnings.extend(warnings)
        return {"assets": checked, "warnings": all_warnings}

    def route(state: AIState) -> str:
        return (
            "revise"
            if state.get("warnings")
            and state.get("revision_count", 0) < 1
            and get_settings().model_provider == "openai"
            else END
        )

    def revise(state: AIState) -> dict:
        revised = []
        for index, asset in enumerate(state["assets"]):
            if asset["warnings"]:
                kind = asset["asset_type"]
                ordinal = sum(
                    1 for previous in state["assets"][:index] if previous["asset_type"] == kind
                )
                replacement = _connected_asset(
                    kind,
                    ordinal,
                    state["segments"],
                    state["topic"],
                    state["brand"],
                    "; ".join(asset["warnings"]),
                )
                revised.append(replacement)
            else:
                revised.append(asset)
        return {"assets": revised, "revision_count": 1}

    graph = StateGraph(AIState)
    graph.add_node("analyze_transcript", analyze)
    graph.add_node("build_claim_ledger", build_claims)
    graph.add_node("plan_assets", plan)
    graph.add_node("generate_asset_branches", generate)
    graph.add_node("check_evidence_and_brand", check)
    graph.add_node("revise_once", revise)
    graph.add_edge(START, "analyze_transcript")
    graph.add_edge("analyze_transcript", "build_claim_ledger")
    graph.add_edge("build_claim_ledger", "plan_assets")
    graph.add_edge("plan_assets", "generate_asset_branches")
    graph.add_edge("generate_asset_branches", "check_evidence_and_brand")
    graph.add_conditional_edges(
        "check_evidence_and_brand", route, {"revise": "revise_once", END: END}
    )
    graph.add_edge("revise_once", "check_evidence_and_brand")
    return graph


def generate_bundle(batch_id: str, segments: list[dict], brand: dict) -> GeneratedBundle:
    settings = get_settings()
    builder = build_graph()
    if settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        uri = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        context = PostgresSaver.from_conn_string(uri)
    else:
        context = nullcontext(None)
    with context as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        result = graph.invoke(
            {"segments": segments, "brand": brand, "revision_count": 0},
            {"configurable": {"thread_id": batch_id}, "recursion_limit": 12},
        )
    return GeneratedBundle(
        claims=result["claims"],
        assets=[GeneratedAsset.model_validate(asset) for asset in result["assets"]],
    )


def regenerate_one(asset_type: str, ordinal: int, segments: list[dict], brand: dict) -> dict:
    if not segments:
        raise ValueError("Cannot regenerate without a transcript")
    words = re.findall(r"[\w-]+", segments[0]["text"])
    topic = " ".join(words[:5]).strip() or "the discussion"
    provider = get_settings().model_provider
    if provider == "fixture":
        return _fixture_asset(asset_type, ordinal, segments, topic)
    if provider == "openai":
        return _connected_asset(asset_type, ordinal, segments, topic, brand)
    raise RuntimeError(f"Unsupported model provider: {provider}")
