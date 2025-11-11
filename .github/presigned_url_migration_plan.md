# Presigned URL Migration Plan

This plan describes how to keep the S3 bucket private while still serving tribute photos by issuing short-lived presigned URLs at render time. It builds on the current S3 migration work (see `S3_CloudFront_migration_plan.md`) and maps concrete code changes across the repository.

---

## Goals

- Prevent direct anonymous access to the S3 bucket while keeping the memorial site functional.
- Generate expiring `GET` URLs when views render, instead of persisting public URLs in the database.
- Keep legacy base64 rows rendering until fully migrated, but avoid creating new base64 data.
- Minimise template churn and keep existing deletion/migration tooling useful.

## Current Snapshot (2025-11-11)

- `app/services/storage.prepare_photo_entries` uploads new files to S3 (via `upload_bytes`) and persists `photo_s3_key`; failed uploads are skipped with a warning.
- `TributePhoto` model (`app/models.py`) stores `photo_b64`, `photo_url`, `photo_s3_key`, and `migrated_at` (nullable).
- Templates read `photo.photo_url` with base64 fallback (`app/templates/partials/_tribute_list.html`, `app/templates/tribute_detail.html`, carousel partial).
- Route helpers (`app/routes.py`) serialise database objects and cache results in `_CAROUSEL_CACHE` and `_TRIBUTES_CACHE`, currently storing `photo_url` strings.
- `tools/migrate_photos_to_s3.py` writes both `photo_s3_key` and `photo_url` after uploads.
- Bucket now rejects ACLs (Object Ownership = Bucket owner enforced). Direct S3 URLs 403 without a public bucket policy.

## Target Architecture

- S3 bucket remains private (no public-read ACLs, Block Public Access can remain enabled).
- Application stores only `photo_s3_key` (plus existing `photo_b64` for legacy data).
- Views call a helper that emits presigned `GET` URLs with a configurable TTL (e.g. 5 minutes).
- Cached data should not persist the presigned URLs longer than their TTL; regenerate URLs for each response or shrink cache entries to keys only.

## Implementation Plan

### Phase 1 – Configuration & Helpers

1. **Config knob**: add `S3_PRESIGNED_TTL` (seconds) to `app/config.py` with default (e.g. 300). Expose via env var.
2. **S3 helper**: extend `app/services/s3.py` with `generate_presigned_get_url(key: str, *, expires_in: int | None = None) -> str`. Internally wraps `boto3.client("s3").generate_presigned_url(...)` and raises `S3ConfigurationError` if bucket/keys missing. Read TTL from config when `expires_in` omitted.
3. Optionally memoise the client similar to existing `_get_client`, reusing it.

### Phase 2 – Stop Persisting Static URLs

4. **Storage service**: in `prepare_photo_entries`, stop including `photo_url` in returned entries. Continue returning `photo_s3_key` so database rows retain object identifiers. Base64 fallback already removed for new uploads.
5. **Tribute service**: ensure `create_tribute` no longer expects `photo_url` in entries; tolerate the field but ignore it. Future data inserts should store only the key.
6. **Migration script**: update `tools/migrate_photos_to_s3.py` to set `photo_url = None` (or simply omit). Consider adding a `--nullify-photo-url` flag to clean up existing rows after migration.

### Phase 3 – Runtime URL Generation

7. **Route serialization**:
   - Create a helper inside `app/routes.py` (e.g. `_resolve_photo_src(photo)`) that returns:
     - Presigned URL from `s3.generate_presigned_get_url(photo.photo_s3_key)` if key exists.
     - Base64 data URI fallback if not.
   - Update `_serialize_tribute` to include `"photo_url": _resolve_photo_src(photo)` without mutating the model. Do not persist this value.
8. **Carousel collector**: adjust `_collect_carousel_images` to regenerate URLs per request. Options:
   - **Simplest**: bypass `_CAROUSEL_CACHE` (or reduce TTL to <= presigned TTL) and rebuild the list each call.
   - **Optimised**: cache only photo IDs, then map to URLs right before rendering.
9. **Tributes cache**: `_TRIBUTES_CACHE` currently stores serialized dicts including `photo_url`. Either set cache TTL ≤ presigned TTL, or store only raw DB fields and compute presigned URLs after cache retrieval.
10. Ensure admin delete flow (`admin_delete_tribute`) continues to delete S3 objects via `photo_s3_key` (no change needed).

### Phase 4 – Templates & Forms

11. Templates already consume `photo_url` + fallback, so no markup change required once serialization supplies presigned URLs.
12. Verify forms and notifications untouched.

### Phase 5 – Testing & Verification

13. **Unit tests**:
    - Add tests for `generate_presigned_get_url` using `monkeypatch` to stub `client.generate_presigned_url`.
    - Update `tests/test_services.py` to confirm S3 entries persist without `photo_url`.
    - Add route-level assertions that responses contain `https://` presigned URLs when `photo_s3_key` exists (mock helper to deterministic value).
14. **Integration**: run `uv run pytest` and manually load `/tributes` and `/tributes/<id>` verifying images load (bucket policy remains private).
15. Optionally add a smoke test in `tools/migrate_photos_to_s3.py` (dry-run) to confirm no `photo_url` writes.

### Phase 6 – Data Hygiene & Cleanup

16. After verifying presigned URLs in production, null existing `photo_url` values (SQL `UPDATE tribute_photos SET photo_url = NULL`). Document or automate via Alembic migration.
17. Once confident no code path requires the column, drop `photo_url` (and `migrated_at` if redundant) in a later migration. Update model accordingly.
18. Update `.github/S3_CloudFront_migration_plan.md` backlog to reflect presigned approach.

## Rollout Steps

1. Implement Phase 1–3 changes locally; run tests.
2. Deploy code alongside configuration update (`S3_PRESIGNED_TTL`).
3. Redeploy so new uploads rely on presigned URLs.
4. Run migration script (without `--dry-run`) to ensure existing rows have keys and base64 fallback intact (URLs now computed dynamically).
5. Verify production traffic (spot-check pages); ensure S3 bucket has no public policy.
6. Proceed with Phase 6 cleanup when ready.

## Backout Plan

- If presigned logic misbehaves, redeploy previous build (which still uses stored `photo_url`). Existing DB rows retain old URLs.
- Ensure bucket policy still allows legacy URLs if fallback is necessary during rollback.
- Migration script retains base64 copies; no data loss expected.

## Risks & Mitigations

- **Expired cache entries**: ensure caches regenerate URLs before they expire or disable caches temporarily.
- **Clock skew**: presigned URLs rely on server time; keep app servers in sync (NTP).
- **Performance**: presigning per photo is light (<1 ms) but still per request; monitor CPU usage. If needed, batch presigning or reduce frequency by caching results with short TTL.
- **URL leakage**: URLs expire quickly; sharing them externally will fail after TTL—this is desired, but communicate to stakeholders if necessary.

## Next Actions

- [ ] Approve this plan.
- [ ] Schedule development window for implementation (est. 1–2 days dev + testing).
- [ ] Update project documentation once changes are live.
