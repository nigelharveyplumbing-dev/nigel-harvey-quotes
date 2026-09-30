"""Read-only release checks from the existing Render service Shell.

Usage: python scripts/verify_release.py --environment staging
       python scripts/verify_release.py --environment production --read-only

No POST/PUT/DELETE requests or SQLite write connections are used. Output omits
customer details and credentials. A nonzero exit means at least one check failed.
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


SERVICES = {
    "staging": "srv-das0vrflk1mc73dtb2cg",
    "production": "srv-d72j5ocg9agc7399dni0",
}
PRODUCTION_ORIGIN = "https://www.nigelharveyplumbing.co.uk"
REDIRECT_TOWNS = (
    "guildford", "woking", "farnham", "godalming", "camberley",
    "aldershot", "leatherhead", "epsom", "fairlands", "worplesdon",
    "merrow", "burpham", "shalford",
)
SCHEMA = {
    "quotes": {"status", "next_follow_up", "loss_reason", "lead_id", "source_category", "work_type",
               "additional_work_types", "share_token"},
    "invoices": {"share_token"},
    "leads": {"source_category", "work_type", "quick_add_key", "customer_id",
              "additional_work_types"},
    "appointments": {"lead_id", "job_id", "kind", "status", "starts_at", "ends_at",
                     "provisional_follow_up", "notes"},
    "jobs": {"lead_id", "quote_id", "invoice_id", "customer_id", "title", "status", "notes"},
}
TABLES = ("customers", "quotes", "invoices", "leads", "material_price_cache")


def assert_identity(environment, db_path, origin):
    """Fail closed on a wrong host or service before making any HTTP request."""
    expected = SERVICES[environment]
    actual = os.getenv("RENDER_SERVICE_ID", "").strip()
    if actual and actual != expected:
        raise ValueError(f"Wrong Render service: {actual}; expected {expected}")
    if db_path != Path("/var/data/quotes.db") or not os.path.ismount("/var/data"):
        raise ValueError("Run inside the intended Render service with /var/data mounted")
    if environment == "production":
        if os.getenv("APP_ENVIRONMENT", "").lower() == "staging" or origin != PRODUCTION_ORIGIN:
            raise ValueError("Production origin/environment mismatch")
    elif (os.getenv("APP_ENVIRONMENT", "").lower() != "staging"
          or not origin.startswith("https://") or origin == PRODUCTION_ORIGIN
          or not origin.endswith(".onrender.com")):
        raise ValueError("Staging origin/environment mismatch")
    return {"service_id": actual or "not exposed by Render (origin and mounted disk checked)",
            "environment": environment, "origin": origin}


def inspect_database(db_path):
    if not db_path.is_file():
        raise ValueError("SQLite database is missing")
    # URI mode=ro prevents schema creation, migration and test writes.
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        columns = {table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                   for table in SCHEMA}
        missing = {table: sorted(required - columns[table])
                   for table, required in SCHEMA.items() if required - columns[table]}
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in TABLES}
        photos = connection.execute("SELECT COUNT(*) FROM invoice_photos").fetchone()[0]
    finally:
        connection.close()
    return {"exists": True, "path": str(db_path), "size_bytes": db_path.stat().st_size,
            "integrity": integrity, "mounted": os.path.ismount(db_path.parent),
            "counts": counts, "invoice_photos": photos,
            "backup_files": len(list((db_path.parent / "backups").glob("quotes-backup-*.db"))),
            "missing_columns": missing}


def check_http(environment, origin, username, password):
    session = requests.Session()
    session.auth = (username, password)
    session.headers["User-Agent"] = "NigelHarveyPlumbing-release-verification/1.0"

    def read(url, authenticated=True):
        if authenticated:
            return session.get(url, timeout=30, allow_redirects=False)
        # Session.auth would otherwise be silently reused for an "anonymous" request.
        return requests.get(url, timeout=30, allow_redirects=False)

    port = int(os.getenv("PORT", "10000"))
    local = f"http://127.0.0.1:{port}"
    api_paths = ("/api/health", "/api/customers", "/api/leads", "/api/quotes",
                 "/api/invoices", "/api/dashboard", "/api/business-performance")
    api = {path: read(local + path).status_code for path in api_paths}
    health = read(local + "/api/health").json() if api["/api/health"] == 200 else {}
    quotes = read(local + "/api/quotes").json() if api["/api/quotes"] == 200 else []
    invoices = read(local + "/api/invoices").json() if api["/api/invoices"] == 200 else []
    documents = {}
    if quotes:
        pdf = read(local + f"/api/quotes/{quotes[0]['id']}/pdf")
        documents["quote_pdf"] = pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        shared = read(origin + quotes[0]["share_pdf_path"], authenticated=environment == "staging")
        documents["shared_quote_pdf"] = shared.status_code == 200 and shared.content.startswith(b"%PDF-")
    if invoices:
        invoice_id = invoices[0]["id"]
        documents["invoice_page"] = read(local + f"/invoice/{invoice_id}").status_code == 200
        pdf = read(local + f"/api/invoices/{invoice_id}/pdf")
        documents["invoice_pdf"] = pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        shared = read(origin + invoices[0]["share_path"], authenticated=environment == "staging")
        documents["shared_invoice_page"] = shared.status_code == 200
        shared_pdf = read(origin + invoices[0]["share_path"] + "/pdf", authenticated=environment == "staging")
        documents["shared_invoice_pdf"] = shared_pdf.status_code == 200 and shared_pdf.content.startswith(b"%PDF-")
    # Authentication checks are anonymous even on staging. Staging guards all routes.
    private = ("/app", "/api/customers", "/api/leads", "/api/quotes",
               "/api/invoices", "/api/dashboard", "/api/business-performance")
    if quotes:
        private += (f"/api/quotes/{quotes[0]['id']}/pdf",)
    if invoices:
        private += (f"/invoice/{invoices[0]['id']}", f"/api/invoices/{invoices[0]['id']}/pdf")
    auth = {path: read(local + path, authenticated=False).status_code for path in private}
    staging_auth = environment == "staging"
    sitemap_response = read(origin + "/sitemap.xml", authenticated=staging_auth)
    robots_response = read(origin + "/robots.txt", authenticated=staging_auth)
    public_routes = {path: read(origin + path, authenticated=staging_auth).status_code
                     for path in ("/", "/request-quote", "/privacy")}
    privacy = read(origin + "/privacy", authenticated=staging_auth)
    privacy_notice = (privacy.status_code == 200 and "Privacy and cookies" in privacy.text
                      and "noindex" in privacy.headers.get("X-Robots-Tag", ""))
    urls = []
    if sitemap_response.status_code == 200:
        urls = [element.text for element in ElementTree.fromstring(sitemap_response.content)
                .iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    failures = []
    schema_blocks = 0
    def schema_urls(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from schema_urls(item)
        elif isinstance(value, list):
            for item in value:
                yield from schema_urls(item)
        elif isinstance(value, str) and value.startswith(("https://", "http://")):
            yield value
    internal = set()
    titles, descriptions, headings = [], [], []
    for url in urls:
        if not url or urlsplit(url).scheme != "https" or urlsplit(url).netloc != urlsplit(origin).netloc:
            failures.append([url, "wrong origin"])
            continue
        page = read(url, authenticated=staging_auth)
        if page.status_code != 200:
            failures.append([url, page.status_code])
            continue
        soup = BeautifulSoup(page.text, "html.parser")
        canonical = soup.find("link", rel="canonical")
        og = soup.find("meta", attrs={"property": "og:url"})
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description = (soup.find("meta", attrs={"name": "description"}) or {}).get("content", "")
        h1 = soup.find("h1")
        headings.append(h1.get_text(" ", strip=True) if h1 else "")
        titles.append(title)
        descriptions.append(description)
        if not title or not description or not headings[-1] or not canonical or canonical.get("href") != url:
            failures.append([url, "metadata/canonical"])
        if og and og.get("content") != url:
            failures.append([url, "Open Graph URL"])
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                parsed_schema = json.loads(script.string or script.get_text())
                schema_blocks += 1
                for schema_url in schema_urls(parsed_schema):
                    hostname = urlsplit(schema_url).netloc.lower()
                    if hostname in {"www.nigelharveyplumbing.co.uk", "nigelharveyplumbing.co.uk",
                                    "nigel-harvey-quotes-staging.onrender.com"} and \
                       hostname != urlsplit(origin).netloc.lower():
                        failures.append([url, "wrong schema hostname"])
            except ValueError:
                failures.append([url, "invalid JSON-LD"])
        for link in soup.select("a[href]"):
            resolved = urljoin(url, link["href"])
            parsed = urlsplit(resolved)
            if parsed.netloc == urlsplit(origin).netloc and parsed.path.startswith("/"):
                internal.add(parsed.path)
    known = {urlsplit(url).path for url in urls} | {"/request-quote", "/privacy", "/app", "/"}
    for path in sorted(internal - known):
        if path.startswith(("/site-images/", "/invoice/", "/api/")):
            continue
        if read(origin + path, authenticated=staging_auth).status_code >= 400:
            failures.append([path, "broken internal link"])
    redirects = {town: (lambda response: [response.status_code, response.headers.get("location")])(
        read(origin + "/blocked-drains-" + town, authenticated=staging_auth)) for town in REDIRECT_TOWNS}
    apex = None
    if environment == "production":
        response = read("https://nigelharveyplumbing.co.uk/", authenticated=False)
        apex = [response.status_code, response.headers.get("location")]
    return {"api_statuses": api, "public_statuses": public_routes,
            "privacy_notice": privacy_notice,
            "health": health, "documents": documents,
            "anonymous_statuses": auth, "sitemap_status": sitemap_response.status_code,
            "sitemap_count": len(urls), "sitemap_unique": len(set(urls)),
            "crawl_failures": failures, "schema_blocks": schema_blocks,
            "internal_destinations": len(internal),
            "duplicate_titles": [v for v, count in Counter(titles).items() if count > 1],
            "duplicate_descriptions": [v for v, count in Counter(descriptions).items() if count > 1],
            "duplicate_h1s": [v for v, count in Counter(headings).items() if count > 1],
            "robots_status": robots_response.status_code,
            "robots": robots_response.text if robots_response.status_code == 200 else "",
            "redirects": redirects, "apex_redirect": apex,
            "server_errors_seen": sorted({status for status in [*api.values(), auth.get("/app"),
                sitemap_response.status_code, robots_response.status_code] if status in (500, 502, 503)}),
            "runtime_log_check": "Use Render logs; this script checks HTTP responses only"}


def evaluate(result):
    db, web, identity = result["database"], result["http"], result["identity"]
    origin = identity["origin"]
    expected_robots = "Disallow: /" if identity["environment"] == "staging" else "Allow: /"
    return (db["integrity"] == "ok" and db["mounted"] and not db["missing_columns"]
            and all(code == 200 for code in web["api_statuses"].values())
            and all(code == 200 for code in web["public_statuses"].values())
            and web["privacy_notice"]
            and web["health"].get("db_exists") is True
            and web["health"].get("sqlite_integrity") == "ok"
            and web["health"].get("var_data_is_mount") is True
            and web["health"].get("counts") == db["counts"]
            and web["health"].get("backup_count") == db["backup_files"]
            and all(web["documents"].values())
            and all(code == 401 for code in web["anonymous_statuses"].values())
            and web["sitemap_status"] == 200 and web["sitemap_count"] == 72
            and web["sitemap_unique"] == 72 and not web["crawl_failures"]
            and not web["duplicate_titles"] and not web["duplicate_descriptions"]
            and not web["duplicate_h1s"] and web["robots_status"] == 200
            and expected_robots in web["robots"]
            and (identity["environment"] == "staging"
                 or f"Sitemap: {origin}/sitemap.xml" in web["robots"])
            and all(pair == [301, "/plumber-" + town] for town, pair in web["redirects"].items())
            and (identity["environment"] != "production" or web["apex_redirect"] == [301, origin + "/"])
            and not web["server_errors_seen"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=SERVICES, required=True)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args(argv)
    if args.environment == "production" and not args.read_only:
        parser.error("Production requires --read-only")
    try:
        db_path = Path("/var/data/quotes.db")
        origin = (os.environ.get("PUBLIC_BASE_URL") or
                  (os.environ.get("RENDER_EXTERNAL_URL") if args.environment == "staging" else "")
                  or "").strip().rstrip("/")
        identity = assert_identity(args.environment, db_path, origin)
        before = inspect_database(db_path)
        username, password = os.environ["APP_USERNAME"], os.environ["APP_PASSWORD"]
        result = {"identity": identity, "database": before,
                  "http": check_http(args.environment, origin, username, password)}
        result["database_after"] = inspect_database(db_path)
        result["ok"] = evaluate(result) and before == result["database_after"]
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2, sort_keys=True))
    print("RELEASE CHECK: " + ("PASS" if result["ok"] else "FAIL"), file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
