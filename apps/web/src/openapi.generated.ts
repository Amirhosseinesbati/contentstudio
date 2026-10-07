// Generated from apps/api/openapi.json. Do not edit by hand.
// SHA256: 61aaf8722f4655d335936bdd2e893e4f794d0b420a84cc4ba96f81db6f3ef687
export interface components {
  schemas: {
    "AssetEditInput": { "title"?: (string | null); "text"?: (string | null); "slides"?: (Array<Record<string, unknown>> | null); "clip_range"?: (Record<string, unknown> | null); "source_segment_ids"?: (Array<string> | null); "expected_hash"?: (string | null) }
    "AssetOut": { "id": string; "logical_asset_id": string; "batch_id": string; "asset_type": string; "title": string; "text": string; "status": string; "version": number; "content_hash": string; "source_segment_ids": Array<string>; "warnings": Array<string>; "slides": Array<Record<string, unknown>>; "clip_range": (Record<string, unknown> | null); "evidence_map": Array<components["schemas"]["EvidenceEntryOut"]>; "render_urls": components["schemas"]["RenderUrlsOut"] }
    "AuthOut": { "user": components["schemas"]["UserOut"]; "mode": string }
    "BatchDetailOut": { "batch": components["schemas"]["BatchOut"]; "source": components["schemas"]["SourceOut"]; "claims": Array<components["schemas"]["ClaimOut"]>; "assets": Array<components["schemas"]["AssetOut"]> }
    "BatchInput": { "brand_profile_id": string; "recipe_version"?: string }
    "BatchOut": { "id": string; "source_asset_id": string; "brand_profile_version_id": string; "transcript_version_id": (string | null); "recipe_version": string; "status": string; "error": (string | null); "created_at": string; "asset_count": number }
    "BatchStepInput": { "workspace_id": string; "batch_id": string }
    "BatchesOut": { "items": Array<components["schemas"]["BatchOut"]> }
    "Body_upload_source_api_v1_sources_upload_post": { "file": string; "title": string; "rights_attested": boolean }
    "BootstrapOut": { "mode": string; "synthetic_demo_dataset": boolean; "workspace": components["schemas"]["WorkspaceOut"]; "user": components["schemas"]["UserOut"]; "stats": Record<string, number>; "connection": Record<string, string> }
    "BrandCreateInput": { "name": string; "tone": string; "rules"?: components["schemas"]["BrandRulesInput"] }
    "BrandOut": { "id": string; "name": string; "version": number; "tone": string; "rules": Record<string, unknown> }
    "BrandRevisionInput": { "tone": string; "rules": components["schemas"]["BrandRulesInput"] }
    "BrandRulesInput": { "accent"?: string; "prohibited_phrases"?: Array<string>; "max_social_chars"?: number }
    "BrandsOut": { "items": Array<components["schemas"]["BrandOut"]> }
    "CalendarEntryOut": { "id": string; "asset_version_id": string; "batch_id": string; "channel": string; "status": string; "scheduled_at": (string | null); "title": string }
    "CalendarOut": { "items": Array<components["schemas"]["CalendarEntryOut"]> }
    "ClaimOut": { "id": string; "text": string; "source_segment_ids": Array<string>; "verification_status": string }
    "DispatchCompleteInput": { "workspace_id": string; "operation_key": string; "external_id": string; "status"?: "success" | "draft" }
    "DispatchPrepareInput": { "workspace_id": string; "asset_version_id": string; "channel": "wordpress"; "operation_key": string }
    "EvidenceEntryOut": { "text": string; "source_segment_ids": Array<string>; "match": "verbatim" }
    "HTTPValidationError": { "detail"?: Array<components["schemas"]["ValidationError"]> }
    "IntakeInput": { "workspace_id": string; "source_asset_id": string; "recipe_version"?: string; "brand_profile_version_id": string; "request_id": string }
    "JobOut": { "id": string; "job_id": string; "kind": string; "status": string; "progress": number; "error": (string | null); "result": Record<string, unknown>; "batch_id": (string | null); "asset_version_id": (string | null); "updated_at": string }
    "JobsOut": { "items": Array<components["schemas"]["JobOut"]> }
    "LoginInput": { "email": string; "password": string }
    "OutboxInput": { "workspace_id": string; "asset_version_id": string; "channel": "newsletter" | "social"; "operation_key": string }
    "RenderStepInput": { "workspace_id": string; "asset_version_id": string }
    "RenderUrlsOut": { "png": Array<string>; "pdf": (string | null); "mp4": (string | null) }
    "ReviewInput": { "decision": "approve" | "reject"; "expected_hash": string; "reason"?: (string | null) }
    "ScheduleInput": { "scheduled_at"?: (string | null); "channel"?: "wordpress" | "newsletter" | "social" }
    "ScheduledOut": { "id": string; "asset_version_id": string; "channel": string; "status": string; "scheduled_at": (string | null) }
    "SegmentCorrectionInput": { "text": string; "expected_transcript_id"?: (string | null) }
    "SegmentInput": { "start_ms": number; "end_ms": number; "speaker"?: (string | null); "text": string }
    "SegmentOut": { "id": string; "start_ms": number; "end_ms": number; "speaker": (string | null); "text": string }
    "SourceDetailOut": { "source": components["schemas"]["SourceOut"]; "transcript": (components["schemas"]["TranscriptOut"] | null); "media_url": (string | null); "media_status": "available" | "missing" | "transcript_only" }
    "SourceOut": { "id": string; "title": string; "kind": string; "mime_type": (string | null); "duration_ms": number; "rights_status": string; "created_at": string; "latest_transcript_version_id": (string | null); "batch_count": number }
    "SourcesOut": { "items": Array<components["schemas"]["SourceOut"]> }
    "TranscriptOut": { "id": string; "version": number; "provenance": string; "segments": Array<components["schemas"]["SegmentOut"]> }
    "TranscriptSourceInput": { "title": string; "rights_attested": boolean; "segments": Array<components["schemas"]["SegmentInput"]> }
    "UserOut": { "id": string; "email": string; "role": "admin" | "operator" | "viewer"; "workspace_id": string }
    "ValidationError": { "loc": Array<(string | number)>; "msg": string; "type": string; "input"?: unknown; "ctx"?: Record<string, unknown> }
    "WorkflowErrorInput": { "workspace_id"?: (string | null); "operation_key": string; "error": string; "outcome"?: "failed" | "unknown" }
    "WorkspaceOut": { "id": string; "slug": string; "name": string }
  }
}

