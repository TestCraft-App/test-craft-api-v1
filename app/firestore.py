from datetime import datetime, timezone

from google.cloud import firestore

DAILY_LIMIT = 10

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_or_create_user(user_info):
    """Create or update a user document in Firestore. Returns the user dict."""
    doc_ref = _get_db().collection("users").document(user_info["googleId"])
    doc = doc_ref.get()

    now = datetime.now(timezone.utc)

    if doc.exists:
        doc_ref.update({"lastLoginAt": now})
        return doc.to_dict()
    else:
        user_data = {
            "email": user_info["email"],
            "name": user_info["name"],
            "picture": user_info["picture"],
            "createdAt": now,
            "lastLoginAt": now,
        }
        doc_ref.set(user_data)
        return user_data


def get_daily_usage(google_id):
    """Return today's usage count for a user."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc_ref = _get_db().collection("users").document(google_id).collection("usage").document(today)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("count", 0)
    return 0


def increment_usage(google_id):
    """Atomically increment today's usage count. Returns new count."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc_ref = _get_db().collection("users").document(google_id).collection("usage").document(today)

    @firestore.transactional
    def _increment(transaction):
        doc = doc_ref.get(transaction=transaction)
        current = doc.to_dict().get("count", 0) if doc.exists else 0
        transaction.set(doc_ref, {"count": current + 1})
        return current + 1

    transaction = _get_db().transaction()
    return _increment(transaction)


def is_limit_reached(google_id):
    """Check if the user has reached their daily generation limit."""
    return get_daily_usage(google_id) >= DAILY_LIMIT
