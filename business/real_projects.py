"""Reviewed project records, shared rendering and explicit publication gates.

This module has no app/database writes or publishing/network side effects.
Only approved published records enter public links, images or the sitemap.
"""

from datetime import date, datetime
from html import escape
import json
from pathlib import Path
import re
from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, model_validator

from business import public_layout

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/real_projects.css").read_text(encoding="utf-8")


class PublicRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectLink(PublicRecord):
    path: str = Field(pattern=r"^/[a-z0-9/-]+$")
    label: str = Field(min_length=1)


class ProjectImage(PublicRecord):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    stage: Literal["before", "during", "after"]
    alt: str = Field(min_length=1)
    caption: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ProjectReview(PublicRecord):
    text: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    source: Literal["Google"]
    stars: Literal[5]
    approved_for_use: bool = False


class ProjectFAQ(PublicRecord):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class Project(PublicRecord):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["draft", "published"] = "draft"
    approved_at: datetime | None = None
    published_at: datetime | None = None
    updated_on: date
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    services: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    findings: str = Field(min_length=1)
    work: list[str] = Field(min_length=1)
    materials: list[str] = Field(default_factory=list)
    result: str = Field(min_length=1)
    images: list[ProjectImage] = Field(min_length=1)
    hero_image: str
    review: ProjectReview | None = None
    links: list[ProjectLink] = Field(min_length=1)
    faqs: list[ProjectFAQ] = Field(default_factory=list)
    seo_title: str = Field(min_length=1, max_length=80)
    meta_description: str = Field(min_length=1, max_length=180)

    @model_validator(mode="after")
    def valid_public_record(self):
        if self.status == "published":
            if not self.approved_at or not self.published_at:
                raise ValueError("Publication requires explicit approval and a real publication date")
            if not self.approved_at.tzinfo or not self.published_at.tzinfo:
                raise ValueError("Approval and publication timestamps require a timezone")
            if self.approved_at > self.published_at or self.updated_on < self.published_at.date():
                raise ValueError("Project dates are out of order")
        if re.search(r"\d|@|\b(?:road|street|lane|avenue|close)\b", self.location, re.I):
            raise ValueError("Use town/area only, never a customer address")
        ids = [image.id for image in self.images]
        if len(ids) != len(set(ids)) or self.hero_image not in ids:
            raise ValueError("Images must be unique and the hero must exist")
        return self

    @property
    def path(self):
        return f"/projects/{self.slug}"


def load_projects():
    records = json.loads((ROOT / "business/project_content.json").read_text(encoding="utf-8"))
    projects = tuple(Project.model_validate(record) for record in records)
    if len({project.slug for project in projects}) != len(projects):
        raise ValueError("Duplicate project slug")
    return projects


PROJECTS = load_projects()


def visible_projects(*, include_drafts=False):
    return tuple(p for p in PROJECTS if p.status == "published" or include_drafts)


def image_path(project, image, size=1280):
    return f"/project-images/{project.slug}/{image.id}-{size}.webp"


def image_html(project, image, *, hero=False):
    return (f'<img src="{image_path(project, image)}" '
            f'srcset="{image_path(project, image, 640)} 640w, {image_path(project, image)} {image.width}w" '
            f'sizes="(max-width: 640px) 92vw, (max-width: 900px) 44vw, 540px" '
            f'width="{image.width}" height="{image.height}" alt="{escape(image.alt, quote=True)}" '
            f'loading="{"eager" if hero else "lazy"}" decoding="async"'
            + (' fetchpriority="high"' if hero else '') + '>')


