import os
import time
from urllib.parse import urlencode

import gradio as gr
from authlib.integrations.starlette_client import OAuth
from decouple import config
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from theflow.settings import settings as flowsettings

from ktem.external_auth import (
    ExternalAuthError,
    clear_session_user,
    identity_from_oidc_claims,
    sync_external_user,
)
from ktem.main import App

KH_APP_DATA_DIR = getattr(flowsettings, "KH_APP_DATA_DIR", ".")
GRADIO_TEMP_DIR = os.getenv("GRADIO_TEMP_DIR", None)
SECRET_KEY = str(config("SECRET_KEY", default="") or "").strip()
AUTHENTIK_SERVER_URL = str(config("AUTHENTIK_SERVER_URL", default="") or "").strip()
AUTHENTIK_SLUG = str(config("AUTHENTIK_SLUG", default="") or "").strip()
AUTHENTIK_CLIENT_ID = str(config("AUTHENTIK_CLIENT_ID", default="") or "").strip()
AUTHENTIK_CLIENT_SECRET = str(config("AUTHENTIK_CLIENT_SECRET", default="") or "").strip()
OIDC_SCOPES = str(config("OIDC_SCOPES", default="openid email profile") or "openid email profile")

if GRADIO_TEMP_DIR is None:
    GRADIO_TEMP_DIR = os.path.join(KH_APP_DATA_DIR, "gradio_tmp")
    os.environ["GRADIO_TEMP_DIR"] = GRADIO_TEMP_DIR

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY muss f?r AUTHENTICATION_METHOD=AUTHENTIK gesetzt sein.")
if not AUTHENTIK_SERVER_URL:
    raise RuntimeError("AUTHENTIK_SERVER_URL muss f?r AUTHENTICATION_METHOD=AUTHENTIK gesetzt sein.")
if not AUTHENTIK_CLIENT_ID or not AUTHENTIK_CLIENT_SECRET:
    raise RuntimeError(
        "AUTHENTIK_CLIENT_ID und AUTHENTIK_CLIENT_SECRET m?ssen gesetzt sein."
    )


def _metadata_url() -> str:
    base_url = AUTHENTIK_SERVER_URL.rstrip("/")
    if base_url.endswith("/.well-known/openid-configuration"):
        return base_url
    if AUTHENTIK_SLUG:
        return f"{base_url}/application/o/{AUTHENTIK_SLUG}/.well-known/openid-configuration"
    return f"{base_url}/.well-known/openid-configuration"


gradio_app = App()
demo = gradio_app.make()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

oauth = OAuth()
oauth.register(
    name="authentik",
    server_metadata_url=_metadata_url(),
    client_id=AUTHENTIK_CLIENT_ID,
    client_secret=AUTHENTIK_CLIENT_SECRET,
    client_kwargs={"scope": OIDC_SCOPES},
)

app = gr.mount_gradio_app(
    app,
    demo,
    path="/app",
    allowed_paths=[
        "libs/ktem/ktem/assets",
        GRADIO_TEMP_DIR,
    ],
)


async def _revalidate_user_groups(request: Request) -> bool:
    """Re-fetch user groups from Authentik and update DB.

    Uses the stored access_token to call the userinfo endpoint,
    then re-syncs group memberships via sync_external_user.
    Returns True on success, False if revalidation was skipped or failed.
    """
    access_token = request.session.get("access_token")
    if not access_token:
        return False
    try:
        token_data = {"access_token": access_token}
        userinfo = await oauth.authentik.userinfo(token=token_data)
        if not userinfo:
            return False
        identity = identity_from_oidc_claims(dict(userinfo))
        print(f"[REVALIDATE] groups={identity.groups}", flush=True)
        sync_external_user(identity)
        request.session["_last_group_sync"] = int(time.time())
        return True
    except Exception:
        return False


@app.middleware("http")
async def revalidate_groups_middleware(request: Request, call_next):
    if "session" not in request.scope:
        return await call_next(request)
    if request.url.path.startswith("/app") and request.session.get("user_id"):
        last_sync = request.session.get("_last_group_sync", 0)
        if int(time.time()) - last_sync > 300:  # every 5 minutes
            await _revalidate_user_groups(request)
    response = await call_next(request)
    return response


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(gradio_app._favicon)


