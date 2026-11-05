"""Read-only checks against PR48's authenticated hosted staging service.

Password is read from the terminal, never a shell argument or saved artifact.
Optionally passes it in process memory to the four-width browser matrix.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import getpass
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup

parser = argparse.ArgumentParser()
parser.add_argument("--origin", required=True)
parser.add_argument("--username", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--browser", action="store_true")
args = parser.parse_args()
origin = args.origin.rstrip("/")
assert urlsplit(origin).scheme == "https" and urlsplit(origin).hostname.endswith(".onrender.com")
auth = (args.username, getpass.getpass("Staging password: "))
anonymous = requests.get(origin + "/sitemap.xml", timeout=60)
assert anonymous.status_code == 401
sitemap = requests.get(origin + "/sitemap.xml", auth=auth, timeout=60)
sitemap.raise_for_status()
assert "noindex" in sitemap.headers.get("x-robots-tag", "")
urls = [x.text for x in ET.fromstring(sitemap.text).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
assert len(urls) == len(set(urls)) == 82
assert all(urlsplit(u).netloc == urlsplit(origin).netloc for u in urls)


def inspect(url):
    response = requests.get(url, auth=auth, timeout=60)
    page = BeautifulSoup(response.text, "html.parser")
    links = []
    for a in page.select("a[href]"):
        target = urlsplit(urljoin(url, a["href"]))
        if target.netloc == urlsplit(origin).netloc:
            links.append({"path": target.path or "/", "fragment": target.fragment})
    return {"path": urlsplit(url).path, "status": response.status_code,
            "canonical": [x.get("href") for x in page.select('link[rel="canonical"]')],
            "title": page.title.get_text(strip=True) if page.title else "",
            "description": [x.get("content") for x in page.select('meta[name="description"]')],
            "h1": len(page.select("h1")), "noindex": response.headers.get("x-robots-tag"),
            "revision": response.headers.get("x-preview-commit"),
            "analyticsSend": page.select_one("#public-analytics").get("data-send-to-google"),
            "links": links, "ids": [x["id"] for x in page.select("[id]")]}


with ThreadPoolExecutor(max_workers=5) as pool:
    pages = list(pool.map(inspect, urls))
by_path = {x["path"]: x for x in pages}
failures = []
for p in pages:
    if p["status"] != 200 or p["canonical"] != [origin+p["path"]] or not p["title"] or len(p["description"]) != 1 or not p["description"][0] or p["h1"] != 1:
        failures.append({"path": p["path"], "error": "HTTP/canonical/metadata"})
    if "noindex" not in (p["noindex"] or "") or p["analyticsSend"] != "false" or not p["revision"]:
        failures.append({"path": p["path"], "error": "staging controls/revision"})
    for link in p["links"]:
        if link["path"] in by_path:
            if link["fragment"] and link["fragment"] not in by_path[link["path"]]["ids"]:
                failures.append({"path": p["path"], "error": "fragment", "target": link})
        elif link["path"] not in ("/app",) and not link["path"].startswith("/api/"):
            # Full-size project photographs are intentional link destinations,
            # not HTML pages that belong in the public sitemap.
            target = requests.get(origin+link["path"], auth=auth, timeout=60)
            if target.status_code != 200:
                failures.append({"path": p["path"], "error": "broken target", "target": link})
for key in ("title",):
    if len({p[key] for p in pages}) != 82:
        failures.append({"error": "duplicate " + key})
assert len({p["revision"] for p in pages}) == 1, "Mixed staging revisions"
robots = requests.get(origin+"/robots.txt", auth=auth, timeout=60)
result = {"origin": origin, "pageCount": len(pages), "anonymousStatus": anonymous.status_code,
          "revision": pages[0]["revision"], "pages": pages, "failures": failures,
          "robots": robots.text, "robotsNoindex": robots.headers.get("x-robots-tag")}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps({"pages": len(pages), "revision": result["revision"], "failures": failures}), flush=True)
assert not failures
if args.browser:
    env = {**os.environ, "NHP_SEO_STAGING_URL": origin,
           "NHP_SEO_STAGING_USERNAME": auth[0], "NHP_SEO_STAGING_PASSWORD": auth[1],
           "FULL_SITE_EVIDENCE_DIR": "/tmp/nhp-pr48-hosted-layouts"}
    raise SystemExit(subprocess.call(["node", "tests/run_full_site_browser.mjs"], env=env,
                                    cwd=Path(__file__).resolve().parents[1]))