def schema_graph(project, absolute_url, request=None):
    from business.public_pages import public_business_entity
    home = absolute_url("/", request)
    canonical = absolute_url(project.path, request)
    business = public_business_entity(home)
    business.pop("@context", None)
    article = {
        "@type": "Article", "@id": canonical + "#article", "url": canonical,
        "mainEntityOfPage": canonical, "headline": project.title,
        "description": project.summary, "inLanguage": "en-GB",
        "author": {"@type": "Organization", "name": "Nigel Harvey Plumbing", "url": home},
        "publisher": {"@id": home + "#business"},
        "contentLocation": {"@type": "Place", "name": project.location},
        "about": [{"@type": "Thing", "name": service} for service in project.services],
        "image": [absolute_url(image_path(project, image), request) for image in project.images],
    }
    # A draft has not been published. Do not invent publication dates.
    if project.status == "published":
        article["datePublished"] = project.published_at.isoformat()
        article["dateModified"] = project.updated_on.isoformat()
    breadcrumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": home},
        {"@type": "ListItem", "position": 2, "name": "Real projects", "item": absolute_url("/projects", request)},
        {"@type": "ListItem", "position": 3, "name": project.title, "item": canonical},
    ]}
    # Review is visible editorial evidence only: no Review, Rating or AggregateRating.
    return {"@context": "https://schema.org", "@graph": [business, article, breadcrumbs]}


def page_shell(title, description, canonical, content, *, noindex=False, schema=None, og_image=None):
    head = (f'<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">'
            f'<link rel="canonical" href="{escape(canonical, quote=True)}">'
            f'<meta name="robots" content="{"noindex,nofollow" if noindex else "index,follow,max-image-preview:large"}">'
            f'<meta property="og:title" content="{escape(title, quote=True)}">'
            f'<meta property="og:description" content="{escape(description, quote=True)}">'
            f'<meta property="og:url" content="{escape(canonical, quote=True)}">'
            '<meta property="og:type" content="article">')
    if og_image:
        head += f'<meta property="og:image" content="{escape(og_image, quote=True)}">'
    if schema:
        head += '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c") + '</script>'
    analytics = public_layout.analytics_markup()
    if noindex:
        analytics = analytics.replace('data-send-to-google="true"', 'data-send-to-google="false"')
    return (f'<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + head + '<style>' + public_layout.SITE_CSS + CSS + '</style></head>'
            '<body class="project-page">' + public_layout.site_header() + '<main id="main">'
            + content + '</main>' + public_layout.site_footer() + analytics + '</body></html>')


def render_project(project, *, absolute_url, request=None, staging=False):
    canonical = absolute_url(project.path, request)
    hero = next(image for image in project.images if image.id == project.hero_image)
    draft = project.status == "draft"
    banner = '<div class="project-draft wrap">Draft for Nigel’s review · not published</div>' if draft else ''
    dates = (f'Draft updated <time datetime="{project.updated_on}">{project.updated_on:%d %B %Y}</time>' if draft else
             f'Published <time datetime="{project.published_at.isoformat()}">{project.published_at:%d %B %Y}</time> · '
             f'Updated <time datetime="{project.updated_on}">{project.updated_on:%d %B %Y}</time>')
    content = banner + f'''<div class="wrap project-breadcrumb"><a href="/">Home</a> / <a href="/projects">Real projects</a> / {escape(project.title)}</div>
<article><header class="wrap project-intro"><div><p class="kicker">A real completed project · {escape(project.location)}</p><h1>{escape(project.title)}</h1><p class="project-lead">{escape(project.summary)}</p><p class="project-byline">Project account by Nigel Harvey Plumbing · Work carried out by <a href="/#about">Nigel Harvey</a><br>{dates}</p><a class="btn" href="/request-quote">Discuss your bathroom</a></div><figure>{image_html(project, hero, hero=True)}<figcaption>{escape(hero.caption)}</figcaption></figure></header>
<section class="project-facts"><div class="wrap"><h2>The job at a glance</h2><dl><div><dt>Location</dt><dd>{escape(project.location)}</dd></div><div><dt>Work</dt><dd>{escape(", ".join(project.services))}</dd></div><div><dt>Carried out by</dt><dd>Nigel Harvey Plumbing</dd></div><div><dt>Materials / systems</dt><dd>{escape("; ".join(project.materials) or "Not recorded")}</dd></div></dl></div></section>
<div class="wrap project-story"><section><h2>What the strip-out revealed</h2><p>{escape(project.problem)}</p><p>{escape(project.findings)}</p></section><section><h2>Work carried out</h2><ul>{"".join("<li>" + escape(item) + "</li>" for item in project.work)}</ul></section><section><h2>The finished result</h2><p>{escape(project.result)}</p></section></div>
<section class="project-gallery"><div class="wrap"><h2>From strip-out to the finished ensuite</h2><p>Real photographs from this project, showing the construction stages and completed room.</p>'''
    for stage, title in (("before", "Strip-out and findings"), ("during", "Rebuilding, preparation and tiling"), ("after", "The finished shower and vanity")):
        images = [image for image in project.images if image.stage == stage and image.id != project.hero_image]
        if images:
            content += f'<section class="project-gallery-stage project-gallery-stage--{stage}"><h3>{title}</h3><div class="project-photo-grid">'
            content += ''.join(f'<figure><a href="{image_path(project, image)}" aria-label="{escape("View larger photo: " + image.alt, quote=True)}">{image_html(project, image)}</a><figcaption>{escape(image.caption)}</figcaption></figure>' for image in images)
            content += '</div></section>'
    content += '<div class="project-gallery-enquiry"><div><h3>Thinking about updating your bathroom?</h3><p>Tell Nigel what you would like to change.</p></div><a class="btn" href="/request-quote">Discuss your bathroom</a></div></div></section>'
    if project.review and project.review.approved_for_use:
        review = project.review
        content += f'<section class="wrap project-review"><h2>Customer feedback</h2><p class="project-review-source">{review.stars}-star {review.source} review</p><blockquote><p>“{escape(review.text)}”</p><cite>{escape(review.attribution)}</cite></blockquote></section>'
    if project.faqs:
        content += '<section class="wrap project-faq"><h2>Questions about this project</h2>'
        content += ''.join(f'<h3>{escape(faq.question)}</h3><p>{escape(faq.answer)}</p>' for faq in project.faqs)
        content += '</section>'
    content += '<section class="wrap project-related"><h2>Related plumbing services and areas</h2><ul>'
    content += ''.join(f'<li><a href="{link.path}">{escape(link.label)}</a></li>' for link in project.links)
    content += '</ul></section></article><section class="final"><div class="wrap"><div><h2>Planning your own bathroom?</h2><p>Tell Nigel what you would like to change and where the work is.</p></div><a class="btn light" href="/request-quote">Request a quote</a></div></section>'
    return page_shell(project.seo_title, project.meta_description, canonical, content,
                      noindex=draft or staging, schema=schema_graph(project, absolute_url, request),
                      og_image=absolute_url(image_path(project, hero), request))


