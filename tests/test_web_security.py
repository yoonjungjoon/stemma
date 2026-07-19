from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from conftest import asgi_request, web_catalog

from stemma import (
    Catalog,
    CatalogEntry,
    Drift,
    DriftKind,
    EntryState,
    FolderMode,
    Location,
)
from stemma.web import create_app

_SECRET = "WEB-API-KEY-SENTINEL"
_CSP = (
    "default-src 'self'; script-src 'none'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)


def _injection_catalog() -> Catalog:
    payload = '<script>alert("xss")</script>'
    desired = Location("DEVICE-X", f"/srv/{payload}", FolderMode.SEND_RECEIVE)
    entry = CatalogEntry(
        folder_id="folder-x",
        folder_label=payload,
        device_id="DEVICE-X",
        device_name=f'node-{payload}-"quoted"',
        desired=desired,
        actual=None,
        state=EntryState.DRIFTED,
        drifts=(Drift(DriftKind.MISSING, payload, "folder-x", None),),
    )
    return Catalog("0.0.1", (entry,))


def test_template_autoescapes_catalog_and_query_payloads() -> None:
    payload = '<script>alert("xss")</script>'
    response = asgi_request(
        create_app(_injection_catalog()),
        "GET",
        "/catalog?q=%3Cscript%3E",
    )

    assert response.status_code == 200
    assert payload not in response.text
    assert "&lt;script&gt;" in response.text
    assert "&#34;" in response.text or "&quot;" in response.text
    assert "<script" not in response.text.lower()


def test_security_headers_and_application_request_id_are_enforced() -> None:
    client_request_id = f"client-{_SECRET}"
    response = asgi_request(
        create_app(web_catalog()),
        "GET",
        "/catalog",
        headers={
            "X-Request-ID": client_request_id,
            "Authorization": f"Bearer {_SECRET}",
            "Cookie": f"session={_SECRET}",
        },
    )

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == _CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    request_id = response.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert request_id != client_request_id
    assert _SECRET not in response.text
    assert all(_SECRET not in value for value in response.headers.values())


def test_400_404_405_and_500_do_not_expose_raw_inputs_or_tracebacks() -> None:
    invalid_mode = cast(FolderMode, object())
    desired = Location("DEVICE-A", "/sensitive/catalog/path", invalid_mode)
    broken_catalog = Catalog(
        "0.0.1",
        (
            CatalogEntry(
                "docs",
                None,
                "DEVICE-A",
                "server",
                desired,
                None,
                EntryState.IN_SYNC,
                (),
            ),
        ),
    )
    responses = [
        asgi_request(create_app(web_catalog()), "GET", f"/catalog?state={_SECRET}"),
        asgi_request(create_app(web_catalog()), "GET", f"/unknown-{_SECRET}"),
        asgi_request(create_app(web_catalog()), "DELETE", "/catalog"),
        asgi_request(create_app(broken_catalog), "GET", "/catalog"),
    ]

    assert [response.status_code for response in responses] == [400, 404, 405, 500]
    for response in responses:
        assert _SECRET not in response.text
        assert "Traceback" not in response.text
        assert "AttributeError" not in response.text
        assert response.headers["content-security-policy"] == _CSP
        assert response.headers["cache-control"] == "no-store"
    assert "/sensitive/catalog/path" not in responses[-1].text
    assert responses[-1].headers["x-request-id"] in responses[-1].text


def test_templates_use_no_raw_or_safe_rendering() -> None:
    template_directory = Path(__file__).parents[1] / "src" / "stemma" / "web" / "templates"
    templates = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(template_directory.glob("*.html"))
    )
    assert "| safe" not in templates
    assert "|safe" not in templates


def test_catalog_page_has_only_read_only_filter_form() -> None:
    response = asgi_request(create_app(web_catalog()), "GET", "/catalog")
    lowered = response.text.lower()
    assert '<form class="filters" method="get"' in lowered
    for action in ("delete", "restart", "scan", "retry", "edit"):
        assert f">{action}<" not in lowered
