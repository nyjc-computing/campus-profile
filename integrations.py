"""Integration catalog and per-provider connection status.

The catalog below is a placeholder until the Campus backend tracks
available integrations in a registry; it mirrors the OAuth proxies
registered by campus.auth.oauth_proxy (discord, github, google).
"""

from campus_python import errors

# Connection statuses shown on the integrations page.
STATUS_CONNECTED = "connected"
STATUS_EXPIRED = "expired"
STATUS_NOT_CONNECTED = "not_connected"
STATUS_UNKNOWN = "unknown"

# label and Bootstrap badge classes per status.
_STATUS_LABELS = {
    STATUS_CONNECTED: ("Connected", "bg-success"),
    STATUS_EXPIRED: ("Expired", "bg-warning text-dark"),
    STATUS_NOT_CONNECTED: ("Not connected", "bg-secondary"),
    STATUS_UNKNOWN: ("Unknown", "bg-danger"),
}

# Placeholder registry: replace with a backend-provided registry
# when the Campus API exposes one.
PROVIDERS = {
    "discord": {"title": "Discord", "icon": "bi-discord"},
    "github": {"title": "GitHub", "icon": "bi-github"},
    "google": {"title": "Google", "icon": "bi-google"},
}


def _mark(view: dict, status: str) -> dict:
    """Stamp a status (label and badge included) onto a view dict."""
    view["status"] = status
    view["label"], view["badge"] = _STATUS_LABELS[status]
    return view


def get_integration_status(client, provider_id: str, user_id: str) -> dict:
    """Build the display state for one provider connection.

    The view carries only the provider identity and its status -- token
    material and connection metadata (scopes, timestamps) are
    server-managed and must never reach the template.
    """
    meta = PROVIDERS[provider_id]
    view = {
        "id": provider_id,
        "title": meta["title"],
        "icon": meta["icon"],
        "status": STATUS_UNKNOWN,
        "label": None,
        "badge": None,
    }

    try:
        creds = client.auth.credentials[provider_id][user_id].get()
    except errors.NotFoundError:
        return _mark(view, STATUS_NOT_CONNECTED)
    except (errors.APIError, TypeError, KeyError):
        # TypeError/KeyError: campus-suite builds older than ff98c44 fail
        # to rehydrate the embedded token (Model.from_resource). Show the
        # provider as unknown rather than crashing the page.
        return _mark(view, STATUS_UNKNOWN)

    token = getattr(creds, "token", None)
    if token is None:
        return _mark(view, STATUS_UNKNOWN)
    if token.is_expired():
        return _mark(view, STATUS_EXPIRED)
    return _mark(view, STATUS_CONNECTED)
