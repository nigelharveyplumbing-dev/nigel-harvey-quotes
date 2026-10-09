"""Editorial records only. No DB access, network calls or automatic publishing."""
from datetime import date, datetime
from difflib import SequenceMatcher
from html import escape
import json
from pathlib import Path
import re
from typing import Literal
from pydantic import Field, model_validator
from business import real_projects
from business.real_projects import PublicRecord, ProjectLink, ProjectFAQ

ROOT = Path(__file__).resolve().parents[1]

class AdviceSection(PublicRecord):
    heading: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1)

class Advice(PublicRecord):
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    topic_key: str = Field(pattern=r'^[a-z0-9-]+$')
    status: Literal['draft', 'published'] = 'draft'
    approved_at: datetime | None = None
    published_at: datetime | None = None
    updated_on: date
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    author: Literal['Nigel Harvey'] = 'Nigel Harvey'
    author_note: str = Field(min_length=1)
    sections: list[AdviceSection] = Field(min_length=1)
    safety: list[str] = Field(min_length=1)
    faqs: list[ProjectFAQ] = Field(default_factory=list)
    services: list[ProjectLink] = Field(min_length=1)
    locations: list[ProjectLink] = Field(default_factory=list)
    project_slugs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    seo_title: str = Field(min_length=1, max_length=80)
    meta_description: str = Field(min_length=1, max_length=180)

    @model_validator(mode='after')
    def publication_gate(self):
        if self.status == 'published':
            if not self.approved_at or not self.published_at:
                raise ValueError('Explicit owner approval and genuine publication date required')
            if not self.approved_at.tzinfo or not self.published_at.tzinfo:
                raise ValueError('Timezone required')
            if self.approved_at > self.published_at or self.updated_on < self.published_at.date():
                raise ValueError('Dates out of order')
        elif self.approved_at or self.published_at:
            raise ValueError('Draft has no publication or approval timestamp')
        if any(not url.startswith('https://') for url in self.sources):
            raise ValueError('Sources must be HTTPS URLs')
        if len({s.heading.casefold() for s in self.sections}) != len(self.sections):
            raise ValueError('Duplicate section heading')
        return self

    @property
    def path(self):
        return '/advice/' + self.slug


def validate_catalogue(records):
    from business import public_pages

    articles = tuple(Advice.model_validate(record) for record in records)
    service_paths = {'/' + service['slug'] for service in public_pages.SERVICE_PAGES}
    service_paths.update(
        '/' + service['slug'] + '-' + area['slug']
        for service in public_pages.LOCAL_SERVICE_PAGES
        for area in public_pages.LOCATION_PAGES
    )
    location_paths = {'/plumber-' + area['slug'] for area in public_pages.LOCATION_PAGES}
    project_slugs = {project.slug for project in real_projects.PROJECTS}
    for article in articles:
        if any(link.path not in service_paths for link in article.services):
            raise ValueError('Advice services must reference public service pages')
        if any(link.path not in location_paths for link in article.locations):
            raise ValueError('Advice locations must reference public location pages')
        if any(slug not in project_slugs for slug in article.project_slugs):
            raise ValueError('Advice must reference an existing project')
    for field in ('slug', 'topic_key', 'title'):
        values = [str(getattr(a, field)).casefold().strip() for a in articles]
        if len(values) != len(set(values)):
            raise ValueError('Duplicate advice ' + field)
    def fingerprint(a):
        return re.sub(r'\W+', ' ', ' '.join([a.summary] + [p for s in a.sections for p in s.paragraphs]).casefold()).strip()
    for i, a in enumerate(articles):
        for b in articles[i+1:]:
            if SequenceMatcher(None, fingerprint(a), fingerprint(b), autojunk=False).ratio() >= .82:
                raise ValueError('Near-duplicate advice requires editorial consolidation')
    return articles

ARTICLES = validate_catalogue(json.loads((ROOT / 'business/advice_content.json').read_text(encoding='utf-8')))

def visible_articles(*, include_drafts=False):
    return tuple(a for a in ARTICLES if a.status == 'published' or include_drafts)

def sitemap_entries():
    published = visible_articles()
    return ([('/advice', max(a.updated_on for a in published).isoformat())] +
            [(a.path, a.updated_on.isoformat()) for a in published]) if published else []

def schema_graph(a, absolute_url, request=None):
    from business.public_pages import public_business_entity
    home, canonical = absolute_url('/', request), absolute_url(a.path, request)
    business = public_business_entity(home)
    business.pop('@context', None)
    article = {'@type': 'Article', '@id': canonical + '#article', 'url': canonical,
               'mainEntityOfPage': canonical, 'headline': a.title, 'description': a.summary,
               'inLanguage': 'en-GB', 'author': {'@type': 'Person', 'name': a.author, 'url': home + '#about'},
               'publisher': {'@id': home + '#business'}}
    if a.status == 'published':
        article.update(datePublished=a.published_at.isoformat(), dateModified=a.updated_on.isoformat())
    breadcrumbs = {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': name, 'item': absolute_url(path, request)}
        for i, (name, path) in enumerate([('Home', '/'), ('Plumbing advice', '/advice'), (a.title, a.path)], 1)]}
    return {'@context': 'https://schema.org', '@graph': [business, article, breadcrumbs]}

