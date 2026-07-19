"""Starlette application factory for the local read-only catalog viewer."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from stemma.models import Catalog

from .filters import QueryValidationError, parse_catalog_query
from .middleware import RequestSecurityMiddleware
from .view_models import build_catalog_page

type WebApplication = Starlette

_PACKAGE_DIRECTORY = Path(__file__).parent
_TEMPLATE_DIRECTORY = _PACKAGE_DIRECTORY / "templates"
_STATIC_DIRECTORY = _PACKAGE_DIRECTORY / "static"


def create_app(catalog: Catalog) -> WebApplication:
    """Create an immutable-catalog application with debug explicitly disabled."""

    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=True),
        undefined=StrictUndefined,
    )
    catalog_template = environment.get_template("catalog.html")
    error_template = environment.get_template("error.html")
    stylesheet = (_STATIC_DIRECTORY / "catalog.css").read_text(encoding="utf-8")

    async def redirect_to_catalog(request: Request) -> Response:
        return RedirectResponse("/catalog", status_code=303)

    async def catalog_page(request: Request) -> Response:
        try:
            query = parse_catalog_query(request.query_params.multi_items(), catalog)
        except QueryValidationError as error:
            return HTMLResponse(
                error_template.render(
                    status=400,
                    title="Invalid catalog filter",
                    message=error.detail,
                    field=error.field,
                    allowed=error.allowed,
                    request_id=None,
                ),
                status_code=400,
            )
        page = build_catalog_page(catalog, query)
        body = catalog_template.render(page=page)
        if request.method == "HEAD":
            return HTMLResponse(
                "",
                status_code=200,
                headers={"Content-Length": str(len(body.encode("utf-8")))},
            )
        return HTMLResponse(body, status_code=200)

    async def static_asset(request: Request) -> Response:
        path = cast(object, request.path_params.get("path"))
        if path != "catalog.css":
            raise HTTPException(status_code=404)
        return Response(stylesheet, media_type="text/css; charset=utf-8")

    async def http_error(request: Request, error: Exception) -> Response:
        if not isinstance(error, HTTPException):  # pragma: no cover - registration invariant
            raise error
        status = error.status_code
        title = "Page not found" if status == 404 else "Method not allowed"
        message = (
            "The requested page does not exist."
            if status == 404
            else "This read-only viewer does not support that method."
        )
        return HTMLResponse(
            error_template.render(
                status=status,
                title=title,
                message=message,
                field=None,
                allowed=(),
                request_id=None,
            ),
            status_code=status,
            headers=error.headers,
        )

    routes = [
        Route("/", redirect_to_catalog, methods=["GET"], name="root"),
        Route("/catalog", catalog_page, methods=["GET", "HEAD"], name="catalog"),
        Route(
            "/static/{path:path}",
            static_asset,
            methods=["GET", "HEAD"],
            name="static",
        ),
    ]
    return Starlette(
        debug=False,
        routes=routes,
        middleware=[Middleware(RequestSecurityMiddleware)],
        exception_handlers={404: http_error, 405: http_error},
    )
