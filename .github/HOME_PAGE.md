# Home page (static)

This file describes the new Home page and how to add content to it.

Purpose
- The home page is a static landing page for the site. It is rendered from `app/templates/home.html` and is available at `/`.
- The existing tributes listing and submission form are now served from `/tributes` (function name `index` in `app/routes.py`).

How to add content
1. Edit `app/templates/home.html` to add text, images and sections.
2. Place images in `static/images/` and reference them in templates with `{{ url_for('static', filename='images/your-image.jpg') }}`.
3. For reusable sections, create partial templates under `app/templates/partials/` and include them with `{% include 'partials/your_partial.html' %}`.

Notes for maintainers
- The navigation bar in `app/templates/base.html` contains links to Home (`/`) and Tributes (`/tributes`).
- The tribute submission flow still redirects to `url_for('main.index')` so form success behavior is unchanged (it will go to `/tributes`).

Next steps (suggestions)
- Replace the placeholder content in `home.html` with the desired text and images.
- Add any additional static pages (about, contact) and nav links if needed.