def render_article(a, *, absolute_url, request=None, staging=False):
    draft = a.status == 'draft'
    date_label = (f'Draft updated {a.updated_on:%d %B %Y}' if draft else
                  f'Published {a.published_at:%d %B %Y} · Updated {a.updated_on:%d %B %Y}')
    content = ('<div class="project-draft wrap">Draft for Nigel’s review · not published</div>' if draft else '')
    content += f'<article class="wrap advice-story"><p class="kicker">Plumbing advice</p><h1>{escape(a.title)}</h1><div class="advice-answer"><p>{escape(a.summary)}</p></div><p class="project-byline">By <a href="/#about">Nigel Harvey</a> · Nigel Harvey Plumbing<br>{escape(date_label)}</p><p>{escape(a.author_note)}</p>'
    for s in a.sections:
        content += '<section><h2>' + escape(s.heading) + '</h2>' + ''.join('<p>' + escape(p) + '</p>' for p in s.paragraphs) + '</section>'
    content += '<section class="advice-safety"><h2>Safety considerations</h2>' + ''.join('<p>' + escape(p) + '</p>' for p in a.safety) + '</section>'
    if a.faqs:
        content += '<section><h2>Homeowner questions</h2>' + ''.join('<h3>' + escape(f.question) + '</h3><p>' + escape(f.answer) + '</p>' for f in a.faqs) + '</section>'
    projects = [p for p in real_projects.visible_projects() if p.slug in a.project_slugs]
    if projects:
        content += '<section><h2>See the work behind the advice</h2><p>These are completed projects, with genuine photographs and the recorded work.</p><ul>' + ''.join(f'<li><a href="{p.path}">{escape(p.title)}</a></li>' for p in projects) + '</ul></section>'
    content += '<section><h2>Help with your shower or bathroom</h2><ul>' + ''.join(f'<li><a href="{link.path}">{escape(link.label)}</a></li>' for link in a.services + a.locations) + '</ul><p>Send a short description, your postcode and photographs of safely visible areas. Nigel can discuss whether a visit is needed.</p><a class="btn" href="/request-quote">Discuss your plumbing job</a></section>'
    if a.sources:
        content += '<section><h2>Further reading</h2><ul>' + ''.join(f'<li><a href="{escape(url, quote=True)}" rel="noopener noreferrer">{escape(url.split("/")[2])} — manufacturer guidance</a></li>' for url in a.sources) + '</ul><p>Check the current instructions for the actual products selected for your installation.</p></section>'
    content += '</article>'
    html = real_projects.page_shell(a.seo_title, a.meta_description, absolute_url(a.path, request), content,
                                   noindex=draft or staging, schema=schema_graph(a, absolute_url, request))
    return html.replace('</style>', '.advice-story{max-width:850px;padding:40px 0 64px}.advice-story h1{font-size:clamp(2rem,5vw,3rem);line-height:1.15}.advice-story h2{margin-top:35px}.advice-story p{line-height:1.75}.advice-answer{background:#eef5f7;border-left:5px solid #d7a844;padding:12px 22px}.advice-safety{border:1px solid #b4c8ce;border-radius:8px;padding:5px 22px;margin:30px 0}.advice-story a{overflow-wrap:anywhere}</style>')

def render_index(*, absolute_url, request=None, include_drafts=False, staging=False):
    content = '<section class="wrap project-index"><p class="kicker">Nigel Harvey Plumbing</p><h1>Plumbing advice</h1><p>Practical explanations to help you understand domestic plumbing problems and plan work.</p>'
    if include_drafts:
        content += '<p class="project-draft">Private owner review · drafts are not published</p>'
    for a in visible_articles(include_drafts=include_drafts):
        content += f'<article><h2><a href="{a.path}">{escape(a.title)}</a></h2><p>{escape(a.summary)}</p></article>'
    return real_projects.page_shell('Plumbing Advice | Nigel Harvey Plumbing', 'Practical domestic plumbing advice from Nigel Harvey Plumbing in Guildford.', absolute_url('/advice', request), content + '</section>', noindex=include_drafts or staging)

def add_related_advice_links(html, path):
    from bs4 import BeautifulSoup
    articles = [a for a in visible_articles() if path in [l.path for l in a.services] or
                path in ['/projects/' + slug for slug in a.project_slugs]]
    if not articles:
        return html
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        return html
    section = soup.new_tag('section', attrs={'class': 'wrap project-related'})
    h = soup.new_tag('h2'); h.string = 'Related plumbing advice'; section.append(h)
    for a in articles:
        p = soup.new_tag('p'); link = soup.new_tag('a', href=a.path); link.string = a.title; p.append(link); section.append(p)
    main.append(section)
    return str(soup)
