"""Portale dell'analista."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from console import deps
from console.routes import adm, admin, auth, content, exports, fase4, pages, probes, profile, sites
from core.bootstrap import inizializza_portale

BASE = Path(__file__).resolve().parent
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    inizializza_portale()
    yield


app = FastAPI(
    title="CTI · Softstrategy",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
for module in (auth, pages, sites, profile, probes, content, fase4, adm, admin, exports):
    app.include_router(module.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not request.url.path.startswith("/static"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(deps.LoginRequired)
async def login_required(request: Request, exc: deps.LoginRequired) -> Response:
    if request.headers.get("HX-Request"):
        return Response(status_code=401, headers={"HX-Redirect": "/accesso"})
    return RedirectResponse("/accesso", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: HTTPException) -> Response:
    if request.headers.get("HX-Request") or request.url.path == "/salute":
        return Response(str(exc.detail), status_code=exc.status_code, media_type="text/plain; charset=utf-8")
    titles = {403: "Operazione non consentita", 404: "Pagina non trovata", 413: "File troppo grande"}
    return deps.render(
        request,
        "errore.html",
        {
            "titolo": titles.get(exc.status_code, "Qualcosa non ha funzionato"),
            "dettaglio": str(exc.detail),
            "codice": exc.status_code,
        },
        status_code=exc.status_code,
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    return RedirectResponse("/static/favicon.svg", status_code=301)


@app.get("/sign-in", include_in_schema=False)
def sign_in_compatibility() -> RedirectResponse:
    return RedirectResponse("/accesso", status_code=307)


@app.get("/salute")
def health() -> JSONResponse:
    return JSONResponse({"stato": "ok"})
