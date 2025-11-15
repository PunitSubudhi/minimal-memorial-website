# Slideshow Layout Improvement Plan

This document captures the proposed approach for refining the `/slideshow` experience so that tribute photos always fit within the viewport, text is right-aligned without overlapping imagery, and multi-photo tributes cycle through all associated media. The plan assumes the existing Flask + Bootstrap stack described in `.github/SLIDESHOW_PLAN.md` and focuses on incremental, testable enhancements.

## Objectives
- Enforce full-photo visibility: every image displays completely while preserving its native aspect ratio, regardless of screen resolution.
- Rotate through all photos per tribute: the slideshow must advance through each tribute's photo set before moving to the next tribute entry.
- Improve text treatment: constrain copy to a right-hand panel, reduce font sizing, and trim overly long content with an ellipsis.
- Maintain responsive, kiosk-friendly presentation: ensure the layout avoids overlap between media and text while remaining legible on 1080p and 4K displays.

## Scope Overview
- No changes to data storage schema; rely on existing `Tribute` and `TributePhoto` models.
- Update slideshow template, stylesheet, and controller JavaScript.
- Expand route/service serialization only if additional metadata is required (e.g., photo ordering cues).

## Implementation Phases

### Phase 1 – Discovery & Validation
- Audit current slideshow DOM structure (`app/templates/slideshow.html`) to confirm container hooks for media and text blocks.
- Confirm JSON payload shape from `/slideshow/data` supports multiple photos per tribute (array presence, order guarantees).
- Capture baseline behaviour with browser dev tools to measure existing image scaling and text layout constraints.

### Phase 2 – Template & Markup Adjustments
- Update `slideshow.html` to introduce dedicated containers:
  - Left column `div` for the active photo with intrinsic aspect ratio handling.
  - Right column `div` for the tribute text block (name, message, timestamp).
- Ensure markup anticipates optional photo arrays and text-only tributes (fallback image slot hidden when empty).
- Embed data attributes to indicate maximum characters for truncation if needed.

### Phase 3 – Styling Enhancements (`static/css/slideshow.css`)
- Apply a two-column, flex-based layout that pins the photo container left and text container right.
- Force images to use `object-fit: contain` with `max-height` and `max-width` tied to viewport dimensions to prevent cropping.
- Add responsive breakpoints: at smaller widths stack content vertically while preserving non-overlap.
- Define typography scale for headings/body text to remain legible yet compact; include ellipsis-friendly styles (`text-overflow`) for safeguards.
- Introduce padding/margins to keep the QR overlay unobstructed.

### Phase 4 – JavaScript Controller Updates (`static/js/slideshow.js`)
- Revise rotation logic to iterate through each tribute's photo list before advancing to the next tribute:
  - Maintain pointers for `activeTributeIndex` and `activePhotoIndex`.
  - Reset `activePhotoIndex` when tribute changes.
- Ensure preloading of upcoming images accounts for per-tribute photo arrays.
- Implement text truncation utility:
  - Accept configurable max length (default derived from template data attribute or query param override).
  - Gracefully append `...` when messages exceed threshold while preserving whole words when possible.
- Adjust transition timing so photo dwell duration applies to each image; total tribute dwell equals photo count * dwell.
- Confirm polling backoff retains photo index state when new data merges into the cache.

### Phase 5 – Accessibility & UX Checks
- Validate contrast ratios for right-hand text panel against background gradients.
- Ensure truncated text exposes full content via optional secondary view (tooltip or detail overlay) or document rationale for kiosk usage where truncation is acceptable.
- Confirm keyboard controls (if enabled for debugging) respect new state machine without desynchronizing photo/text alignment.

### Phase 6 – Testing & QA
- Extend `tests/test_routes.py` (or new module) to verify `/slideshow/data` returns ordered photo arrays and includes necessary metadata for client sequencing.
- Add front-end smoke tests (Playwright or manual checklist) covering:
  - Mixed-content tributes (single photo, multiple photos, text-only).
  - Various viewport sizes (1080p landscape, 4K, portrait tablet if relevant).
  - Long message truncation and ellipsis rendering.
- Manual regression checklist: ensure QR overlay remains fixed, polling cadence unchanged, and offline resilience intact.

### Phase 7 – Documentation & Deployment
- Update `.github/SLIDESHOW_PLAN.md` or README with new configuration knobs (e.g., `SLIDESHOW_MAX_MESSAGE_LENGTH`, per-photo dwell).
- Note styling changes and debugging parameters for kiosk operators.
- Prepare release notes summarizing user-facing improvements and testing performed.

## Risks & Mitigations
- **Excessive truncation visibility**: mitigate by selecting conservative character limits and documenting how to adjust via configuration.
- **Performance regression due to extra DOM updates**: throttle animation transitions and reuse DOM nodes to minimize reflow.
- **Image aspect ratio edge cases**: add CSS fallbacks (`background-color` framing) for extreme panorama or portrait sizes.

## Timeline Estimate
- Phase 1–2: 0.5 day
- Phase 3–4: 1 day
- Phase 5–6: 0.5 day
- Phase 7: 0.25 day

Total effort: ~1.75 developer-days assuming familiarity with existing slideshow implementation.
