from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BrandRulesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accent: str = Field(default="#D26634", pattern=r"^#[0-9a-fA-F]{6}$")
    prohibited_phrases: list[str] = Field(default_factory=list, max_length=50)
    max_social_chars: int = Field(default=500, ge=80, le=500)

    @field_validator("prohibited_phrases")
    @classmethod
    def phrases(cls, values):
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 120 for value in cleaned):
            raise ValueError("Brand phrases must contain 1-120 characters")
        return list(dict.fromkeys(cleaned))


class BrandCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=45)
    tone: str = Field(min_length=2, max_length=300)
    rules: BrandRulesInput = Field(default_factory=BrandRulesInput)


class BrandRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tone: str = Field(min_length=2, max_length=300)
    rules: BrandRulesInput


class LoginInput(BaseModel):
    email: str
    password: str


class SegmentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must exceed start_ms")
        return self


class TranscriptSourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=250)
    rights_attested: bool
    segments: list[SegmentInput] = Field(min_length=1, max_length=5000)


class SegmentCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=10000)
    expected_transcript_id: str | None = None


class BatchInput(BaseModel):
    brand_profile_id: str
    recipe_version: str = Field(default="v1", min_length=1, max_length=40)


class AssetEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=250)
    text: str | None = Field(default=None, max_length=40000)
    slides: list[dict] | None = None
    clip_range: dict | None = None
    source_segment_ids: list[str] | None = Field(default=None, max_length=5000)
    expected_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def one_field(self):
        if all(v is None for v in (self.title, self.text, self.slides, self.clip_range, self.source_segment_ids)):
            raise ValueError("At least one field is required")
        return self


class ReviewInput(BaseModel):
    decision: Literal["approve", "reject"]
    expected_hash: str = Field(min_length=64, max_length=64)
    reason: str | None = Field(default=None, max_length=2000)


class ScheduleInput(BaseModel):
    scheduled_at: str | None = None
    channel: Literal["wordpress", "newsletter", "social"] = "wordpress"


class IntakeInput(BaseModel):
    workspace_id: str
    source_asset_id: str
    recipe_version: str = "v1"
    brand_profile_version_id: str
    request_id: str = Field(min_length=1, max_length=180)


class BatchStepInput(BaseModel):
    workspace_id: str
    batch_id: str


class RenderStepInput(BaseModel):
    workspace_id: str
    asset_version_id: str


class DispatchPrepareInput(BaseModel):
    workspace_id: str
    asset_version_id: str
    channel: Literal["wordpress"]
    operation_key: str = Field(min_length=1, max_length=180)


class OutboxInput(BaseModel):
    workspace_id: str
    asset_version_id: str
    channel: Literal["newsletter", "social"]
    operation_key: str = Field(min_length=1, max_length=180)


class DispatchCompleteInput(BaseModel):
    workspace_id: str
    operation_key: str
    external_id: str
    status: Literal["success", "draft"] = "success"


class WorkflowErrorInput(BaseModel):
    workspace_id: str | None = None
    operation_key: str
    error: str = Field(max_length=2000)
    outcome: Literal["failed", "unknown"] = "failed"


class UserOut(BaseModel):
    id: str
    email: str
    role: Literal["admin", "operator", "viewer"]
    workspace_id: str


class AuthOut(BaseModel):
    user: UserOut
    mode: str


class WorkspaceOut(BaseModel):
    id: str
    slug: str
    name: str


class BootstrapOut(BaseModel):
    mode: str
    synthetic_demo_dataset: bool
    workspace: WorkspaceOut
    user: UserOut
    stats: dict[str, int]
    connection: dict[str, str]


class SegmentOut(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    speaker: str | None
    text: str


class TranscriptOut(BaseModel):
    id: str
    version: int
    provenance: str
    segments: list[SegmentOut]


class SourceOut(BaseModel):
    id: str
    title: str
    kind: str
    mime_type: str | None
    duration_ms: int
    rights_status: str
    created_at: str
    latest_transcript_version_id: str | None
    batch_count: int


class SourceDetailOut(BaseModel):
    source: SourceOut
    transcript: TranscriptOut | None
    media_url: str | None
    media_status: Literal["available", "missing", "transcript_only"]


class SourcesOut(BaseModel):
    items: list[SourceOut]


class BrandOut(BaseModel):
    id: str
    name: str
    version: int
    tone: str
    rules: dict


class BrandsOut(BaseModel):
    items: list[BrandOut]


class EvidenceEntryOut(BaseModel):
    text: str
    source_segment_ids: list[str]
    match: Literal["verbatim"]


class RenderUrlsOut(BaseModel):
    png: list[str]
    pdf: str | None
    mp4: str | None


class AssetOut(BaseModel):
    id: str
    logical_asset_id: str
    batch_id: str
    asset_type: str
    title: str
    text: str
    status: str
    version: int
    content_hash: str
    source_segment_ids: list[str]
    warnings: list[str]
    slides: list[dict]
    clip_range: dict | None
    evidence_map: list[EvidenceEntryOut]
    render_urls: RenderUrlsOut


class ClaimOut(BaseModel):
    id: str
    text: str
    source_segment_ids: list[str]
    verification_status: str


class BatchOut(BaseModel):
    id: str
    source_asset_id: str
    brand_profile_version_id: str
    transcript_version_id: str | None
    recipe_version: str
    status: str
    error: str | None
    created_at: str
    asset_count: int


class BatchDetailOut(BaseModel):
    batch: BatchOut
    source: SourceOut
    claims: list[ClaimOut]
    assets: list[AssetOut]


class BatchesOut(BaseModel):
    items: list[BatchOut]


class JobOut(BaseModel):
    id: str
    job_id: str
    kind: str
    status: str
    progress: int
    error: str | None
    result: dict
    batch_id: str | None
    asset_version_id: str | None
    updated_at: str


class JobsOut(BaseModel):
    items: list[JobOut]


class CalendarEntryOut(BaseModel):
    id: str
    asset_version_id: str
    batch_id: str
    channel: str
    status: str
    scheduled_at: str | None
    title: str


class CalendarOut(BaseModel):
    items: list[CalendarEntryOut]


class ScheduledOut(BaseModel):
    id: str
    asset_version_id: str
    channel: str
    status: str
    scheduled_at: str | None
