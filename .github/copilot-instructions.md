# Copilot Instructions for `memorial`

## Project Snapshot
- Deployed baseline: Flask memorial site with carousel hero, tribute submission form, tribute gallery, Neon Postgres storage, and ntfy notifications. See `.github/PLAN.md` for a full technical guide.
 - Deployed baseline: Flask memorial site with carousel hero, tribute submission form, tribute gallery, Neon Postgres storage, and ntfy notifications. See `.github/PLAN.md` for a full technical guide. Note: the site now separates the landing Home page (`/`) and the Tributes page (`/tributes`).
- Application is fully scaffolded—`app/` contains factory, routes, models, services, forms, templates, and tests. `static/` already hosts CSS/JS plus carousel imagery.
- Latest schema migration applied (`07075a1ea27e_use_timezone_aware_timestamps`). Tests (`uv run pytest`) cover storage helpers, service layer, and route flows.

## Architecture Highlights
- `app/__init__.py` builds the Flask app, binds the static folder to `<repo>/static`, registers extensions (`app/extensions.py`), blueprints (`app/routes.py`), and context processors (current year).
- Data layer lives in `app/models.py` (`Tribute`, `TributePhoto` with timezone-aware timestamp). Service helpers for uploads/notifications reside in `app/services/`.
- Forms (`app/forms.py`) enforce length and extension validation; `app/routes.py` orchestrates the homepage submission flow, detail page, and carousel discovery.
- Templates under `app/templates/` leverage Bootstrap 5 CDN and partials. Carousel styling is handled in `static/css/main.css` (`object-fit: contain` to preserve aspect ratios).
- Tests inhabit `tests/`, with fixtures creating a temp SQLite DB and path adjustments so the package imports correctly.

Additional notes for contributors
- The tributes listing and submission form are now on `/tributes` (function `index` in `app/routes.py`).
- A static `home.html` template is rendered at `/` and is intended for static text/pictures. See `.github/HOME_PAGE.md` for instructions.
- `app/templates/base.html` contains a small navbar linking Home (`/`) and Tributes (`/tributes`).

## Configuration & Environment
- `.env` is loaded automatically. Required variables: `DATABASE_URL`, `SECRET_KEY`; optional: `MAX_CONTENT_LENGTH`, `ALLOWED_EXTENSIONS`, `NTFY_TOPIC`.
- `app/config.py` normalizes Postgres URLs to `postgresql+psycopg://` and falls back to a SQLite file. Testing uses `DATABASE_URL_TEST` (set in fixtures).
- Carousel assets must be placed inside `static/images/`; filenames with spaces are acceptable.

## Workflows & Commands
- Use `uv` for all Python invocations:
	- Dev server: `uv run flask --app main.py --debug run`
	- Migrations: `uv run flask --app main.py db migrate -m "message"` and `uv run flask --app main.py db upgrade`
	- Tests: `uv run pytest`
- Avoid copying commands that include Markdown link syntax (square brackets); type them manually to keep zsh happy.

## Coding Conventions
- Default to ASCII for source files; reserve non-ASCII for user content or external assets.
- Keep comments concise and purposeful—only annotate non-obvious logic (e.g., conversion edge cases).
- Reuse service helpers instead of reimplementing conversion or notification logic inside routes/views.
- Ensure UI changes remain responsive and accessible; Bootstrap grid is already in place.

## Documentation Expectations
- Update `.github/PLAN.md`, `README.md`, and this file when adding features or changing workflows.
- Record new migrations and schema adjustments in the plan/backlog section.
- Note any third-party integrations or environment variable additions.

## Future Notes
- Backlog items (pagination, moderation, accessibility, linting) are listed in `.github/PLAN.md`. Tackle them incrementally; document assumptions and testing steps with each change.
- When adding new dependencies, update `pyproject.toml` and run `uv lock` if necessary.
