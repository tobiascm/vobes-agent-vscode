"""
Zentralisierte Authentication-Utilities für LiteLLM API Tests.

Verantwortung: OAuth Token-Verwaltung und API-Credentials

Benötigte Windows System-Umgebungsvariablen:
- LLMAAS_CLIENT_ID: OAuth Client ID für VW IDP
- LLMAAS_CLIENT_SECRET: OAuth Client Secret
- LLMAAS_API_CLIENT_ID: LiteLLM API Client ID (sk-...)
- LLMAAS_IDP_URL (optional): Token-Endpoint URL
- LLMAAS_BASE_URL (optional): LiteLLM Gateway Base URL
"""

import os
import httpx
from typing import Dict


# Credentials aus Umgebungsvariablen lesen
CLIENT_ID = os.environ.get("LLMAAS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("LLMAAS_CLIENT_SECRET")
LLM_API_CLIENT_ID = os.environ.get("LLMAAS_API_CLIENT_ID")

# URLs mit Defaults (optional als Umgebungsvariable)
IDP_URL = os.environ.get(
    "LLMAAS_IDP_URL",
    "https://idp.cloud.vwgroup.com/auth/realms/kums-mfa/protocol/openid-connect/token"
)
BASE_URL = os.environ.get("LLMAAS_BASE_URL", "https://llmapi.ai.vwgroup.com")


def _validate_credentials():
    """Validiert, dass alle erforderlichen Umgebungsvariablen gesetzt sind."""
    missing = []
    if not CLIENT_ID:
        missing.append("LLMAAS_CLIENT_ID")
    if not CLIENT_SECRET:
        missing.append("LLMAAS_CLIENT_SECRET")
    if not LLM_API_CLIENT_ID:
        missing.append("LLMAAS_API_CLIENT_ID")
    if missing:
        raise EnvironmentError(
            f"Fehlende Umgebungsvariablen: {', '.join(missing)}\n"
            "Bitte als Windows System-Umgebungsvariablen setzen:\n"
            "  1. Windows-Taste + R -> sysdm.cpl -> Enter\n"
            "  2. Tab 'Erweitert' -> 'Umgebungsvariablen'\n"
            "  3. Unter 'Benutzervariablen' -> 'Neu' klicken"
        )


_validate_credentials()


def get_token() -> str:
    """
    Holt OAuth Access Token vom VW Group IDP.

    Returns:
        str: JWT Access Token für API-Authentifizierung

    Raises:
        httpx.HTTPError: Bei Authentifizierungsfehlern
    """
    response = httpx.post(
        IDP_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=30.0
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_api_client_id() -> str:
    """
    Gibt die LiteLLM API Client ID zurück.

    Returns:
        str: API Client ID für X-LLM-API-CLIENT-ID Header
    """
    return LLM_API_CLIENT_ID


def get_auth_headers(token: str) -> Dict[str, str]:
    """
    Erstellt Standard-Headers für API-Requests (für httpx).

    Args:
        token: OAuth Access Token

    Returns:
        Dict mit Authorization und x-llm-api-client-id Headers
        Hinweis: x-llm-api-client-id benötigt auch "Bearer" Prefix
    """
    return {
        "Authorization": f"Bearer {token}",
        "x-llm-api-client-id": f"Bearer {LLM_API_CLIENT_ID}",
    }


def get_base_url() -> str:
    """
    Gibt die Base URL für das LiteLLM Gateway zurück.

    Returns:
        str: Base URL
    """
    return BASE_URL
