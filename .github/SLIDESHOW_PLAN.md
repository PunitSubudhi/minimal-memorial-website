# Slideshow Page Implementation Plan

This document outlines the architecture, tasks, and rollout steps for introducing a standalone slideshow experience at `/slideshow`. The page will run independently from the main memorial site navigation and continuously surface tributes, updating as new submissions arrive.

## Objectives
- Provide a kiosk-friendly slideshow that rotates through all tributes without exposing navigation back to the rest of the site.
- Display image-backed tributes with their associated media and overlay text that remains legible on large screens.
- Render text-only tributes in an engaging, full-screen layout to avoid empty space and reduce burn-in risk.
- Surface a QR code call-to-action so viewers can easily access the `/tributes` submission form.
- Detect and incorporate new tributes automatically with minimal latency and low server load.

## High-Level Architecture
- **Route design**: introduce a dedicated Blueprint route `GET /slideshow` that renders a specialized template (`slideshow.html`). The template should bypass the standard `base.html` navbar to maintain a distraction-free view.
- **Data service**: expose a JSON feed endpoint (e.g., `GET /slideshow/data`) returning tributes ordered by `created_at` (descending). Include essential fields (id, name, message, timestamp, photo URLs/captions) and leverage SQLAlchemy eager loading to avoid N+1 queries.
- **Client polling**: a lightweight JavaScript controller (`static/js/slideshow.js`) loads the dataset on startup, tracks a `lastFetched` timestamp, and periodically polls the JSON endpoint. When no new data is available, the slideshow continues cycling the cached list.
- **Caching strategy**: compute a `last_modified` value based on the most recent tribute update. Serve it via response headers (e.g., `Last-Modified`, `ETag`) to enable conditional requests (304 responses). Optionally cache serialized payloads in memory or a future Redis layer to keep response times consistent under load.

## Backend Tasks
- [x] Add a route in `app/routes.py` (or a dedicated blueprint module) for `/slideshow` that renders `slideshow.html`.
- [x] Create the JSON feed endpoint returning tributes and related photos in the required shape. Consider introducing a serializer helper in `app/services/tributes.py` for reuse.
- [x] Ensure photo URLs are normalized: prefer presigned S3 links when present, otherwise fallback to base64 data as today.
- [x] Implement conditional response headers (`Last-Modified`, `ETag`) using the latest `Tribute.created_at` value.
- [x] Provide a config knob (e.g., `SLIDESHOW_POLL_SECONDS`) to adjust client polling frequency without code changes.
- [x] Extend tests in `tests/test_routes.py` (or a new module) to cover both the HTML route and the JSON feed (ordering, structure, last-modified headers).

## Frontend Tasks
- [x] Create `app/templates/slideshow.html` with a minimal HTML skeleton, linking a dedicated stylesheet (`static/css/slideshow.css`) and JavaScript controller (`static/js/slideshow.js`). Avoid including the standard navbar/footer.
- [x] Design two layout variants:
  - **Image tributes**: full-viewport image treatment with `object-fit: contain` and an anchored gradient panel containing tribute text, contributor name, and timestamp.
  - **Text-only tributes**: centered typographic layout on a dark background with subtle animation (e.g., fade-in, slow scale) to avoid static burn-in.
- [x] Add a persistent corner overlay reserved for a QR code image (served from `static/images/qrcode.svg`) accompanied by a short prompt ("Share your memories at memorial.site/tributes").
- [x] Implement slideshow transitions (CSS `opacity` crossfade or JS-managed slide-in). Support configurable dwell duration and transition timing through data attributes or configuration variables.
- [x] Handle empty-state rendering with a friendly message encouraging tribute submissions and showing the QR prompt.
- [x] Integrate responsive typography and spacing to ensure readability on 1080p and 4K displays.

### 2025-11 Layout & Rotation Enhancements
- Refined the slideshow canvas to a contained two-column layout so photos always remain fully visible while copy stays in a dedicated right-hand panel.
- Updated `static/css/slideshow.css` to rely on `object-fit: contain`, flexbox alignment, and responsive breakpoints that stack panels on smaller viewports without overlap.
- Reworked `static/js/slideshow.js` to iterate through every photo attached to a tribute before advancing to the next tribute, preload upcoming assets, and expose a per-photo status indicator.
- Added configurable message trimming through the `SLIDESHOW_MAX_MESSAGE_LENGTH` setting (default 600) and client-side word-preserving ellipsis with tooltip access to the full submission.

## JavaScript Controller Responsibilities (`static/js/slideshow.js`)
- [x] Fetch the JSON feed on page load; store tributes in memory and sort by creation time.
- [x] Rotate through entries using a timer (default 8–10 second dwell). Preload upcoming image assets for smooth transitions.
- [x] Periodically poll the feed (e.g., every 60 seconds) using conditional requests. Append newly discovered tributes to the rotation.
- [x] Provide basic offline resilience: if a fetch fails, log the error to the console, back off the polling interval, and keep cycling cached tributes.
- [x] Allow optional keyboard controls or URL query parameters for debugging (e.g., `?duration=5000`, `?shuffle=true`). Disable these in production deployments.

## Performance & Resilience Considerations
- Downscale large images on the server side when storing in S3 to balance visual quality and network overhead. If real-time resizing isnt available, apply CSS constraints and lazy-loading.
- Use requestAnimationFrame or CSS animations over heavy JS timers to ensure smooth transitions.
- Consider a full-screen black background that masks letterboxing for varied image aspect ratios.
- Modify browser kiosk settings (documented below) to prevent the screen from sleeping or showing browser chrome.

## Testing Strategy
- **Unit tests**: validate JSON serialization and ordering logic via Flask test client; include cases for tributes with and without photos.
- **Integration tests**: ensure the `/slideshow` page renders successfully and includes placeholder containers for images, text, and the QR panel.
- **Manual QA checklist**:
  - Confirm slideshow loops indefinitely without flicker.
  - Upload a new tribute and verify it appears after the next poll interval without a manual refresh.
  - Test layouts for mixed content (multiple photos, long messages, short messages).
  - Validate QR overlay positioning on various display resolutions.
  - Test offline behaviour by disconnecting network; slideshow should continue with cached entries.

## Deployment & Operational Notes
- Document the recommended browser setup for the kiosk (Chrome in full-screen mode, `--kiosk` flag, disable sleep/screensaver on host machine).
- Update `.github/HOME_PAGE.md` or `README.md` with instructions for operating the slideshow, including how to swap the QR asset and adjust polling intervals.
- Coordinate with design/content stakeholders to finalize typography, background treatment, and copywriting prior to deployment.
- After release, monitor server logs for JSON feed performance and adjust caching or polling intervals as needed.

---
Maintaining this plan:
- Update the checklist as tasks are completed; reference associated pull requests or issues.
- Record significant architectural decisions (e.g., choice of caching layer) to aid future maintenance.
