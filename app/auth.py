from functools import wraps

from flask import jsonify, request, g
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Config

config = Config()


def validate_google_token(token):
    """Validate a Google ID token and return the user info."""
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            config.GOOGLE_CLIENT_ID,
        )
        return {
            "googleId": idinfo["sub"],
            "email": idinfo.get("email", ""),
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture", ""),
        }
    except ValueError:
        return None


def require_auth(f):
    """Decorator that validates the Authorization: Bearer token and sets g.user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header."}), 401

        token = auth_header.split(" ", 1)[1]
        user = validate_google_token(token)
        if not user:
            return jsonify({"error": "Invalid or expired token."}), 401

        g.user = user
        return f(*args, **kwargs)

    return decorated
