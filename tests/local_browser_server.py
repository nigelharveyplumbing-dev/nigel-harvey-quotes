"""Run the real app with disposable storage and no outbound connections.

The production checkout is never imported. A copied config is checked before
import because app.py initializes SQLite as it loads.
"""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import smtplib
import socket
import sys
import tempfile
from contextlib import contextmanager

import requests


ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def block_external_connections():
    """Allow a loopback web server while denying all other DNS, HTTP and SMTP."""
    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_http = requests.sessions.Session.request
    original_smtp = smtplib.SMTP
    original_smtp_ssl = smtplib.SMTP_SSL

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in LOOPBACK:
            raise RuntimeError("External DNS blocked in local integration test")
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in LOOPBACK:
            raise RuntimeError("External socket blocked in local integration test")
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if not isinstance(address, tuple) or address[0] not in LOOPBACK:
            raise RuntimeError("External socket blocked in local integration test")
        return original_connect_ex(sock, address)

    def blocked_http(*_args, **_kwargs):
        raise RuntimeError("External HTTP blocked in local integration test")

    def blocked_smtp(*_args, **_kwargs):
        raise RuntimeError("SMTP blocked in local integration test")

    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    requests.sessions.Session.request = blocked_http
    smtplib.SMTP = blocked_smtp
    smtplib.SMTP_SSL = blocked_smtp

    def restore():
        socket.getaddrinfo = original_getaddrinfo
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        requests.sessions.Session.request = original_http
        smtplib.SMTP = original_smtp
        smtplib.SMTP_SSL = original_smtp_ssl

    return restore


@contextmanager
def disposable_app(username: str, password: str,
                   public_base_url: str = "", environment: str = "",
                   bank_settings: dict | None = None):
    if not username or not password:
        raise ValueError("Test-only Basic Auth credentials are required")
    with tempfile.TemporaryDirectory(prefix="stage6-local-") as temporary:
        root = Path(temporary).resolve()
        for name in ("business", "templates", "static"):
            shutil.copytree(ROOT / name, root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        config = root / "business" / "config.py"
        settings = config.read_text()
        for source, destination in (
            ('Path("/var/data/quotes.db")', root / "quotes.db"),
            ('Path("/var/data/backups")', root / "backups"),
            ('Path("/var/data/invoice_photos")', root / "photos"),
        ):
            if settings.count(source) != 1:
                raise RuntimeError("Storage isolation check failed before app import")
            settings = settings.replace(source, f"Path({str(destination)!r})")
        if 'Path("/var/data/' in settings:
            raise RuntimeError("Default storage path survived isolation")
        config.write_text(settings)
        shutil.copy2(ROOT / "app.py", root / "app_under_test.py")

        # Explicitly neutralize any inherited production integration settings.
        overrides = {
            "APP_USERNAME": username,
            "APP_PASSWORD": password,
            "EMAIL_ENABLED": "0",
            "EMAIL_USER": "",
            "EMAIL_PASS": "",
            "EMAIL_HOST": "localhost",
            "AUTO_OVERDUE_REMINDERS": "0",
            "GOOGLE_PLACES_API_KEY": "",
            "GOOGLE_PLACE_ID": "",
            "OPENAI_API_KEY": "",
            "PUBLIC_BASE_URL": public_base_url,
            "APP_ENVIRONMENT": environment,
            "BANK_NAME": "Test Bank",
            "BANK_ACCOUNT_NAME": "Synthetic Test Account",
            "BANK_SORT_CODE": "00-00-00",
            "BANK_ACCOUNT_NUMBER": "00000000",
            "SHOW_BANK_DETAILS_ON_QUOTES": "0",
        }
        if bank_settings is not None:
            for key in ("BANK_NAME", "BANK_ACCOUNT_NAME", "BANK_SORT_CODE",
                        "BANK_ACCOUNT_NUMBER"):
                overrides[key] = bank_settings.get(key, "")
            overrides["SHOW_BANK_DETAILS_ON_QUOTES"] = bank_settings.get(
                "SHOW_BANK_DETAILS_ON_QUOTES", "1")
        previous = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        sys.path.insert(0, str(root))
        previous_business = {
            key: sys.modules.pop(key) for key in list(sys.modules)
            if key == "business" or key.startswith("business.")
        }
        restore_network = None
        try:
            restore_network = block_external_connections()
            spec = importlib.util.spec_from_file_location("stage6_app_under_test", root / "app_under_test.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for path in (module.DB_PATH, module.DB_BACKUP_DIR,
                         sys.modules["business.config"].INVOICE_PHOTO_DIR):
                if not path.resolve().is_relative_to(root):
                    raise RuntimeError("Imported app escaped temporary storage")
            module.init_db()
            routes = [(method, route.path) for route in module.app.routes
                      if route.path not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
                      for method in getattr(route, "methods", [])]
            expected = [tuple(row) for row in json.loads((ROOT / "tests/route_inventory.json").read_text())]
            if len(routes) != len(set(routes)) or set(routes) != set(expected) or len(routes) != 66:
                raise RuntimeError("Route inventory changed")
            yield module, root
        finally:
            if restore_network is not None:
                restore_network()
            for key in list(sys.modules):
                if key == "business" or key.startswith("business."):
                    del sys.modules[key]
            sys.modules.update(previous_business)
            sys.path.remove(str(root))
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ["STAGE6_TEST_PORT"])
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid local test port")
    with disposable_app(os.environ["STAGE6_TEST_USERNAME"],
                        os.environ["STAGE6_TEST_PASSWORD"]) as (app_module, _):
        app_module.upsert_material_price_cache(
            "https://example.test/synthetic-valve", "Synthetic valve",
            "Test supplier", price=5, status="cached",
        )
        uvicorn.run(app_module.app, host="127.0.0.1", port=port,
                    log_level="warning", access_log=False)
