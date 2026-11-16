"""Resolve API credentials via the Muse dynamic_credentials surrogate mechanism.

Keys live in the Secure Vault; this module only ever carries ``hsurr:``
surrogates. The egress layer swaps each surrogate for the real credential on
an approved request to the registered host. No key is ever printed, logged
or stored here.

Falls back to environment variables when the surrogate is unavailable
(e.g. local dev without the authd socket). The GitHub copy of this repo
therefore still works standalone with a plain .env file.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
try:
    from dynamic_credentials import dynamic_credential_entry
except Exception:  # pragma: no cover - no authd socket on plain machines
    dynamic_credential_entry = None


def _surrogate(connection: str) -> str | None:
    if dynamic_credential_entry is None:
        return None
    try:
        entry = dynamic_credential_entry(connection)
        surrogate = str(entry.get("surrogate", "")).strip()
        return surrogate if surrogate.startswith("hsurr:") else None
    except Exception as exc:
        logger.debug("Surrogate unavailable for %s: %s", connection, exc)
        return None


def _bearer_headers(connection: str, env_name: str) -> dict:
    surrogate = _surrogate(connection)
    if surrogate:
        return {"Authorization": f"Bearer {surrogate}"}
    key = os.getenv(env_name, "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _custom_header(connection: str, env_name: str, header_name: str) -> dict:
    surrogate = _surrogate(connection)
    if surrogate:
        return {header_name: surrogate}
    key = os.getenv(env_name, "").strip()
    return {header_name: key} if key else {}


def synmerco_auth_headers() -> dict:
    """Bearer header for custom.synmerco (or SYNMERCO_API_KEY fallback)."""
    return _bearer_headers("custom.synmerco", "SYNMERCO_API_KEY")


def moltjobs_auth_headers() -> dict:
    """Bearer header for custom.moltjobs (or MOLTJOBS_API_KEY fallback)."""
    return _bearer_headers("custom.moltjobs", "MOLTJOBS_API_KEY")


def hyrve_auth_headers() -> dict:
    """X-API-Key header for custom.hyrve (or HYRVE_API_KEY fallback)."""
    return _custom_header("custom.hyrve", "HYRVE_API_KEY", "X-API-Key")


def makefun_auth_headers() -> dict:
    """x-api-key header for custom.makefun (or MAKEFUN_API_KEY fallback)."""
    return _custom_header("custom.makefun", "MAKEFUN_API_KEY", "x-api-key")
