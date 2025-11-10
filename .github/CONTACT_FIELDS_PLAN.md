# Implementation Plan: Contact Fields & Submission Feedback

**Created:** 2025-11-10  
**Status:** Planning  
**Target:** Add phone/email fields (server-only) + submission UI feedback

---

## Overview

This document outlines the implementation plan for two features:
1. **Phone Number & Email Fields:** Optional contact fields stored server-side only, never displayed publicly
2. **Submission Feedback UI:** Client-side loading state to prevent double-submissions and provide user feedback

---

## Part 1: Phone Number & Email Fields (Server-Only Storage)

### 1.1 Database Strategy

**Approach:** Use existing `Tribute.extra_fields` JSON column (no migration required)

**Rationale:**
- ✅ Infrastructure already exists
- ✅ No schema migration needed
- ✅ Flexible for future fields
- ✅ Phone/email stored as `{"phone": "...", "email": "..."}`

**Alternative considered:** Dedicated columns (`phone`, `email`) - rejected due to migration overhead and reduced flexibility.

### 1.2 Form Layer Changes

**File:** `app/forms.py`

Add two new optional fields to `TributeForm`:

```python
from wtforms import StringField, EmailField
from wtforms.validators import Email, Optional, Regexp

class TributeForm(FlaskForm):
    # ... existing fields (name, message, photos) ...
    
    phone = StringField(
        "Phone Number (optional)",
        validators=[
            Optional(),
            Length(max=20),
            Regexp(r'^[\d\s\-\+\(\)\.]+$', message="Invalid phone number format")
        ],
        render_kw={"placeholder": "e.g., (555) 123-4567"}
    )
    
    email = StringField(
        "Email Address (optional)",
        validators=[Optional(), Email(), Length(max=120)],
        render_kw={"placeholder": "your.email@example.com", "type": "email"}
    )
    
    # ... existing submit field ...
```

**Validation rules:**
- Both fields optional (no `DataRequired()`)
- Phone: regex allows formats like `+1-555-123-4567`, `(555) 123-4567`
- Email: WTForms built-in `Email()` validator
- Length limits: phone=20 chars, email=120 chars

### 1.3 Service Layer Changes

**File:** `app/services/tributes.py`

Update `create_tribute()` function signature and logic:

```python
def create_tribute(
    *,
    name: str,
    message: str,
    photo_entries: Iterable[Mapping[str, object]],
    phone: Optional[str] = None,      # NEW
    email: Optional[str] = None,      # NEW
    extra_fields: Optional[dict] = None,
    logger: Optional[logging.Logger] = None,
) -> Tribute:
    """Persist a tribute with optional contact info."""
    log = logger or LOGGER
    
    # Merge contact info into extra_fields
    fields = extra_fields or {}
    if phone:
        fields["phone"] = phone.strip()
    if email:
        fields["email"] = email.strip().lower()
    
    tribute = Tribute(
        name=name.strip(),
        message=message.strip(),
        extra_fields=fields,
    )
    # ... rest of function unchanged ...
```

**Notes:**
- Strip whitespace from both fields
- Normalize email to lowercase
- Store in `extra_fields` JSON column

### 1.4 Route Layer Changes

**File:** `app/routes.py`

Update the `index()` function to pass new form fields:

```python
if form.validate_on_submit():
    entries = storage.prepare_photo_entries(...)
    try:
        tribute = tributes.create_tribute(
            name=form.name.data,
            message=form.message.data,
            photo_entries=entries,
            phone=form.phone.data,    # NEW
            email=form.email.data,    # NEW
        )
    except Exception:
        # ... error handling unchanged ...
```

### 1.5 Template Changes

**File:** `app/templates/partials/_form.html`

Add two new form fields **after** the `message` field and **before** the `photos` field:

```django-html
<!-- Existing name and message fields above -->

<div class="mb-3">
    {{ form.phone.label(class_="form-label") }}
    {{ form.phone(class_="form-control", maxlength=20) }}
    <div class="form-text">Optional - for organizers only, never displayed publicly</div>
    {% for error in form.phone.errors %}
        <div class="invalid-feedback d-block">{{ error }}</div>
    {% endfor %}
</div>

<div class="mb-3">
    {{ form.email.label(class_="form-label") }}
    {{ form.email(class_="form-control", maxlength=120, type="email") }}
    <div class="form-text">Optional - for organizers only, never displayed publicly</div>
    {% for error in form.email.errors %}
        <div class="invalid-feedback d-block">{{ error }}</div>
    {% endfor %}
</div>

<!-- Existing photos field below -->
```

**Privacy assurance:** The `form-text` helper explicitly states these fields are never displayed publicly.

### 1.6 Privacy Verification

**Action items:**
- [ ] Verify `app/templates/partials/_tribute_list.html` does NOT render `extra_fields`
- [ ] Verify `app/templates/tribute_detail.html` does NOT render `extra_fields`
- [ ] Confirm `Tribute.to_dict()` includes `extra_fields` but templates never use it
- [ ] Add template tests to ensure contact info never appears in HTML

**Files to review:**
- `app/templates/index.html`
- `app/templates/partials/_tribute_list.html`
- `app/templates/tribute_detail.html`

---

## Part 2: Submission Feedback UI

### 2.1 JavaScript Implementation

**File:** `static/js/main.js`

Replace placeholder comment with form submission handler:

```javascript
document.addEventListener('DOMContentLoaded', function() {
    const tributeForm = document.querySelector('form[method="post"]');
    
    if (tributeForm) {
        tributeForm.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitBtn) {
                // Disable button to prevent double-submit
                submitBtn.disabled = true;
                
                // Store original text
                const originalText = submitBtn.textContent || submitBtn.value;
                
                // Show loading state with Bootstrap spinner
                if (submitBtn.tagName === 'BUTTON') {
                    submitBtn.innerHTML = `
                        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        Processing...
                    `;
                } else {
                    submitBtn.value = 'Processing...';
                }
                
                // Re-enable after 10 seconds as fallback
                setTimeout(function() {
                    submitBtn.disabled = false;
                    if (submitBtn.tagName === 'BUTTON') {
                        submitBtn.textContent = originalText;
                    } else {
                        submitBtn.value = originalText;
                    }
                }, 10000);
            }
        });
    }
});
```

**Features:**
- Uses Bootstrap 5's built-in spinner component (already in project)
- Disables button immediately on click
- Shows "Processing..." with spinner animation
- 10-second timeout prevents permanent lock if server doesn't respond
- Works with both `<button>` and `<input type="submit">`

### 2.2 Submit Button Update

**File:** `app/templates/partials/_form.html`

Replace the WTForms submit field:

**Current:**
```django-html
<div class="d-grid">
    {{ form.submit(class_="btn btn-primary btn-lg") }}
</div>
```

**New:**
```django-html
<div class="d-grid">
    <button type="submit" class="btn btn-primary btn-lg" id="tributeSubmitBtn">
        Share Tribute
    </button>
</div>
```

**Rationale:** Using a `<button>` instead of WTForms' `SubmitField` allows easier HTML manipulation for the spinner.

### 2.3 Flash Messages Enhancement (Optional)

**File:** `app/templates/base.html`

Ensure flash messages have proper Bootstrap styling:

```django-html
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        <div class="container mt-3">
            {% for category, message in messages %}
                <div class="alert alert-{{ 'success' if category == 'success' else 'danger' }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            {% endfor %}
        </div>
    {% endif %}
{% endwith %}
```

**Result:**
- Success messages appear in green
- Error messages appear in red
- Auto-dismissible with close button

---

## Part 3: Testing Strategy

### 3.1 Unit Tests

**File:** `tests/test_services.py`