export interface paths {
  "/api/v1/assets/{asset_id}": {
    patch: { request: components["schemas"]["AssetEditInput"]; response: components["schemas"]["AssetOut"] }
  }
  "/api/v1/assets/{asset_id}/regenerate": {
    post: { request: unknown; response: components["schemas"]["AssetOut"] }
  }
  "/api/v1/assets/{asset_id}/render": {
    post: { request: unknown; response: components["schemas"]["JobOut"] }
  }
  "/api/v1/assets/{asset_id}/renders/{attempt_id}/{filename}": {
    get: { request: unknown; response: unknown }
  }
  "/api/v1/assets/{asset_id}/renders/{filename}": {
    get: { request: unknown; response: unknown }
  }
  "/api/v1/assets/{asset_id}/review": {
    post: { request: components["schemas"]["ReviewInput"]; response: components["schemas"]["AssetOut"] }
  }
  "/api/v1/assets/{asset_id}/schedule": {
    post: { request: components["schemas"]["ScheduleInput"]; response: components["schemas"]["ScheduledOut"] }
  }
  "/api/v1/auth/login": {
    post: { request: components["schemas"]["LoginInput"]; response: components["schemas"]["AuthOut"] }
  }
  "/api/v1/auth/logout": {
    post: { request: unknown; response: unknown }
  }
  "/api/v1/auth/me": {
    get: { request: unknown; response: components["schemas"]["AuthOut"] }
  }
  "/api/v1/batches": {
    get: { request: unknown; response: components["schemas"]["BatchesOut"] }
  }
  "/api/v1/batches/{batch_id}": {
    get: { request: unknown; response: components["schemas"]["BatchDetailOut"] }
  }
  "/api/v1/batches/{batch_id}/download": {
    get: { request: unknown; response: unknown }
  }
  "/api/v1/batches/{batch_id}/package": {
    post: { request: unknown; response: components["schemas"]["JobOut"] }
  }
  "/api/v1/bootstrap": {
    get: { request: unknown; response: components["schemas"]["BootstrapOut"] }
  }
  "/api/v1/brands": {
    get: { request: unknown; response: components["schemas"]["BrandsOut"] }
    post: { request: components["schemas"]["BrandCreateInput"]; response: components["schemas"]["BrandOut"] }
  }
  "/api/v1/brands/{brand_id}": {
    put: { request: components["schemas"]["BrandRevisionInput"]; response: components["schemas"]["BrandOut"] }
  }
  "/api/v1/calendar": {
    get: { request: unknown; response: components["schemas"]["CalendarOut"] }
  }
  "/api/v1/jobs": {
    get: { request: unknown; response: components["schemas"]["JobsOut"] }
  }
  "/api/v1/jobs/{job_id}": {
    get: { request: unknown; response: components["schemas"]["JobOut"] }
  }
  "/api/v1/jobs/{job_id}/cancel": {
    post: { request: unknown; response: components["schemas"]["JobOut"] }
  }
  "/api/v1/jobs/{job_id}/events": {
    get: { request: unknown; response: unknown }
  }
  "/api/v1/sources": {
    get: { request: unknown; response: components["schemas"]["SourcesOut"] }
  }
  "/api/v1/sources/transcript": {
    post: { request: components["schemas"]["TranscriptSourceInput"]; response: components["schemas"]["SourceDetailOut"] }
  }
  "/api/v1/sources/upload": {
    post: { request: components["schemas"]["Body_upload_source_api_v1_sources_upload_post"]; response: components["schemas"]["SourceDetailOut"] }
  }
  "/api/v1/sources/{source_id}": {
    get: { request: unknown; response: components["schemas"]["SourceDetailOut"] }
  }
  "/api/v1/sources/{source_id}/batches": {
    post: { request: components["schemas"]["BatchInput"]; response: components["schemas"]["BatchDetailOut"] }
  }
  "/api/v1/sources/{source_id}/media": {
    get: { request: unknown; response: unknown }
  }
  "/api/v1/sources/{source_id}/segments/{segment_id}": {
    patch: { request: components["schemas"]["SegmentCorrectionInput"]; response: components["schemas"]["SourceDetailOut"] }
  }
  "/healthz": {
    get: { request: unknown; response: unknown }
  }
  "/internal/workflows/demo-fixtures": {
    get: { request: unknown; response: unknown }
  }
  "/internal/workflows/demo-scenario-status": {
    get: { request: unknown; response: unknown }
  }
  "/internal/workflows/dispatch/complete": {
    post: { request: components["schemas"]["DispatchCompleteInput"]; response: unknown }
  }
  "/internal/workflows/dispatch/prepare": {
    post: { request: components["schemas"]["DispatchPrepareInput"]; response: unknown }
  }
  "/internal/workflows/due": {
    get: { request: unknown; response: unknown }
  }
  "/internal/workflows/errors": {
    post: { request: components["schemas"]["WorkflowErrorInput"]; response: unknown }
  }
  "/internal/workflows/generate": {
    post: { request: components["schemas"]["BatchStepInput"]; response: unknown }
  }
  "/internal/workflows/intake": {
    post: { request: components["schemas"]["IntakeInput"]; response: unknown }
  }
  "/internal/workflows/outbox": {
    post: { request: components["schemas"]["OutboxInput"]; response: unknown }
  }
  "/internal/workflows/package": {
    post: { request: components["schemas"]["BatchStepInput"]; response: unknown }
  }
  "/internal/workflows/reconcile": {
    get: { request: unknown; response: unknown }
  }
  "/internal/workflows/render": {
    post: { request: components["schemas"]["RenderStepInput"]; response: unknown }
  }
  "/internal/workflows/transcribe": {
    post: { request: components["schemas"]["BatchStepInput"]; response: unknown }
  }
  "/internal/workflows/workspaces": {
    get: { request: unknown; response: unknown }
  }
}

export type ApiResponse<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends { response: infer R } ? R : never
export type ApiRequest<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends { request: infer R } ? R : never
