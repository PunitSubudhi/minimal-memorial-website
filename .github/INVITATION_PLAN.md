# Invitation Page Plan

This document describes the plan to add a new `invitation` page to the memorial website. The page will be added as `/invitation` and will present an invitation hero image, event details, embedded Google Maps with a link to open in Google Maps, a "Get in touch" contact section with WhatsApp links, and a CTA to the Tributes page.

---

## Overview

Create a simple static invitation page with the following components:

- Hero image (hosted on S3)
- Event details (date & time)
- Embedded Google Maps with an "Open in Google Maps" link
- "Get in touch" section with 4 contact cards; clicking a card opens WhatsApp using `wa.me/<countrycode><number>`
- CTA prompting visitors to add Tributes (link to `/tributes`)

The page is static and requires only a GET route to render the template.

---

## Files to add / modify

- `app/routes.py` — add a `@main_bp.route("/invitation")` view that renders `invitation.html`.
- `app/templates/invitation.html` — new template implementing the full page layout.
- `app/templates/base.html` — add a navbar link to the Invitation page (label: "Invitation").
- Optional: `static/css/main.css` — small additions for responsive map container and contact card hover styles (or include scoped inline styles in the template).
- `README.md` / `.github/PLAN.md` — (optional) note that the invitation page was added.

---

## Template structure (`invitation.html`)

Suggested structure (Bootstrap 5):

1. Hero image (top)
   - Use the S3 URL: `https://778bff83-75d6-44df-b16e-6f9c816261c4.s3.us-east-2.amazonaws.com/recipe-images/homepagepic.webp`
   - `img-fluid rounded mx-auto d-block` with `max-height` and `object-fit: cover` to match site styling.

2. Event Details
   - Heading: "Event Details"
   - Date line: "🗓️ 16 November, Sunday"
   - Time line: "🕣 7:00 PM"
   - Use a simple card or bordered box for emphasis.

3. Venue & Map
   - Heading: "Event Location"
   - Responsive map wrapper (maintain aspect ratio) with the provided iframe embed.
   - A button/link under the map: "Open in Google Maps" — this should point to the full Google Maps URL (same location) and open in a new tab (`target="_blank" rel="noopener noreferrer"`).

4. Get in touch
   - Heading: "Get in touch"
   - Responsive grid of 4 contact cards. Each card contains:
     - Contact name
     - Telephone number (displayed)
     - The card (or a button inside it) is a link to `https://wa.me/<countrycode><number>` so clicking opens WhatsApp chat.
   - Example link format for India numbers: `https://wa.me/91xxxxxxxxxx` (no `+` or spaces).

5. CTA: Add Tributes
   - Prominent card or alert with a button linking to `{{ url_for('main.index') }}` (the Tributes page) and inviting people to "Share your memories".

---

## Accessibility & UX considerations

- Provide descriptive `alt` text for the hero image.
- Use semantic headings (h1/h2) and a logical heading order.
- Ensure the map iframe has `title="Event location map"`.
- WhatsApp links should include `rel="noopener noreferrer"` and open in a new tab to avoid losing the site.

---

## Contacts

Add four contact cards. The route rendering the template can pass a static list of contacts, or they may be hard-coded in the template. Each contact should include:

- `name` — displayed on the card
- `phone_display` — formatted for display (e.g., `+91 98765 43210`)
- `phone_link` — digits-only with country code for the `wa.me` link (e.g., `919876543210`)

Example contacts placeholder (update with real numbers when provided):

- Name: `Rajesh Kumar` — Phone (display): `+91 98111 22233` — wa.me link: `https://wa.me/919811122233`
- Name: `Sushma Devi` — Phone (display): `+91 98765 43210` — wa.me link: `https://wa.me/919876543210`
- Name: `Anil Sahu` — Phone (display): `+91 91234 56789` — wa.me link: `https://wa.me/919123456789`
- Name: `Priya Nanda` — Phone (display): `+91 90000 11122` — wa.me link: `https://wa.me/919000011122`

> Note: Replace the example contacts with actual contact details before publishing.

---

## Small CSS suggestions

If adding to `static/css/main.css` or inline in the template, consider the following small rules:

- Responsive map wrapper (16:9 or 4:3):

```css
.map-responsive {
  position: relative;
  padding-bottom: 56.25%; /* 16:9 */
  height: 0;
  overflow: hidden;
}
.map-responsive iframe {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: 0;
}
```

- Contact card hover:

```css
.contact-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.06);
}
```

(These are intentionally small, safe, and additive.)

---

## Testing checklist (manual)

- [ ] Load `/invitation` and verify it returns HTTP 200.
- [ ] Hero image loads successfully from S3.
- [ ] Event date and time are displayed correctly.
- [ ] Map iframe renders and the "Open in Google Maps" link opens the correct location.
- [ ] Each contact card opens the WhatsApp link when clicked.
- [ ] CTA to Tributes page works and navigates to `/tributes`.
- [ ] Page looks good on mobile, tablet, and desktop widths.

---

## Next steps after creating the page

1. Replace placeholder contact names and numbers with final contact info.
2. Consider adding optional Google Maps parameters (like a direct Google Maps URL) if needed.
3. If the page needs to be translated or localized, extract the strings for easy translation.
4. Optionally add a tiny analytics event for the "Open in Google Maps" button and contact clicks.

---

## Revision history

- 2025-11-10 — Initial plan drafted and saved.

---

_End of plan._
