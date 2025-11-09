# Memorial Web App Implementation Plan

## Architecture & Structure
- Framework: Flask application packaged under `app/` with modules `__init__.py`, `routes.py`, `models.py`, `forms.py`, `services/storage.py`, `config.py`, and `extensions.py`.
- Assets: `templates/` (Jinja layouts, partials, pages), `static/` (CSS, JS, fonts), `static/images/` (carousel photos), `migrations/` (Flask-Migrate).
- Entry point: `main.py` uses app factory from `app/__init__.py`.
- Core routes: home (`/`) combining carousel → form → tribute gallery (handles form POST), and tribute detail (`/tributes/<id>`) showing a single entry in full.
- Third-party packages: `Flask`, `Flask-WTF`, `Flask-SQLAlchemy`, `Flask-Migrate`, `psycopg[binary]`, `python-dotenv`, `Pillow`, `pillow-heif`, `requests`.

## Configuration & Setup
- Manage secrets via environment variables (`DATABASE_URL`, `SECRET_KEY`, `MAX_CONTENT_LENGTH`, `ALLOWED_EXTENSIONS`). Support `.env` for local development.
- Provision Neon Postgres instance; capture connection string for `DATABASE_URL`.
- `config.py` reads environment and sets `SQLALCHEMY_DATABASE_URI`, session security flags, file size limits.
- `extensions.py` initializes SQLAlchemy, Migrate, WTF CSRF; imported by app factory.

## Data Model & Persistence
- `Tribute` model:
  - `id` (UUID or autoincrement), `name`, `message`, `created_at`.
  - `extra_fields` JSON column for future dynamic form fields.
- `TributePhoto` model:
  - `id` primary key with foreign key to `Tribute.id` (cascade delete).
  - `photo_b64` (TEXT) and `photo_content_type` (VARCHAR) per image.
  - `display_order` integer for carousel/list ordering; optional caption string if desired.
- Initialize Flask-Migrate, generate base migration, run against Neon (`uv run flask db upgrade`).

## Carousel Component
- Store slideshow assets in `static/images/`.
- On route render, scan the directory or maintain JSON manifest; pass filenames to Jinja template.
- Template uses Bootstrap carousel markup; lazy-load images and include controls.

## Tribute Submission Form
- Flask-WTF form with fields finalized once requirements provided; include text area for tributes and optional image upload.
- Validate file size and MIME type (use Pillow + pillow-heif for HEIC/HEIF support).
- Normalize uploads via Pillow, convert non-WebP images to WebP in-memory (quality ≈85), then base64 encode; store `image/webp` MIME unless already WebP.
- Persist encoded payloads through related `TributePhoto` rows with content type and ordering metadata.
- Home route (`/`) handles `GET` (render carousel + form + gallery) and `POST` (create entry, flash status, notify `ntfy.sh/JAYDEVSUBUDHINOTIFICATIONS`, redirect back to home).

## Displaying Tributes
- Fetch recent records ordered by `created_at DESC`; limit for pagination in the gallery.
- Decode related `TributePhoto` records on display (render as `data:{content_type};base64,{photo_b64}`).
- Tribute cards link to the detail route (`/tributes/<id>`); detail page renders full message, metadata, and photo set.
- Handle long text on gallery cards (truncate with "Read more" if needed).

## Templates & Static Assets
- `base.html` shared layout with Bootstrap, nav/footer, flash messaging.
- `index.html` extends base, stacking carousel, submission form, and gallery grid of tribute cards with responsive Bootstrap columns (`col-12`, `col-sm-6`, `col-lg-4`).
- `tribute_detail.html` extends base for the dedicated full-page view with full message, metadata, and responsive photo gallery using `img-fluid` and flex utilities.
- Separate partials for carousel (`_carousel.html`), form (`_form.html`), tribute cards (`_tribute_list.html`), and optional photo grid (`_photo_grid.html`).
- Custom styles in `static/css/main.css`; optional JS enhancements in `static/js/main.js`.
- Add viewport meta tag in `base.html`, leverage Bootstrap utility classes, and sprinkle media-query tweaks for spacing/typography to keep the experience touch-friendly.

## Services & Utilities
- `services/storage.py` encapsulates base64 encoding/decoding and file validation.
- `services/tributes.py` (optional) to interact with the database, aiding testability.
- `services/notifications.py` posts activity updates to `https://ntfy.sh/JAYDEVSUBUDHINOTIFICATIONS` using `requests` when tributes/photos are created (wrap HTTP failures to avoid blocking user flow).
- Logging configuration for submissions and errors.

## Testing & Quality
- Unit tests for form validation, storage helpers, and model serialization.
- Integration tests using Flask test client for GET/POST flows (run via `uv run pytest`).
- Set up linting/formatting (e.g., `ruff`, `black`) and CI workflow if desired.

## Deployment & Operations
- Document local run commands (`uv run flask --app main.py --debug run`).
- Outline environment variable setup for production deployment.
- Ensure HTTPS/session settings in production (secure cookies, `SESSION_COOKIE_SECURE`).
- Serve `static/robots.txt` (Disallow all) to deter indexing.
- Future enhancement: containerization or `docker-compose` for local Postgres alternative.

## TODO Checklist
- [ ] Confirm final form fields and validation with stakeholder.
- [x] Provision Neon database; share `DATABASE_URL`.
- [ ] Scaffold Flask modules and initialize extensions.
- [ ] Create initial migration for `Tribute`; run `uv run flask db upgrade` on Neon.
- [ ] Implement carousel image loader and template integration.
- [ ] Build submission form with validation, base64 image handling, and storage logic.
- [ ] Implement routes to create/display tributes; add flash messaging.
- [ ] Wire notification service to publish to ntfy on new tributes.
- [ ] Finalize Jinja templates and static assets for UI components.
- [ ] Add automated tests, linting, and usage docs in `README.md`.
