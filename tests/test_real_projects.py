"""Project evidence, approval gates and the proposed published SEO behaviour."""

import base64
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from local_browser_server import disposable_app

ROOT = Path(__file__).resolve().parents[1]
REVIEW = "Nigel did a complete fit of an en-suite bathroom for us, including radiation, tiling, flooring, shower tray, glass window and toilet. We are very pleased with the result. Nigel communicated well and explained options along the way. Much recommended."


class RealProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(18))
        cls.module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        cls.projects = cls.module.real_projects
        cls.project = cls.projects.PROJECTS[0]
        token = f"{cls.module.APP_USERNAME}:{cls.module.APP_PASSWORD}".encode()
        cls.auth = {"Authorization": "Basic " + base64.b64encode(token).decode()}

    def published(self):
        data = self.project.model_dump(mode="json")
        data.update(status="published", approved_at="2026-10-06T20:00:00+01:00",
                    published_at="2026-10-06T20:05:00+01:00")
        return self.projects.Project.model_validate(data)

    def test_owner_approved_production_catalogue_is_published_without_content_changes(self):
        record = json.loads((ROOT / "business/project_content.json").read_text())[0]
        self.assertEqual(record["status"], "published")
        self.assertEqual(record["approved_at"], "2026-10-08T22:02:45+01:00")
        self.assertEqual(record["published_at"][:10], "2026-10-08")
        self.assertEqual(record["review"]["text"], REVIEW)
        self.assertEqual(record["review"]["attribution"], "Tristan, Merrow")
        self.assertEqual(len(record["images"]), 9)
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(18),
                            projects_as_drafts=False) as (module, _), TestClient(module.app) as client:
            project = module.real_projects.PROJECTS[0]
            self.assertEqual(project.status, "published")
            self.assertEqual(client.get(project.path).status_code, 200)
            self.assertIn(project.path, client.get("/projects").text)
            self.assertIn(project.path, client.get("/sitemap.xml").text)
            self.assertNotIn("noindex", client.get(project.path).headers.get("X-Robots-Tag", ""))

    def test_draft_requires_staff_auth_and_does_not_leak(self):
        c, p = self.client, self.project
        self.assertEqual(c.get(p.path).status_code, 404)
        self.assertEqual(c.get(p.path, headers={"Authorization": "Basic ZmFrZTpmYWtl"}).status_code, 404)
        response = c.get(p.path, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response.headers["X-Robots-Tag"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertIn("Draft for Nigel’s review", response.text)
        self.assertIn('data-send-to-google="false"', response.text)
        self.assertNotIn(p.title, c.get("/projects").text)
        self.assertIn(p.title, c.get("/projects", headers=self.auth).text)
        self.assertNotIn(p.path, c.get("/sitemap.xml").text)
        for link in p.links:
            self.assertNotIn(p.path, c.get(link.path).text)
        self.assertEqual(c.get("/projects/does-not-exist", headers=self.auth).status_code, 404)
        self.assertEqual(c.post(p.path, headers=self.auth).status_code, 405)

    def test_published_routing_sitemap_and_exact_canonical(self):
        p = self.published()
        with patch.object(self.projects, "PROJECTS", (p,)):
            response = self.client.get(p.path + "?utm_source=test", headers={"Host": "untrusted.example"})
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.text, "html.parser")
            self.assertEqual(soup.select_one('link[rel="canonical"]')["href"], "https://www.nigelharveyplumbing.co.uk" + p.path)
            self.assertNotIn("noindex", response.headers.get("X-Robots-Tag", ""))
            self.assertEqual(soup.select_one('meta[name="robots"]')["content"], "index,follow,max-image-preview:large")
            sitemap = ElementTree.fromstring(self.client.get("/sitemap.xml").text)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            entries = sitemap.findall("s:url", ns)
            locations = [node.findtext("s:loc", namespaces=ns) for node in entries]
            self.assertEqual(len(locations), 74)
            self.assertEqual(len(locations), len(set(locations)))
            self.assertIn("https://www.nigelharveyplumbing.co.uk/projects", locations)
            for entry in entries:
                path = urlsplit(entry.findtext("s:loc", namespaces=ns)).path
                self.assertEqual(self.client.get(path).status_code, 200, path)
                if path.startswith("/projects"):
                    self.assertEqual(entry.findtext("s:lastmod", namespaces=ns), p.updated_on.isoformat())
                self.assertFalse(path.startswith(("/app", "/api/")))

    def test_structured_data_has_real_identity_images_and_no_review_markup(self):
        p = self.published()
        with patch.object(self.projects, "PROJECTS", (p,)):
            soup = BeautifulSoup(self.client.get(p.path).text, "html.parser")
        graph = json.loads(soup.select_one('script[type="application/ld+json"]').string)
        self.assertEqual(graph["@context"], "https://schema.org")
        by_type = {item["@type"]: item for item in graph["@graph"]}
        self.assertEqual(set(by_type), {"Plumber", "Article", "BreadcrumbList"})
        article = by_type["Article"]
        canonical = "https://www.nigelharveyplumbing.co.uk" + p.path
        self.assertEqual(article["url"], canonical)
        self.assertEqual(article["mainEntityOfPage"], canonical)
        self.assertEqual(article["headline"], soup.h1.get_text())
        self.assertEqual(article["contentLocation"], {"@type": "Place", "name": "Merrow, Guildford"})
        self.assertEqual(article["publisher"]["@id"], by_type["Plumber"]["@id"])
        self.assertEqual(article["author"]["name"], "Nigel Harvey Plumbing")
        self.assertEqual(len(article["image"]), 9)
        datetime.fromisoformat(article["datePublished"])
        for prohibited in ("Review", "AggregateRating", "reviewRating", "streetAddress", "hasCredential"):
            self.assertNotIn(prohibited, json.dumps(graph))
        self.assertEqual([item["position"] for item in by_type["BreadcrumbList"]["itemListElement"]], [1, 2, 3])
        draft_graph = self.projects.schema_graph(self.project, self.module.absolute_url)
        self.assertNotIn("datePublished", json.dumps(draft_graph))

    def test_review_facts_metadata_and_privacy(self):
        response = self.client.get(self.project.path, headers=self.auth)
        soup = BeautifulSoup(response.text, "html.parser")
        self.assertEqual(soup.blockquote.p.get_text(), "“" + REVIEW + "”")
        self.assertEqual(soup.cite.get_text(), "Tristan, Merrow")
        self.assertEqual(soup.title.string, self.project.seo_title)
        self.assertEqual(soup.select_one('meta[name="description"]')["content"], self.project.meta_description)
        self.assertEqual(len(soup.select('main h1')), 1)
        self.assertEqual(len(soup.select('main img')), 9)
        self.assertNotIn("definitive technical cause", soup.get_text())
        self.assertIn("Marmox", soup.get_text())
        for prohibited in ("professional mould remediation", "guaranteed mould-free", "source-photos", "libfile_", "source_sha256"):
            self.assertNotIn(prohibited, response.text)
        self.assertIn('data-measurement-id="G-Q9Z2WWNF6F"', response.text)
        self.assertIn("landing_page", response.text)

    def test_owner_refinements_keep_the_story_photos_and_enquiry_in_order(self):
        soup = BeautifulSoup(self.client.get(self.project.path, headers=self.auth).text, "html.parser")
        story = soup.select_one(".project-story")
        self.assertEqual([h.get_text() for h in story.select("h2")],
                         ["What the strip-out revealed", "Work carried out", "The finished result"])
        opening = story.section
        self.assertEqual(len(opening.select("p")), 2)
        for fact in ("visible mould", "insulation build-up", "stripped back", "rebuilt"):
            self.assertIn(fact, opening.get_text())
        for claim in ("definitive technical cause", "professional mould remediation", "caused by"):
            self.assertNotIn(claim, story.get_text().lower())
        gallery = soup.select_one(".project-gallery")
        stages = gallery.select(".project-gallery-stage")
        self.assertEqual([len(stage.select("img")) for stage in stages], [2, 4, 2])
        finished = gallery.select_one(".project-gallery-stage--after")
        self.assertEqual([Path(img["src"]).name for img in finished.select("img")],
                         ["finished-shower-1280.webp", "finished-vanity-1280.webp"])
        enquiry = gallery.select_one(".project-gallery-enquiry")
        self.assertIs(finished.find_next_sibling(), enquiry)
        button = enquiry.select_one("a.btn")
        self.assertEqual(button.get_text(), "Discuss your bathroom")
        self.assertEqual(urlsplit(button["href"]).path, "/request-quote")
        self.assertEqual(self.client.get(button["href"]).status_code, 200)
        self.assertEqual(len(soup.select("main img")), 9)

    def test_reciprocal_links_only_on_relevant_published_pages(self):
        p = self.published()
        with patch.object(self.projects, "PROJECTS", (p,)):
            soup = BeautifulSoup(self.client.get(p.path).text, "html.parser")
            for link in p.links:
                self.assertTrue(soup.select(f'main a[href="{link.path}"]'))
                page = self.client.get(link.path)
                self.assertEqual(page.status_code, 200)
                self.assertIn(p.path, page.text)
            # Batch 8 permits a nearby example, explicitly labelled as Merrow,
            # without claiming this project took place in Woking.
            woking = self.client.get("/plumber-woking").text
            self.assertIn(p.path, woking)
            self.assertIn("project took place in Merrow, Guildford", woking)
            self.assertNotIn(p.path, self.client.get("/leak-repair-guildford").text)
            for a in soup.select('main a[href^="/"]'):
                self.assertEqual(self.client.get(a["href"]).status_code, 200, a["href"])
        self.assertIn('href="/projects"', self.client.get("/").text)

    def test_review_opt_in_and_escaped_content(self):
        p = self.project.model_copy(update={"review": self.project.review.model_copy(update={"approved_for_use": False})})
        html = self.projects.render_project(p, absolute_url=self.module.absolute_url)
        self.assertNotIn(REVIEW, html)
        self.assertNotIn("Tristan, Merrow", html)
        hostile = self.project.model_copy(update={"summary": '<script>alert("test")</script>'})
        soup = BeautifulSoup(self.projects.render_project(hostile, absolute_url=self.module.absolute_url), "html.parser")
        self.assertEqual(soup.select_one(".project-lead").get_text(), hostile.summary)
        self.assertFalse(any(script.get_text() == 'alert("test")' for script in soup.select("script")))

    def test_publication_validation_and_duplicate_detection(self):
        data = self.project.model_dump(mode="json")
        for update in ({"status": "published"}, {"location": "12 Example Road, Merrow"},
                       {"customer_email": "private@example.invalid"}, {"hero_image": "absent"}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                self.projects.Project.model_validate({**data, **update})
        with patch.object(self.projects, "ROOT", self.root):
            source = self.root / "business/project_content.json"
            original = source.read_text()
            self.addCleanup(source.write_text, original)
            source.write_text(json.dumps([data, data]))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                self.projects.load_projects()

    def test_image_allowlist_dimensions_formats_metadata_and_private_source_provenance(self):
        p = self.project
        image = p.images[0]
        path = self.projects.image_path(p, image)
        self.assertEqual(self.client.get(path).status_code, 404)
        response = self.client.get(path, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(response.headers["content-type"], "image/webp")
        self.assertEqual(self.client.get(f"/project-images/{p.slug}/manifest.json", headers=self.auth).status_code, 404)
        self.assertEqual(self.client.get(f"/project-images/{p.slug}/IMG_2393.jpeg", headers=self.auth).status_code, 404)
        with patch.object(self.projects, "PROJECTS", (self.published(),)):
            public = self.client.get(path)
            self.assertEqual(public.status_code, 200)
            self.assertIn("public", public.headers["Cache-Control"])
            soup = BeautifulSoup(self.client.get(p.path).text, "html.parser")
            eager = soup.select('main img[loading="eager"]')
            self.assertEqual(len(eager), 1)
            self.assertEqual(eager[0]["fetchpriority"], "high")
            for img in soup.select("main img"):
                response = self.client.get(img["src"])
                with Image.open(io.BytesIO(response.content)) as web:
                    self.assertEqual(web.format, "WEBP")
                    self.assertEqual(web.size, (int(img["width"]), int(img["height"])))
                    self.assertFalse(web.getexif())
                    self.assertNotIn("xmp", web.info)
                self.assertIn("640w", img["srcset"])
                self.assertTrue(img["alt"].strip())
                for entry in img["srcset"].split(","):
                    url, width = entry.strip().split()
                    with Image.open(io.BytesIO(self.client.get(url).content)) as small:
                        self.assertEqual(small.width, int(width[:-1]))
        manifest = json.loads((ROOT / "docs/project-images/merrow-ensuite/manifest.json").read_text())
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(len(manifest["images"]), 9)
        for record in manifest["images"]:
            self.assertNotIn("source", record)
            self.assertRegex(record["source_sha256"], r"^[a-f0-9]{64}$")
            for variant in record["variants"]:
                asset = ROOT / "static/project-images/ensuite-renovation-merrow-guildford" / variant["filename"]
                self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), variant["sha256"])
                self.assertEqual(asset.stat().st_size, variant["bytes"])
                with Image.open(asset) as web:
                    self.assertEqual(web.format, "WEBP")
                    self.assertEqual(web.size, (variant["width"], variant["height"]))
                    self.assertFalse(web.getexif())
                    for metadata in ("exif", "xmp", "icc_profile"):
                        self.assertNotIn(metadata, web.info)

    def test_public_project_assets_and_preview_contain_only_cleared_derivatives(self):
        self.assertFalse((ROOT / "docs/project-sources").exists())
        folder = ROOT / "static/project-images" / self.project.slug
        expected = {f"{image.id}-{size}.webp" for image in self.project.images for size in (640, 1280)}
        self.assertEqual({path.name for path in folder.iterdir()}, expected)
        self.assertEqual({path.name for path in (ROOT / "docs/project-images/merrow-ensuite").iterdir()}, {"manifest.json"})
        hashes = {hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in expected}
        preview = BeautifulSoup((ROOT / "docs/growth-batch-6-preview/merrow-case-study-preview.html").read_text(), "html.parser")
        images = preview.select("main img")
        self.assertEqual(len(images), 9)
        for img in images:
            self.assertTrue(img["src"].startswith("data:image/webp;base64,"))
            self.assertIn(hashlib.sha256(base64.b64decode(img["src"].split(",", 1)[1])).hexdigest(), hashes)

    def test_sitemap_preserves_exact_main_baseline_and_retired_drain_redirects(self):
        evidence = json.loads((ROOT / "docs/sitemap-baseline-reconciliation.json").read_text())
        baseline = set(evidence["main_paths"])
        self.assertEqual(len(baseline), 72)

        def paths():
            xml = ElementTree.fromstring(self.client.get("/sitemap.xml").text)
            return {urlsplit(node.text).path for node in xml.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}

        self.assertEqual(paths(), baseline)
        with patch.object(self.projects, "PROJECTS", (self.published(),)):
            self.assertEqual(paths(), baseline | {"/projects", self.project.path})
        self.assertEqual(len(evidence["removed_since_growth_5"]), 13)
        for path in evidence["removed_since_growth_5"]:
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response.headers["location"], path.replace("/blocked-drains-", "/plumber-"))
            self.assertEqual(self.client.get(response.headers["location"]).status_code, 200)

    def test_app_and_staging_indexing_stay_private(self):
        for path in ("/app", "/api/jobs"):
            self.assertEqual(self.client.get(path).status_code, 401)
            self.assertIn("noindex", self.client.get(path).headers["X-Robots-Tag"])
            response = self.client.get(path, headers=self.auth)
            self.assertEqual(response.status_code, 200)
            self.assertIn("noindex", response.headers["X-Robots-Tag"])
        self.assertIn("Disallow: /app", self.client.get("/robots.txt").text)
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "staging", "PUBLIC_BASE_URL": "https://preview.example.invalid"}), \
                patch.object(self.projects, "PROJECTS", (self.published(),)):
            self.assertEqual(self.client.get(self.project.path).status_code, 401)
            response = self.client.get(self.project.path, headers=self.auth)
            self.assertIn("noindex", response.headers["X-Robots-Tag"])
            self.assertIn("https://preview.example.invalid" + self.project.path, response.text)
            self.assertIn('data-send-to-google="false"', response.text)
            self.assertEqual(self.client.get("/robots.txt", headers=self.auth).text, "User-agent: *\nDisallow: /\n")
            self.assertNotIn("https://www.nigelharveyplumbing.co.uk/projects", self.client.get("/sitemap.xml", headers=self.auth).text)
