# Memory Wall Pagination Plan

This document outlines the approach and tasks required to paginate the tributes shown on the `/tributes` page (the "memory wall"). The current implementation renders all tributes at once; the goal is to show only the most recent entries initially and provide a way to load additional tributes on demand without full page reloads.

## Objectives
- Limit the number of tributes rendered on first load to improve perceived performance and reduce payload size.
- Introduce a progressive loading experience ("Load more" button) that keeps the current form and layout intact.
- Ensure the API and client logic can support configurable page sizes and preserve descending `created_at` ordering.
- Maintain accessibility and graceful degradation (pagination should still work if JS fails).
- Keep the service layer reusable for future pagination or API needs.

## High-Level Approach
1. **Server-side pagination**: Extend the tributes query in the service layer to accept `page` and `per_page` parameters, defaulting to a new `TRIBUTES_PER_PAGE` config value.
2. **API endpoint**: Expose a JSON endpoint (e.g., `GET /tributes/data`) that returns paginated tribute batches and metadata (`has_next`, `next_page`). Leverage the existing serialization helper used by the slideshow feed to avoid duplication.
3. **Initial render**: Update the `/tributes` route to render only the first page of tributes and include the pagination metadata in the template context.
4. **Progressive loading**: Add client-side JavaScript that listens for a "Load more" button click, fetches the next page via the JSON endpoint, appends the results, and updates the button state.
5. **No-JS fallback**: Provide a query-string based pagination (`/tributes?page=2`) so users without JS can navigate using standard links.
6. **Caching & ordering**: Preserve ordering by `Tribute.created_at DESC`; ensure eager loading of photos still applies and pagination respects existing filtering logic.

## Backend Tasks
- [x] **Config**: Add `TRIBUTES_PER_PAGE` to `app/config.py` with a sensible default (e.g., 12) and ensure test settings override if needed.
- [x] **Service**: Update `app/services/tributes.py` to expose a paginated query function returning items plus pagination flags.
- [x] **Routes**:
  - [x] Adjust the main `/tributes` route to request the first page from the service and pass pagination data to the template.
  - [x] Add a JSON route (`/tributes/data`) that accepts `page` (and optional `per_page`) query params, returning serialized tributes and pagination metadata.
- [x] **Serialization**: Reuse or extend the existing tribute serializer (currently used by the slideshow feed) so both HTML and JSON routes share a consistent output shape.
- [x] **Validation**: Sanitize incoming pagination parameters (ensure positive integers, enforce a max page size to prevent abuse).
- [x] **Headers**: Consider emitting cache-friendly headers (`Cache-Control`, `ETag`) for the JSON endpoint, mirroring the slideshow implementation where feasible.

## Frontend Tasks
- [x] **Template (`app/templates/index.html`)**:
  - [x] Render only the first page of tributes.
  - [x] Insert a container element and a "Load more" button that reflects whether more pages exist.
  - [x] Include pagination metadata in `data-*` attributes for the JS controller (e.g., current page, next page URL).
- [x] **JavaScript (`static/js/main.js` or new module)**:
  - [x] Implement a small controller that reads pagination metadata, handles button clicks, fetches more tributes via `fetch`, and appends rendered HTML to the tribute list.
  - [x] Provide loading state feedback and disable/hide the button when no further pages exist.
  - [x] Gracefully handle errors, surfacing a toast or inline message.
- [x] **Partial rendering**: Either reuse the existing `_tribute_list.html` partial via cloning or render new tributes client-side using a simple template literal. Prefer server-rendered partials to keep formatting consistent.
- [x] **Accessibility**: Ensure the button has appropriate ARIA attributes and the appended content is announced for screen readers (e.g., `aria-live` region).

## Testing Strategy
- [x] **Unit tests**: Extend `tests/test_services.py` to cover the new pagination function, including boundary conditions.
- [x] **Route tests**: Update `tests/test_routes.py` to verify the `/tributes` HTML route respects pagination defaults and that the `/tributes/data` endpoint returns correct metadata, ordering, and error handling for invalid params.
- [ ] **Template tests**: If feasible, add tests ensuring the "Load more" button presence toggles based on `has_next` state.
- [ ] **JavaScript**: Add or update frontend tests if we introduce a dedicated JS module (likely manual QA due to current stack).
- [ ] **Manual QA**:
  - Confirm initial load performance improvements.
  - Validate Load more functionality, including edge cases (no more results, network failure).
  - Test no-JS fallback by disabling JS and navigating via query parameters.
  - Ensure mobile responsiveness and layout stability after additional tributes are appended.

## Rollout & Documentation
- [x] Update `.github/PLAN.md` and project README with pagination details and configuration knobs.
- [x] Document environment variables (`TRIBUTES_PER_PAGE`) and how to adjust them per deployment.
- [ ] Consider adding analytics or logging to monitor pagination usage (future enhancement).
- [ ] Communicate the change to stakeholders, highlighting the performance gains and how to adjust the load-more behavior if needed.

---
Maintaining this plan: keep the checklist updated as tasks are completed and reference related PRs or issues for traceability.