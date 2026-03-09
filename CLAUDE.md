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
| POST | `/api/v2/stream` | Proxy prompt to OpenAI (gpt-4o-mini) via SSE | Yes |
| GET | `/api/v2/auth/me` | Get user info + daily usage count | Yes |

**v2 Architecture:**
- `app/auth.py` — `validate_google_token()` verifies Google ID tokens, `@require_auth` decorator protects endpoints
- `app/firestore.py` — Firestore operations: `get_or_create_user()`, `get_daily_usage()`, `increment_usage()`, `is_limit_reached()`
- Free tier forces `gpt-4o-mini` server-side (defense in depth)
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
- `o1-mini` model uses only a `user` message (no `developer` role). Other o-series models (o1, o3) skip the `temperature` parameter.
- HTML is minified and script tags stripped before being included in prompts (`parse_html()`).
- Token count is validated against model limits before calling OpenAI; returns 413 if too large.

## Code Style

- flake8: `max-line-length = 120`, excludes `.git`, `__pycache__`, `build`, `dist`, `venv`

## CI/CD

GitHub Actions (`.github/workflows/main.yml`): pushes to `main` deploy to production Cloud Run service (`openai-api-proxy`), pushes to `dev` deploy to development (`openai-api-proxy-dev`). Builds Docker image via `gcloud builds submit`.

## Docker

Python 3.11-slim, gunicorn with 1 worker / 80 threads, port 8080.
