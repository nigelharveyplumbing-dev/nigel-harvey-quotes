"""Crawl all public routes offline, with published content and disposable data.

Produces reproducible per-page evidence and all 3,321 pairwise content scores.
The scores measure overlap, not Google's assessment or an indexing prediction.
"""
import argparse
from collections import Counter, deque
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = args.checkout.resolve()
sys.path.insert(0, str(root / "tests"))
sys.path.insert(0, str(root))
from local_browser_server import disposable_app
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup

origin = "https://www.nigelharveyplumbing.co.uk"
digest = lambda s: hashlib.sha256(s.encode()).hexdigest()
with disposable_app("seo-audit-only", "synthetic-offline-only", projects_as_drafts=False,
                    advice_as_drafts=False) as (module, _), TestClient(module.app) as client:
    xml = client.get("/sitemap.xml")
    urls = [x.text for x in ET.fromstring(xml.text).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert len(urls) == len(set(urls)) == 82
    pages, failures, media = {}, [], set()
    from business.public_pages import SOUTH_WEST_LONDON_PAGES
    names = sorted([x["name"].lower() for x in module.LOCATION_PAGES + SOUTH_WEST_LONDON_PAGES] + ["surrey"], key=len, reverse=True)
    for url in urls:
        path = urlsplit(url).path
        response = client.get(path)
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = [x.get("href") for x in soup.select('link[rel="canonical"]')]
        title = soup.title.get_text(strip=True) if soup.title else ""
        meta = soup.select('meta[name="description"]')
        description = meta[0].get("content", "") if len(meta) == 1 else ""
        h1 = [x.get_text(" ", strip=True) for x in soup.select("h1")]
        if response.status_code != 200 or canonical != [url] or len(h1) != 1 or not title or not description:
            failures.append({"path": path, "error": "status/canonical/heading/metadata"})
        if "noindex" in response.headers.get("x-robots-tag", "") or soup.select('meta[name="robots"][content*="noindex"]'):
            failures.append({"path": path, "error": "unexpected noindex"})
        schemas = [json.loads(x.string) for x in soup.select('script[type="application/ld+json"]')]
        links = []
        for a in soup.select("a[href]"):
            u = urlsplit(urljoin(url, a["href"]))
            if u.netloc == urlsplit(origin).netloc and u.scheme in ("https", "http"):
                links.append({"path": u.path or "/", "fragment": u.fragment, "text": a.get_text(" ", strip=True)})
        for img in soup.select("img[src]"):
            u = urlsplit(urljoin(url, img["src"]))
            if u.netloc == urlsplit(origin).netloc:
                media.add(u.path)
        scripts = [x.get_text() for x in soup.select("script") if x.get("type") != "application/ld+json"]
        main = BeautifulSoup(str(soup.select_one("main") or soup.body), "html.parser")
        for x in main.select("script, style, header, footer, nav, .pill-links, .area-links, .service-links, .cta, .hero-review-badge, #reviews, #areas"):
            x.decompose()
        text = main.get_text(" ", strip=True)
        normal = text.lower()
        for name in names:
            normal = re.sub(r"\b" + re.escape(name) + r"\b", "<area>", normal)
        words = re.findall(r"[a-z0-9<>]+", normal)
        shingles = set(" ".join(words[i:i+5]) for i in range(max(0, len(words)-4)))
        pages[path] = {"status": response.status_code, "title": title, "description": description,
                       "canonical": canonical[0], "h1": h1[0], "words": len(text.split()),
                       "content": text, "normalizedContentHash": digest(normal), "shingles": sorted(shingles),
                       "htmlHash": digest(response.text), "scriptsHash": digest(json.dumps(scripts)),
                       "headerHash": digest(str(soup.header)), "footerHash": digest(str(soup.footer)),
                       "formHash": digest(str(soup.select("form"))),
                       "links": links, "ids": [x["id"] for x in soup.select("[id]")], "schemas": schemas}
    for path, page in pages.items():
        for link in page["links"]:
            target = link["path"]
            if target in pages:
                if link["fragment"] and link["fragment"] not in pages[target]["ids"]:
                    failures.append({"path": path, "error": "missing fragment", "target": link})
            elif target not in ("/app",) and not target.startswith("/api/"):
                r = client.get(target)
                if r.status_code != 200:
                    failures.append({"path": path, "error": "broken internal target", "target": target})
    for asset in media:
        if client.get(asset).status_code != 200:
            failures.append({"error": "broken image", "target": asset})
    for key in ("title", "description", "h1"):
        duplicates = [v for v, n in Counter(p[key] for p in pages.values()).items() if n > 1]
        if duplicates:
            failures.append({"error": "duplicate " + key, "values": duplicates})
    inbound = {p: set() for p in pages}
    for p, page in pages.items():
        for link in page["links"]:
            if link["path"] in inbound and link["path"] != p:
                inbound[link["path"]].add(p)
    depth, queue = {"/": 0}, deque(["/"])
    while queue:
        p = queue.popleft()
        for link in pages[p]["links"]:
            t = link["path"]
            if t in pages and t not in depth:
                depth[t] = depth[p] + 1
                queue.append(t)
    for p in pages:
        pages[p]["inboundSources"] = sorted(inbound[p])
        pages[p]["clickDepth"] = depth.get(p)
        if p not in depth or not inbound[p]:
            failures.append({"path": p, "error": "orphan/unreachable"})
    pairs = []
    for a, b in itertools.combinations(pages, 2):
        x, y = set(pages[a]["shingles"]), set(pages[b]["shingles"])
        pairs.append({"a": a, "b": b, "jaccard5": round(len(x & y) / max(1, len(x | y)), 4)})
    for page in pages.values():
        del page["shingles"]
    result = {"origin": origin, "pages": pages, "pairs": sorted(pairs, key=lambda x: -x["jaccard5"]),
              "failures": failures, "pageCount": len(pages), "pairCount": len(pairs), "mediaCount": len(media)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("pageCount", "pairCount", "mediaCount", "failures")}))
    raise SystemExit(bool(failures))
