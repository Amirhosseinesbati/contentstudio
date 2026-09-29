"""Print measured counts from the configured demo database."""

import json

from sqlalchemy import func, select

from contentstudio.db import session_factory
from contentstudio.models import (
    BrandProfileVersion,
    ContentAssetVersion,
    ContentBatch,
    Segment,
    SourceAsset,
    Workspace,
)


def main():
    with session_factory()() as db:
        showcase = db.scalar(select(ContentBatch).where(ContentBatch.recipe_version == "v1").limit(1))
        assets = db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == showcase.id)).all()
        result = {
            "workspaces": db.scalar(select(func.count(Workspace.id))),
            "sources": db.scalar(select(func.count(SourceAsset.id))),
            "segments": db.scalar(select(func.count(Segment.id))),
            "brands": db.scalar(select(func.count(BrandProfileVersion.id))),
            "asset_versions": db.scalar(select(func.count(ContentAssetVersion.id))),
            "showcase_assets": len(assets),
            "showcase_warned_assets": sum(bool(asset.warnings_json) for asset in assets),
            "article_words": [len(a.text.split()) for a in assets if a.asset_type == "article"],
            "newsletter_words": [len(a.text.split()) for a in assets if a.asset_type == "newsletter"],
            "clip_durations_ms": [a.clip_range_json["end_ms"] - a.clip_range_json["start_ms"] for a in assets if a.asset_type == "clip"],
        }
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