KH_PUBLIC_URL = str(config("KH_PUBLIC_URL", default="") or "").strip()

@app.get("/login", include_in_schema=False)
async def login(request: Request):
    # Clear any stale user session before starting the OIDC flow.
    # Without this, closing the browser and re-opening would auto-login
    # the previous user via the persisted session cookie, and the
    # subsequent OIDC callback could carry over stale identity data.
    clear_session_user(request)
    if KH_PUBLIC_URL:
        redirect_uri = KH_PUBLIC_URL.rstrip("/") + "/auth/callback"
    else:
        redirect_uri = str(request.url_for("auth_callback"))
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", include_in_schema=False, name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.authentik.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = await oauth.authentik.userinfo(token=token)
        identity = identity_from_oidc_claims(dict(userinfo))
        print("[AUTH DEBUG] userinfo keys: " + str(list(userinfo.keys()) if userinfo else "None"), flush=True)
        print(f"[AUTH DEBUG] identity.groups: {identity.groups}", flush=True)
        result = sync_external_user(identity)
        user_id = result.user_id
        decision = result.decision
        print(f"[AUTH DEBUG] decision: can_access={decision.can_access}, is_admin={decision.is_admin}, reason={decision.reason}", flush=True)
        if not user_id or not decision.can_access:
            clear_session_user(request)
            params = urlencode({"message": decision.reason or "Zugriff verweigert"})
            return RedirectResponse(url=f"/auth/error?{params}", status_code=302)

        request.session["user_id"] = user_id
        if token.get("id_token"):
            request.session["id_token"] = token["id_token"]
        if token.get("access_token"):
            request.session["access_token"] = token["access_token"]

        # HTML-Redirect statt 302: stellt sicher, dass der Browser den
        # Session-Cookie speichert, BEVOR er /app anfordert.
        # Ohne das kann ein Race entstehen, bei dem /app noch den
        # alten Cookie (admin) mitsendet und der falsche User
        # angezeigt wird.
        return HTMLResponse(
            "<html><head>"
            "<meta http-equiv=\"refresh\" content=\"0;url=/app\">"
            "</head><body>"
            "<p>Anmeldung erfolgreich, du wirst weitergeleitet…</p>"
            "<script>window.location.replace('/app');</script>"
            "</body></html>"
        )
    except ExternalAuthError as exc:
        clear_session_user(request)
        params = urlencode({"message": str(exc)})
        return RedirectResponse(url=f"/auth/error?{params}", status_code=302)
    except Exception as exc:
        error_msg = str(exc)
        if "mismatching_state" in error_msg.lower() or "state not equal" in error_msg.lower():
            return RedirectResponse(url="/login", status_code=302)
        clear_session_user(request)
        params = urlencode({"message": f"OIDC-Callback fehlgeschlagen: {exc}"})
        return RedirectResponse(url=f"/auth/error?{params}", status_code=302)


@app.get("/auth/error", include_in_schema=False)
async def auth_error(message: str = "Unbekannter Authentifizierungsfehler"):
    return HTMLResponse(
        f"""
        <html>
          <head><title>Kaidoku Anmeldung</title></head>
          <body>
            <h2>Anmeldung fehlgeschlagen</h2>
            <p>{message}</p>
            <p><a href="/app">Zur?ck zur Anwendung</a></p>
          </body>
        </html>
        """.strip()
    )


@app.get("/logout", include_in_schema=False)
async def logout(request: Request):
    id_token = request.session.get("id_token")
    clear_session_user(request)

    metadata = getattr(oauth.authentik, "server_metadata", {}) or {}
    end_session_endpoint = metadata.get("end_session_endpoint")
    if end_session_endpoint:
        params = {"post_logout_redirect_uri": str(request.base_url).rstrip("/") + "/app"}
        if id_token:
            params["id_token_hint"] = id_token
        return RedirectResponse(
            url=f"{end_session_endpoint}?{urlencode(params)}",
            status_code=302,
        )
    return RedirectResponse(url="/app", status_code=302)
