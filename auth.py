import os
from fastapi import Header, HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
ALLOWED_EMAIL = os.environ.get("ALLOWED_EMAIL")

_request = google_requests.Request()


def require_auth(authorization: str = Header(None)):
    """Exige um ID token do Google valido no header Authorization: Bearer <token>."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Login com Google nao configurado no servidor (GOOGLE_CLIENT_ID ausente).")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Faca login com sua conta Google para editar o portfolio.")

    token = authorization[len("Bearer "):].strip()

    try:
        payload = id_token.verify_oauth2_token(token, _request, GOOGLE_CLIENT_ID)
    except ValueError:
        raise HTTPException(status_code=401, detail="Sessao invalida ou expirada. Faca login novamente.")

    if not payload.get("email_verified"):
        raise HTTPException(status_code=401, detail="E-mail da conta Google nao verificado.")

    if ALLOWED_EMAIL and payload.get("email", "").lower() != ALLOWED_EMAIL.lower():
        raise HTTPException(status_code=403, detail="Esta conta nao tem permissao para editar este portfolio.")

    return payload
