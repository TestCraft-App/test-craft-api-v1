# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

TestCraft API — a Python/Flask REST API that proxies requests to OpenAI to generate test ideas, automation scripts, and accessibility reports from HTML elements. Deployed on Google Cloud Run.

## Running Locally

```bash
cp example.env .env  # Set FLASK_ENV=local and your OPENAI_API_KEY
pip install -r requirements.txt
python main.py       # Runs on http://localhost:8080
```

Environment variables (see `example.env`):
- `FLASK_ENV=local` — required for local dev (skips GCP Secret Manager)
- `OPENAI_API_KEY` — your OpenAI key
- `PROJECT_ID` — GCP project ID (only needed in production)
- `GOOGLE_CLIENT_ID` — Google OAuth Client ID (for v2 free tier auth)

## Architecture

- **`main.py`** — Flask app factory. Registers the `api` Blueprint, enables CORS. Port from `PORT` env var (default 8080).
- **`app/api.py`** — All routes in a single Blueprint. Handles prompt construction, OpenAI API calls, token counting (tiktoken), HTML minification, and SSE streaming.
- **`app/config.py`** — Config class. In production (`FLASK_ENV != local`), fetches the API key from GCP Secret Manager. Locally, reads from `.env` via python-dotenv.
- **`app/decorators.py`** — `@query_params()` decorator. Extracts JSON body fields, converts camelCase to snake_case, maps them to function parameters. Returns 400 if required params are missing.

### API Endpoints

| Method | Route | Purpose | Streaming |
|--------|-------|---------|-----------|
| GET | `/api/ping` | Health check | No |
| GET | `/api/models` | List available OpenAI models | No |
| POST | `/api/generate-ideas` | Generate test ideas from HTML | Yes |
| POST | `/api/automate-tests` | Generate automation code | Yes |
| POST | `/api/automate-tests-ideas` | Automate selected test ideas | Yes |
| POST | `/api/check-accessibility` | WCAG 2.1 accessibility check | Yes |
| POST | `/api/get-regex-for-run` | Generate Mocha grep regex | No |

All POST endpoints accept an optional `openAiApiKey` to use the caller's key instead of the server's.

### v2 API Endpoints (Free Tier with Google OAuth)

| Method | Route | Purpose | Auth Required |
|--------|-------|---------|---------------|
| GET | `/api/v2/ping` | Health check (v2) | No |
| POST | `/api/v2/stream` | Proxy prompt to OpenAI (gpt-5.6-luna) via SSE | Yes |
| GET | `/api/v2/auth/me` | Get user info + daily usage count | Yes |

**v2 Architecture:**
- `app/auth.py` — `validate_google_token()` verifies Google ID tokens, `@require_auth` decorator protects endpoints
- `app/firestore.py` — Firestore operations: `get_or_create_user()`, `get_daily_usage()`, `increment_usage()`, `is_limit_reached()`
- Free tier forces `gpt-5.6-luna` server-side (defense in depth)
- Daily limit: 10 generations/day per user (429 when exceeded)
- Usage tracked in Firestore: `users/{googleId}/usage/{YYYY-MM-DD}` with atomic increment

**Firestore Schema:**
```
users/{googleId}:
  email, name, picture, createdAt, lastLoginAt

users/{googleId}/usage/{YYYY-MM-DD}:
  count: number
```

### Key Design Details

- Streaming endpoints return SSE (`text/event-stream`). Non-streaming returns JSON.
- GPT-5.6 Sol, Terra, and Luna use medium reasoning and omit `temperature`. Explicitly supplied older models retain their existing request parameters.
- HTML is minified and script tags stripped before being included in prompts (`parse_html()`).
- Token count is validated against model limits before calling OpenAI; returns 413 if too large.

## Security Rules

**Before merging any PR, verify ALL of the following:**

1. **No secrets in code** — Never commit API keys, tokens, passwords, or credentials. `.env` must stay gitignored. Use `example.env` for templates (no real values).
2. **No secrets in logs** — Never `print()` or log API keys, tokens, or full error responses that may contain secrets. Use structured logging with sanitized output.
3. **No `eval()` or `exec()`** — No dynamic code execution.
4. **Input validation** — Validate and sanitize all user input (HTML, prompts, API keys) before processing. Don't trust client-provided data.
5. **Auth required on sensitive endpoints** — All v2 endpoints that consume resources (OpenAI calls, Firestore writes) must use `@require_auth`.
6. **Error messages must not leak internals** — Don't expose stack traces, file paths, config values, or secrets in API responses. Return generic error messages.
7. **HTTPS only** — All external API calls must use `https://`.
8. **Firestore transactions** — Use atomic increments for usage counters to prevent race conditions.
9. **Token validation** — Google ID tokens must be verified with `google.oauth2.id_token.verify_oauth2_token()` — never trust unverified JWTs.
10. **Dependencies** — Review new dependencies for known vulnerabilities. Pin versions in `requirements.txt`.
11. **CORS** — Currently permissive (`CORS(app)`). When restricting, whitelist only the extension's origin.
12. **Cloud Run** — Uses `--allow-unauthenticated` because the API handles its own auth. Ensure all resource-consuming endpoints are protected by `@require_auth` or API key validation.

## Code Style

- flake8: `max-line-length = 120`, excludes `.git`, `__pycache__`, `build`, `dist`, `venv`

## CI/CD

GitHub Actions (`.github/workflows/main.yml`): pushes to `main` deploy to production Cloud Run service (`openai-api-proxy`), pushes to `dev` deploy to development (`openai-api-proxy-dev`). Builds Docker image via `gcloud builds submit`.

## Docker

Python 3.11-slim, gunicorn with 1 worker / 80 threads, port 8080.