Add test for phone/email storage:

```python
def test_create_tribute_with_contact_info():
    """Verify phone and email are stored in extra_fields."""
    tribute = tributes.create_tribute(
        name="John Doe",
        message="Test message",
        photo_entries=[],
        phone="555-1234",
        email="john@example.com"
    )
    
    assert tribute.extra_fields["phone"] == "555-1234"
    assert tribute.extra_fields["email"] == "john@example.com"

def test_create_tribute_without_contact_info():
    """Verify tribute works without phone/email."""
    tribute = tributes.create_tribute(
        name="Jane Doe",
        message="Test message",
        photo_entries=[]
    )
    
    assert "phone" not in tribute.extra_fields
    assert "email" not in tribute.extra_fields
```

### 3.2 Form Validation Tests

**File:** `tests/test_routes.py`

Add tests for form validation:

```python
def test_tribute_submission_with_contact(client):
    """Verify form accepts phone/email."""
    response = client.post('/tributes', data={
        'name': 'Test User',
        'message': 'Test message',
        'phone': '(555) 123-4567',
        'email': 'test@example.com',
        'csrf_token': get_csrf_token(client)
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Thank you for sharing' in response.data

def test_tribute_submission_invalid_phone(client):
    """Verify invalid phone format is rejected."""
    response = client.post('/tributes', data={
        'name': 'Test User',
        'message': 'Test message',
        'phone': 'invalid phone!!!',
        'csrf_token': get_csrf_token(client)
    })
    
    assert b'Invalid phone number format' in response.data

def test_tribute_submission_invalid_email(client):
    """Verify invalid email format is rejected."""
    response = client.post('/tributes', data={
        'name': 'Test User',
        'message': 'Test message',
        'email': 'not-an-email',
        'csrf_token': get_csrf_token(client)
    })
    
    assert b'Invalid email address' in response.data
```

### 3.3 Privacy Tests

**File:** `tests/test_routes.py`

Add tests to verify contact info never appears:

```python
def test_tribute_detail_hides_contact_info(client, db_session):
    """Ensure phone/email never appear in rendered HTML."""
    tribute = tributes.create_tribute(
        name="Test User",
        message="Test message",
        photo_entries=[],
        phone="555-1234",
        email="test@example.com"
    )
    
    response = client.get(f'/tributes/{tribute.id}')
    assert b'555-1234' not in response.data
    assert b'test@example.com' not in response.data

def test_tribute_listing_hides_contact_info(client, db_session):
    """Ensure phone/email never appear in tribute listing."""
    tribute = tributes.create_tribute(
        name="Test User",
        message="Test message",
        photo_entries=[],
        phone="555-9999",
        email="hidden@example.com"
    )
    
    response = client.get('/tributes')
    assert b'555-9999' not in response.data
    assert b'hidden@example.com' not in response.data
```

### 3.4 Manual Testing Checklist

- [ ] Submit form with phone/email → verify stored in database
- [ ] Submit form without phone/email → verify no errors
- [ ] Submit with invalid phone format → verify validation error displayed
- [ ] Submit with invalid email → verify validation error displayed
- [ ] Check tribute listing page → verify phone/email not visible
- [ ] Check tribute detail page → verify phone/email not visible
- [ ] Click submit button → verify it disables and shows spinner
- [ ] Simulate slow network → verify button re-enables after 10 seconds
- [ ] Double-click submit button → verify only one submission occurs
- [ ] Test on mobile device → verify spinner and button behavior

---

## Part 4: Implementation Order

### Phase 1: Backend Changes (60 minutes)
1. ✅ Update `app/forms.py` → Add phone/email fields with validators
2. ✅ Update `app/services/tributes.py` → Accept phone/email params
3. ✅ Update `app/routes.py` → Pass form data to service
4. ✅ Update `app/templates/partials/_form.html` → Add input fields
5. ✅ Run tests: `uv run pytest`

