"""Local, read-only web viewer for validated Stemma catalogs."""

from .app import WebApplication, create_app
from .filters import QueryValidationError, parse_catalog_query
from .server import WebServerConfigurationError, create_server_config, run_server
from .view_models import (
    CatalogPage,
    CatalogQuery,
    CatalogRow,
    CatalogSummary,
    DeviceOption,
    DriftView,
    build_catalog_page,
)

__all__ = [
    "CatalogPage",
    "CatalogQuery",
    "CatalogRow",
    "CatalogSummary",
    "DeviceOption",
    "DriftView",
    "QueryValidationError",
    "WebApplication",
    "WebServerConfigurationError",
    "build_catalog_page",
    "create_app",
    "create_server_config",
    "parse_catalog_query",
    "run_server",
]
