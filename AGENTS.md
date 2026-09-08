# AGENTS.md

## Scope and priorities

- These instructions apply to the entire repository.
- Follow the user's request over this file when they conflict.
- Keep changes focused. Preserve existing routes, response shapes, streaming behavior, and deployment behavior unless the task explicitly changes them.
- Do not mix opportunistic model migrations, dependency upgrades, or broad refactors into an unrelated change.

## Repository overview

TestCraft API is a Python 3.11 Flask API deployed to Google Cloud Run. It proxies requests to OpenAI to generate test ideas, automation code, regular expressions, and accessibility reports. The `/api/v2` endpoints add Google ID-token authentication and a Firestore-backed daily free-tier limit.

## Important files

- `main.py`: Flask application factory, CORS setup, and Blueprint registration.
- `app/api.py`: Routes, prompt construction, model selection, token checks, OpenAI calls, and SSE streaming.
- `app/config.py`: Local `.env` loading and production access to GCP Secret Manager and Cloud Logging.
- `app/decorators.py`: JSON-body extraction and camelCase-to-snake_case parameter mapping.
- `app/auth.py`: Google ID-token validation and the `@require_auth` decorator.
- `app/firestore.py`: User records and UTC daily-usage accounting.
- `.github/workflows/main.yml`: Automatic Cloud Run deployments from `main` and `dev`.

## Local setup

1. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

2. Activate `.venv` using the command for the current shell, then install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy `example.env` to `.env` and set at least:

   ```dotenv
   FLASK_ENV=local
   OPENAI_API_KEY=your-key
   ```

4. Start the server:

   ```bash
   python main.py
   ```

The server listens on port `8080` by default. Always use `FLASK_ENV=local` for local commands that import the application; otherwise `Config` treats the environment as production and may try to access GCP Secret Manager during import. Never commit `.env` or real credentials.

## Validation

There is currently no automated test suite. Run the narrowest checks appropriate to the change and report exactly what was run.

- For every Python change, check syntax/import-independent compilation:

  ```bash
  python -m compileall -q main.py app
  ```

- For changes to application setup or basic routing, run this local smoke test without contacting OpenAI or GCP:

  ```bash
  python -c "import os; os.environ['FLASK_ENV']='local'; from main import create_app; c=create_app().test_client(); assert c.get('/api/ping').status_code == 200; assert c.get('/api/v2/ping').status_code == 200"
  ```

- `.flake8` sets a 120-character line limit. Run `python -m flake8 .` when flake8 is available; it is not currently declared in `requirements.txt`, so do not claim this check passed if the module is missing.
- Tests must not make real OpenAI, Google OAuth, Secret Manager, Cloud Logging, or Firestore calls. Mock external clients and responses.
- For dependency or container changes, build the Docker image locally when Docker is available. Do not run `gcloud builds submit` or deploy unless the user explicitly asks.

## API and implementation contracts

- Keep route handlers on the `api` Blueprint and register it through `create_app()`.
- `@query_params()` maps JSON camelCase fields to snake_case function parameters. Preserve this client-facing contract when changing handler signatures.
- Streaming endpoints return `text/event-stream` chunks in `data: <json>\n\n` format. Do not replace streaming responses with buffered JSON accidentally.
- Return intentional Flask status codes and sanitized JSON errors. Do not expose stack traces, configuration values, provider response bodies, or credentials.
- The v2 free-tier stream must keep its server-selected model; do not accept a client model override without an explicit product change.
- Daily limits use UTC dates. Changes to quota enforcement must consider concurrent requests: checking the limit and incrementing usage separately can race even if the write itself uses a transaction.
- Treat changes to supported OpenAI models, message roles, token limits, or request parameters as compatibility-sensitive. Verify current official OpenAI documentation before changing them and avoid model migrations unless requested.

## Security requirements

- Never add secrets, tokens, passwords, project credentials, or real user data to code, fixtures, logs, examples, or error responses.
- Treat HTML, prompts, API keys, authorization headers, model names, and other request data as untrusted. Validate required fields and bound inputs before using them.
- Do not use `eval()`, `exec()`, or shell execution on request-controlled data.
- Keep Google ID-token verification in `validate_google_token()` using `google.oauth2.id_token.verify_oauth2_token()` and the configured client ID. Never decode a JWT and trust it without verification.
- Keep `@require_auth` on `/api/v2/stream` and `/api/v2/auth/me`. New endpoints that spend server resources or access user data require equivalent authentication and authorization.
- Preserve transactional Firestore writes. When changing quota logic, make the limit check and increment safe under concurrency rather than relying on a read followed by a separate write.
- Use HTTPS for external service calls. Sanitize logs and provider exceptions before recording or returning them.
- CORS is currently permissive at the Flask layer. Do not broaden exposure elsewhere; if the CORS policy changes, use an explicit allowlist for the extension's trusted origins.

## Style and maintenance

- Follow PEP 8 and the repository's 120-character line limit. Use snake_case in Python and retain camelCase only at the external JSON boundary.
- Prefer small functions and targeted edits, especially in `app/api.py`. Avoid reformatting unrelated code.
- Add an explicit version constraint for any new production dependency, explain why it is needed, and check it for known vulnerabilities.
- Update `example.env` when adding configuration, and update `README.md` or this file when setup, routes, validation, or deployment behavior changes.
- Do not edit generated caches, local logs, `.env`, or IDE files as part of a change.

## Code review priorities

When reviewing changes, prioritize secret leakage, authentication or quota bypasses, unsafe handling of request data, provider-error leakage, and broken SSE or API compatibility. Give concrete failure scenarios and a safe remediation path; leave purely stylistic enforcement to flake8.