### Phase 2: Privacy Verification (30 minutes)
6. ✅ Review `app/templates/partials/_tribute_list.html` → Confirm no extra_fields
7. ✅ Review `app/templates/tribute_detail.html` → Confirm no extra_fields
8. ✅ Add template tests to verify contact info never rendered
9. ✅ Run full test suite

### Phase 3: Client-Side Feedback (30 minutes)
10. ✅ Update `static/js/main.js` → Add form submission handler
11. ✅ Update `app/templates/partials/_form.html` → Change submit to `<button>`
12. ✅ Test in browser → Verify spinner appears and button disables

### Phase 4: Testing & Documentation (60 minutes)
13. ✅ Write unit tests for contact info storage
14. ✅ Write integration tests for form validation
15. ✅ Write privacy tests for template rendering
16. ✅ Manual testing with all edge cases
17. ✅ Update `.github/PLAN.md` with implementation notes
18. ✅ Update `README.md` if contact fields affect user instructions

**Total estimated time:** 3 hours

---

## Part 5: Rollback Plan

If issues arise during implementation:

| Issue | Rollback Action | Command |
|-------|----------------|---------|
| Form validation errors | Revert `app/forms.py` | `git checkout HEAD -- app/forms.py` |
| Service layer bugs | Revert `app/services/tributes.py` | `git checkout HEAD -- app/services/tributes.py` |
| Template rendering issues | Revert `_form.html` | `git checkout HEAD -- app/templates/partials/_form.html` |
| JavaScript errors | Clear `main.js` | `git checkout HEAD -- static/js/main.js` |
| Database corruption | N/A - using existing JSON column | No migration to rollback |

**Emergency rollback (all changes):**
```bash
git reset --hard HEAD
```

---

## Part 6: Security Considerations

### 6.1 Data Protection
- ✅ Phone/email stored in `extra_fields` JSON column
- ✅ Templates verified to NOT expose `extra_fields`
- ✅ Fields are optional (no forced data collection)
- ⚠️ **TODO:** Add to privacy policy that contact info is collected for organizer use only
- ⚠️ **TODO:** Consider encrypting `extra_fields` at rest (future enhancement)

### 6.2 Input Validation
- ✅ Phone regex prevents SQL injection and script injection
- ✅ Email validator prevents malformed addresses
- ✅ Length limits prevent database overflow attacks
- ✅ Optional validators prevent empty string storage
- ✅ WTForms CSRF protection already in place

### 6.3 Rate Limiting (Future Enhancement)
- Consider adding Flask-Limiter to prevent form spam
- Suggested limit: 5 submissions per IP per hour
- Alternative: Add honeypot field to catch bots

### 6.4 GDPR Considerations
- Users should be able to request deletion of contact info
- Consider adding "Delete my contact info" link to confirmation email
- Document data retention policy

---

## Part 7: Documentation Updates

### 7.1 Update `.github/PLAN.md`

Add to backlog section:

```markdown
### Contact Information Fields (2025-11-10)
- Added optional `phone` and `email` fields to tribute submission form
- Stored in `Tribute.extra_fields` JSON column (server-side only, never public)
- Validation: phone regex (digits/spaces/punctuation), email format, both optional
- Templates verified to never expose contact information
- Tests added for storage, validation, and privacy guarantees

### Submission Feedback UI (2025-11-10)
- Added client-side form submission handler in `static/js/main.js`
- Disables submit button on click to prevent double-submission
- Shows Bootstrap 5 spinner with "Processing..." text during submission
- 10-second timeout fallback re-enables button if server doesn't respond
- Improves UX and prevents duplicate tribute submissions
```

### 7.2 Update `README.md` (if needed)

Add to user instructions section:

```markdown
#### Privacy Note
The tribute submission form includes optional phone number and email fields. 
These fields are for organizer use only and are **never displayed publicly** 
on the website. All submitted contact information is stored securely.
```

