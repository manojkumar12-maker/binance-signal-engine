# Security Guide

- PAPER mode only by default. LIVE requires multiple independent flags and a marker file.
- Admin authentication uses hashed passwords (PBKDF2) and server-side sessions.
- Sessions are HTTP-only, SameSite, and Secure when HTTPS.
- Rate limiting on login.
- API secrets are never logged or returned.
- Kill switch persists in SQLite.
- No default admin password; set via environment.
- Protect dashboard with authentication before exposing publicly.
- Do not commit `.env` or database files.