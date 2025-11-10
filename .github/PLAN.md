# Memorial Web App Technical Guide

This document captures the current state of the memorial application so that future contributors can understand the system quickly and extend it safely.

## Current Feature Set
- Static homepage (`/`) reserved for site content (text and pictures) and a separate "Tributes" page at `/tributes` that serves the Bootstrap carousel, tribute submission form, and a gallery of recent tributes.
- Tribute detail view (`/tributes/<id>`) showcasing the full message and associated photos.
- Photo uploads converted to WebP, base64-stored, and rendered inline.
- Hero carousel populated automatically from `static/images/` with graceful fallback messaging; carousel and submission are rendered on the Tributes page.
- ntfy push notification dispatched after each successful tribute save.
- Neon Postgres persistence with Flask-Migrate migrations applied (latest revision `07075a1ea27e_use_timezone_aware_timestamps`).
- Automated tests for storage helpers, service layer, and core routes (`uv run pytest`). Note: some tests may need updates if they assumed the tributes listing was at `/`.

## Code Organization
- `main.py`: loads environment via `python-dotenv` and instantiates the Flask app factory.
- `app/__init__.py`: creates the application, registers extensions/blueprints/context processors, and pins the static folder to `<repo>/static`.
- `app/config.py`: environment-driven configuration with automatic normalization of `DATABASE_URL` (supports `postgres://`, `postgresql://`, SQLite fallback).
- `app/extensions.py`: SQLAlchemy, Migrate, and CSRFProtect instances.
- `app/models.py`: `Tribute` (timezone-aware `created_at`, JSON extras) and `TributePhoto` (ordered photo metadata).
- `app/forms.py`: `TributeForm` with name/message validation and extension whitelist checks.
- `app/routes.py`: the tributes listing and submission flow is available at `/tributes` (function `index`); a new static home route serves `home.html` at `/`.
- `app/services/`:
  - `storage.py`: Pillow-based normalization to WebP and base64 encoding (HEIC supported via pillow-heif if installed).
  - `tributes.py`: transactional creation of tributes and related photos.
  - `notifications.py`: ntfy webhook integration (non-blocking on failure).
- `app/templates/`: `base.html` (with embedded CSS and navbar), `index.html` (Tributes), `home.html` (static landing), `tribute_detail.html`, plus partials for carousel, form, and tribute listing.
- `static/`: `js/main.js` placeholder, `images/` for hero assets, `robots.txt` blocking crawlers.
- `migrations/`: Alembic environment with two applied revisions.
- `tests/`: pytest fixtures (SQLite temp DB) and coverage for storage/services/routes.

## Configuration & Environment
- `.env` is respected automatically (`load_dotenv()` in `main.py`). Key variables: `DATABASE_URL`, `SECRET_KEY`, optional `MAX_CONTENT_LENGTH`, `ALLOWED_EXTENSIONS`, `NTFY_TOPIC`.
- Default database fallback is SQLite file under the repo when `DATABASE_URL` is absent.
- Testing config uses a temporary SQLite database via `DATABASE_URL_TEST`; fixtures clean up automatically.

## Data Model Snapshot
- `Tribute`: id (PK, autoincrement), name, message, created_at (`timezone=True`), extra_fields (JSON), relationship to `TributePhoto` with `delete-orphan` cascade and selectin loading.
- `TributePhoto`: id, tribute_id FK (cascade delete), photo_b64 (TEXT), photo_content_type, display_order, caption.

## Frontend Behavior
- Carousel images use `object-fit: contain` to preserve aspect ratios inside a fixed 420px viewport with dark letterboxing. The site includes a navigation bar (in `app/templates/base.html`) linking Home (`/`) and Tributes (`/tributes`).
- Flash messages rendered via Bootstrap alerts.
- Gallery truncates messages with Jinja `truncate`, linking to detail view via stretched card link.

## Testing & Tooling
- Run tests with `uv run pytest` (pytest included in `pyproject.toml`).
- No linting/formatting tools are configured yet; consider adding Ruff/Black in future iterations.
- Note: update tests that expect tributes at `/` to use `/tributes`.

## Operational Notes
- Use `uv run flask --app main.py --debug run` for local dev server (ensuring the command is plain text in shells to avoid Markdown link substitution issues). After running the server, visit `/` for the Home page and `/tributes` for the tributes listing and submission form.
- Migrations:
  - `uv run flask --app main.py db migrate -m "<message>"`
  - `uv run flask --app main.py db upgrade`
- Carousel assets must reside under `static/images/`; filenames with spaces are supported.
- ntfy notifications default to `https://ntfy.sh/JAYDEVSUBUDHINOTIFICATIONS` unless overridden.

## Backlog & Ideas
- Refine form copy and validation once stakeholder feedback is available.
- Add pagination or lazy loading for tributes if volume grows.
- Provide admin moderation or deletion tools.
- Enhance accessibility (ARIA roles for carousel, alt text customizations for uploaded photos).
- Add smoke/integration tests for image upload workflows (currently covered indirectly via services).
- Integrate linting/formatting and CI automation.

## Recent changes
- Split the landing and tributes workflows: the landing page `/` is now a static Home template (`app/templates/home.html`) and the tributes listing/submission moved to `/tributes` (route `index` in `app/routes.py`).
- Added a small site navbar in `app/templates/base.html` linking Home and Tributes.
- Added `.github/HOME_PAGE.md` with instructions for adding content to the Home page.

Keep this guide updated whenever the architecture or workflows evolve so future contributors have an accurate reference point.
