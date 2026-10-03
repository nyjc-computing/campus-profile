"""Integration cards from the campus.auth registry, plus per-user
connection status and disconnect.

Cards are enumerated from the campus.auth integration registry
(GET /integrations/v1/, public, campus#751) and status from the
metadata-only connections inventory (GET /auth/v1/connections/,
campus#750); see campus#733 §2.7 and campus-profile#25. The registry
is the catalog -- this module keeps no list of integrations itself.
"""

from urllib.parse import urlencode

from campus_python import errors

# Connection statuses shown on the integrations page. There is no
# "expired": expires_at is the access token's last-known expiry, not
# connection health -- campus refreshes silently server-side, so a
# healthy connection usually shows a stale timestamp (#25 correction).
STATUS_CONNECTED = "connected"
STATUS_NOT_CONNECTED = "not_connected"
STATUS_UNAVAILABLE = "unavailable"

# label and Bootstrap badge classes per status.
_STATUS_LABELS = {
    STATUS_CONNECTED: ("Connected", "bg-success"),
    STATUS_NOT_CONNECTED: ("Not connected", "bg-secondary"),
    STATUS_UNAVAILABLE: ("Status unavailable", "bg-warning text-dark"),
}

# Registry endpoint: public, sits beside /auth/v1 at the auth service
# root, so it is not reached via auth.make_path().
REGISTRY_PATH = "/integrations/v1/"

# Bootstrap icon per card. The registry carries no icon field; this is
# a display hint only -- never a catalog of what exists (that is the
# registry's job), and unknown slugs get a generic plug.
_ICONS = {
    "classroom": "bi-journal-bookmark",
    "calendar": "bi-calendar-event",
}
_DEFAULT_ICON = "bi-plug"


def fetch_registry(client) -> list[dict]:
    """Fetch the integration catalog from campus.auth (public).

    Campus JSON responses are always objects: the entries ride an
    {"integrations": [...]} envelope (campus#751), never a bare list.
    """
    response = client.auth.client.get(REGISTRY_PATH)
    response.raise_for_status()
    return response.json()["integrations"]


def fetch_connections(client, user_id: str) -> list[dict]:
    """Fetch a user's upstream connection inventory (metadata-only).

    Delegated read: the page's server-mode basic auth plus user_id
    (required -- campus answers 400 without it, meaning the parameter
    was dropped, not that the user has no connections). No token
    values are ever present in the payload (invariant C2), and the
    user's campus login tokens are not connections and are not listed.
    """
    response = client.auth.client.get(
        client.auth.make_path("connections/"),
        query={"user_id": user_id},
    )
    response.raise_for_status()
    return response.json()["connections"]


def registry_entry(registry: list[dict], slug: str) -> dict:
    """Return the registry entry for a slug; LookupError if unknown."""
    for entry in registry:
        if entry["slug"] == slug:
            return entry
    raise LookupError(slug)


def find_connection(connections: list[dict], entry: dict) -> dict | None:
    """Return the connection matching a registry entry, if granted."""
    for connection in connections:
        if (connection.get("integration") == entry["slug"]
                or connection.get("provider") == entry["provider"]):
            return connection
    return None


def _mark(card: dict, status: str) -> dict:
    """Stamp a status (label and badge included) onto a card."""
    card["status"] = status
    card["label"], card["badge"] = _STATUS_LABELS[status]
    return card


def build_card(entry: dict, connection: dict | None) -> dict:
    """Build the display state for one registry entry.

    A present connection means Connected; absence means Not connected
    (#25 correction -- see the status note above). The card carries
    only registry fields and the status: connection metadata (scopes,
    timestamps) is server-managed and must never reach the template.
    """
    status = STATUS_CONNECTED if connection else STATUS_NOT_CONNECTED
    card = {
        "id": entry["slug"],
        "title": entry["title"],
        "description": entry.get("description"),
        "icon": _ICONS.get(entry["slug"], _DEFAULT_ICON),
        "connectable": bool(entry.get("connectable")),
        "status": None,
        "label": None,
        "badge": None,
    }
    return _mark(card, status)


def mark_unavailable(card: dict) -> dict:
    """Stamp a failed status read onto a card (campus unreachable)."""
    return _mark(card, STATUS_UNAVAILABLE)


def connect_authorize_url(client, slug: str, target: str) -> str:
    """Build the campus.auth URL that starts a connect flow (#733).

    The authorize path comes from the registry entry, not hardcode.
    target is this app's connect callback URL; campus.auth checks its
    origin against the integration's vault CONNECT_TARGETS allowlist
    before starting the flow, so a misconfigured deployment fails
    there, not here.
    """
    entry = registry_entry(fetch_registry(client), slug)
    endpoint = client.auth.base_url + entry["authorize_path"]
    return f"{endpoint}?{urlencode({'target': target})}"


def disconnect(client, entry: dict, user_id: str) -> bool:
    """Disconnect a user's integration grant.

    campus.auth deletes the stored credential rows and their token
    records and emits the campus.integrations.disconnect audit
    event campus-side; profile adds nothing to the audit trail and
    never touches token material. 404 (nothing was connected) is
    idempotent success, not an error.

    Returns True if a connection was deleted, False if there was
    none; raises only on real failures.
    """
    path = f"connections/{entry['base_provider']}/{entry['slug']}/"
    # The client's delete() carries no query= parameter, and campus
    # reads user_id from the query string only.
    path = f"{path}?{urlencode({'user_id': user_id})}"
    response = client.auth.client.delete(client.auth.make_path(path))
    try:
        response.raise_for_status()
    except errors.NotFoundError:
        return False
    return True