def render_index(*, absolute_url, request=None, include_drafts=False, staging=False):
    records = visible_projects(include_drafts=include_drafts)
    content = '<section class="wrap project-index"><p class="kicker">Nigel Harvey Plumbing</p><h1>Real plumbing projects</h1><p>Completed jobs, with photographs and a practical account of the work carried out.</p>'
    if not records:
        content += '<p>Project accounts are being prepared. <a href="/request-quote">Contact Nigel to discuss your job</a>.</p>'
    for project in records:
        hero = next(image for image in project.images if image.id == project.hero_image)
        content += f'<article class="project-card">{image_html(project, hero)}<div><p class="kicker">{escape(project.location)}</p><h2><a href="{project.path}">{escape(project.title)}</a></h2><p>{escape(project.summary)}</p>'
        if project.status == "draft":
            content += '<p>Draft for Nigel’s review · not published</p>'
        content += '</div></article>'
    content += '</section>'
    return page_shell("Real Plumbing Projects | Nigel Harvey Plumbing", "Real completed plumbing projects by Nigel Harvey Plumbing, with job photographs, findings and practical work accounts.", absolute_url("/projects", request), content,
                      noindex=staging or include_drafts or not records)


def add_related_project_links(html, path):
    """Published evidence only; unchanged HTML when no relevant record exists."""
    related = [p for p in visible_projects() if any(link.path == path for link in p.links)]
    if not related:
        return html
    soup = BeautifulSoup(html, "html.parser")
    markup = '<section class="wrap section"><h2>A real completed project</h2>'
    markup += ''.join(f'<p><a href="{p.path}">{escape(p.title)}</a> — {escape(p.summary)}</p>' for p in related)
    markup += '</section>'
    soup.main.append(BeautifulSoup(markup, "html.parser"))
    return str(soup)


def sitemap_entries():
    published = visible_projects()
    if not published:
        return ()
    return (("/projects", max(p.updated_on for p in published)),
            *((p.path, p.updated_on) for p in published))
