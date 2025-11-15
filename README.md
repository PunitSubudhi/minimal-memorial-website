## Memorial Web Application

This project powers a memorial site where visitors can share tributes, upload photos, and browse memories contributed by others.

### Getting Started
- Install dependencies: `uv pip install -e .`
- Copy `.env.example` (if available) to `.env` and set `DATABASE_URL` plus `SECRET_KEY`.
- Run the development server: `uv run flask --app main.py --debug run`

### Database Migrations
- Initialize migrations: `uv run flask db init`
- Generate migrations: `uv run flask db migrate -m "describe change"`
- Apply migrations: `uv run flask db upgrade`

### Testing
- Execute the suite with `uv run pytest`

### Project Layout Highlights
- `app/__init__.py`: Flask application factory and blueprint registration.
- `app/routes.py`: Homepage and tribute detail routes.
- `app/services/`: Upload normalization, notification delivery, and tribute persistence helpers.
- `app/templates/`: Bootstrap-powered layouts with embedded CSS and components.
- `static/`: JavaScript hooks and carousel imagery (`static/images/`).

Carousel photos populate automatically from the `static/images/` directory. Uploaded tribute photos are converted to WebP before storing in the database to optimize size and display performance.

### Tribute Pagination
- Configure the initial batch size with `TRIBUTES_PER_PAGE` (defaults to 12). The server enforces an upper bound via `TRIBUTES_MAX_PER_PAGE` to keep responses light-weight.
- The tributes page renders the first batch and exposes a “Load more tributes” control that progressively fetches `/tributes/data?page=<n>` using JSON.
- Disable JavaScript to verify the fallback query-string pagination (`/tributes?page=2`) still works as expected.
