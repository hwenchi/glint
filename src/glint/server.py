"""The local web server: only the user's own browser, on this machine, gets in."""

import secrets

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, TypeAdapter
from starlette.middleware.trustedhost import TrustedHostMiddleware

from glint.agent import Session
from glint.history import Entry

TOKEN_COOKIE = "glint_token"

ENTRY = TypeAdapter(Entry)


class NewMessage(BaseModel):
    text: str


def create_app(session: Session, token: str, port: int) -> FastAPI:
    # No OpenAPI or docs routes: the docs page loads scripts from a CDN, which
    # the CSP forbids. The schema is still available as app.openapi().
    app = FastAPI(openapi_url=None)
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def valid(given: str) -> bool:
        return secrets.compare_digest(given.encode(), token.encode())

    # Middleware added later runs earlier: host, then token, then origin.

    @app.middleware("http")
    async def require_same_origin(request: Request, call_next):
        """Changes must come from the page itself, not another site."""
        if request.method not in ("GET", "HEAD") and request.headers.get("origin") not in origins:
            return PlainTextResponse("forbidden origin", status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        """The URL printed at startup carries the token; the browser then keeps it as a cookie."""
        query_token = request.query_params.get("token")
        if query_token is not None:
            if not valid(query_token):
                return PlainTextResponse("invalid token", status_code=403)
            # Drop the token from the URL so it isn't left in the address bar or history.
            response = RedirectResponse(str(request.url.remove_query_params("token")), status_code=303)
            response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict")
            return response
        cookie_token = request.cookies.get(TOKEN_COOKIE, "")
        if not valid(cookie_token):
            return PlainTextResponse("missing or invalid token", status_code=403)
        return await call_next(request)

    # Against DNS rebinding: another site's hostname pointed at 127.0.0.1.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.get("/api/history", response_model=list[Entry])
    def get_history():
        return list(session.history)

    @app.post("/api/history")
    def add_message(message: NewMessage):
        """Add the user's message and stream the turn's entries as server-sent events as they arrive."""
        entries = session.respond(message.text)
        events = (b"data: " + ENTRY.dump_json(entry) + b"\n\n" for entry in entries)
        return StreamingResponse(events, media_type="text/event-stream")

    return app