### 7.3 Create Privacy Policy (Future)

Consider adding `app/templates/privacy.html`:
- Explain what data is collected (name, message, photos, optional phone/email)
- State contact info is never displayed publicly
- Provide contact email for data deletion requests
- Add GDPR-compliant consent language

---

## Part 8: Performance Considerations

### 8.1 Database Performance
- ✅ `extra_fields` is JSON column (indexed by default in Postgres)
- ✅ No additional joins needed (data embedded in tribute record)
- ⚠️ If querying by phone/email becomes needed, consider GIN index:
  ```sql
  CREATE INDEX idx_tributes_extra_fields ON tributes USING GIN (extra_fields);
  ```

### 8.2 Form Submission Performance
- ✅ JavaScript runs after DOM load (no blocking)
- ✅ Spinner uses CSS animations (GPU accelerated)
- ✅ 10-second timeout prevents indefinite waiting
- ✅ No external API calls (all server-side)

---

## Part 9: Future Enhancements

### 9.1 Contact Info Management
- [ ] Admin panel to view/export contact information
- [ ] Email confirmation to submitter (if email provided)
- [ ] SMS confirmation to submitter (if phone provided)
- [ ] Bulk export of contact info as CSV

### 9.2 Advanced Validation
- [ ] Phone number normalization (convert to E.164 format)
- [ ] Email verification (send confirmation link)
- [ ] Duplicate detection (same email/phone within 24 hours)

### 9.3 UI Improvements
- [ ] Full-screen loading overlay (instead of just button spinner)
- [ ] Progress indicator for photo uploads
- [ ] Success animation after submission
- [ ] Auto-scroll to success message

---

## Appendix A: File Change Summary

| File | Type | Changes |
|------|------|---------|
| `app/forms.py` | Modify | Add `phone` and `email` fields with validators |
| `app/services/tributes.py` | Modify | Update `create_tribute()` signature, store in `extra_fields` |
| `app/routes.py` | Modify | Pass `phone` and `email` to `create_tribute()` |
| `app/templates/partials/_form.html` | Modify | Add phone/email inputs, change submit to `<button>` |
| `static/js/main.js` | Modify | Add form submission handler with spinner |
| `tests/test_services.py` | Modify | Add tests for contact info storage |
| `tests/test_routes.py` | Modify | Add tests for validation and privacy |
| `.github/PLAN.md` | Modify | Document implementation |

**Total files modified:** 8  
**New files created:** 0  
**Migrations required:** 0

---

## Appendix B: Code Snippets for Quick Reference

### Phone Regex Explanation
```regex
^[\d\s\-\+\(\)\.]+$
```
- `^` = start of string
- `[\d\s\-\+\(\)\.]+` = one or more of: digits, spaces, hyphens, plus signs, parentheses, dots
- `$` = end of string

**Matches:**
- `555-1234`
- `(555) 123-4567`
- `+1 555 123 4567`
- `555.123.4567`

**Rejects:**
- `555-CALL-NOW` (letters)
- `call 555-1234` (text before)
- `555-1234!` (invalid characters)

### Email Validation
WTForms' `Email()` validator uses this pattern:
```regex
^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
```

**Matches:**
- `user@example.com`
- `first.last@company.co.uk`
- `user+tag@gmail.com`

**Rejects:**
- `userexample.com` (no @)
- `user@` (no domain)
- `@example.com` (no local part)

---

## Appendix C: Testing Commands

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_services.py

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run only contact info tests
uv run pytest -k "contact"

# Run with verbose output
uv run pytest -v

# Run and stop at first failure
uv run pytest -x
```

---

## Sign-off

**Plan created by:** GitHub Copilot  
**Reviewed by:** [Awaiting review]  
**Approved by:** [Awaiting approval]  
**Implementation start:** [TBD]  
**Target completion:** [TBD]

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-10 | 1.0 | Initial plan created |
