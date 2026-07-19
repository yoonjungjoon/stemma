from __future__ import annotations

from conftest import asgi_request, web_catalog

from stemma import Catalog
from stemma.web import create_app


def test_root_redirects_to_catalog_with_303() -> None:
    response = asgi_request(create_app(web_catalog()), "GET", "/")
    assert response.status_code == 303
    assert response.headers["location"] == "/catalog"


def test_catalog_renders_summary_mapping_table_and_distinct_drift_labels() -> None:
    response = asgi_request(create_app(web_catalog()), "GET", "/catalog")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "Local Docs Sync Catalog" in response.text
    assert "Read-only view of snapshot files prepared locally" in response.text
    assert "Company documents" in response.text
    assert "sendreceive" in response.text
    assert "sendonly" in response.text
    assert "Device snapshot missing" in response.text
    assert "Folder missing" in response.text
    assert "Path mismatch" in response.text
    assert "Mode mismatch" in response.text
    assert response.text.index("assets") < response.text.index("company-docs")


def test_head_has_get_headers_and_no_body() -> None:
    app = create_app(web_catalog())
    get_response = asgi_request(app, "GET", "/catalog")
    head_response = asgi_request(app, "HEAD", "/catalog")

    assert head_response.status_code == 200
    assert head_response.content == b""
    assert head_response.headers["content-length"] == get_response.headers["content-length"]
    for header in (
        "content-type",
        "cache-control",
        "content-security-policy",
        "x-content-type-options",
        "referrer-policy",
        "x-frame-options",
    ):
        assert head_response.headers[header] == get_response.headers[header]


def test_unknown_route_and_unsupported_methods_use_html_errors() -> None:
    app = create_app(web_catalog())
    not_found = asgi_request(app, "GET", "/not-found")
    method_not_allowed = asgi_request(app, "POST", "/catalog")

    assert not_found.status_code == 404
    assert "Page not found" in not_found.text
    assert method_not_allowed.status_code == 405
    assert "Method not allowed" in method_not_allowed.text
    assert "read-only viewer" in method_not_allowed.text
    assert "application/json" not in not_found.headers["content-type"]


def test_static_css_is_local_and_api_route_does_not_exist() -> None:
    app = create_app(web_catalog())
    page = asgi_request(app, "GET", "/catalog")
    stylesheet = asgi_request(app, "GET", "/static/catalog.css")
    api = asgi_request(app, "GET", "/api/catalog")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert "/static/catalog.css" in page.text
    assert "https://" not in page.text
    assert "http://" not in page.text
    assert "<script" not in page.text.lower()
    assert api.status_code == 404


def test_empty_catalog_and_valid_no_results_have_distinct_messages() -> None:
    empty = Catalog(schema_version="0.0.1", entries=())
    empty_response = asgi_request(create_app(empty), "GET", "/catalog")
    no_results = asgi_request(
        create_app(web_catalog()),
        "GET",
        "/catalog?state=in_sync&drift_kind=missing",
    )

    assert empty_response.status_code == 200
    assert "Catalog entry가 없습니다." in empty_response.text
    assert no_results.status_code == 200
    assert "조건에 맞는 entry가 없습니다." in no_results.text
    assert "Filter 초기화" in no_results.text


def test_invalid_queries_return_actionable_400_without_raw_value() -> None:
    app = create_app(web_catalog())
    secret_value = "QUERY-SECRET-SENTINEL"

    responses = [
        asgi_request(app, "GET", f"/catalog?state={secret_value}"),
        asgi_request(app, "GET", "/catalog?q=one&q=two"),
        asgi_request(app, "GET", f"/catalog?unknown={secret_value}"),
    ]

    assert all(response.status_code == 400 for response in responses)
    assert all(secret_value not in response.text for response in responses)
    assert "Allowed values" in responses[0].text
    assert "state" in responses[0].text
    assert "at most once" in responses[1].text
    assert "unknown" in responses[2].text
