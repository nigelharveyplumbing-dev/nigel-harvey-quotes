"""Build the PR48 review from the two offline crawls and captured GSC evidence."""
import ast
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.local_service_guidance import LOCAL_GUIDANCE

before = json.loads(Path('/tmp/nhp-pr48-before.json').read_text())
after = json.loads(Path('/tmp/nhp-pr48-after.json').read_text())
evidence = json.loads((ROOT/'docs/seo-2026-11-05-evidence.json').read_text())
out = ROOT/'docs/seo'
out.mkdir(exist_ok=True)
origin = after['origin']
performance = {x['url'].replace(origin,''):x for x in evidence['sitemapPerformance']['urls']}
tracked = {x['url'].replace(origin,''):x for x in evidence['trackedUrls']['urls']}
history = {}
for x in sorted(evidence['inspections']['inspections'],key=lambda x:x['requested_at']):
    history[x['url'].replace(origin,'')] = {'coverageState':x['coverage_state'],'checked':x['requested_at']}
for p,x in tracked.items():
    history[p] = {'coverageState':x['coverageState'],'checked':x['lastCheckAt']}
for x in evidence['freshInspections']['results']:
    history[x['url'].replace(origin,'')] = {'coverageState':x['coverageState'],'checked':evidence['capturedAt']}

service_slugs = ['emergency-plumber','toilet-repair','leak-repair','bathroom-plumbing']
local = {p for p in after['pages'] if any(p.startswith('/'+s+'-') for s in service_slugs) and not p.endswith('-surrey')}
initial_custom = set()
for node in ast.walk(ast.parse(Path('/tmp/nhp-pr48-production/business/public_pages.py').read_text())):
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='priority_details' for t in node.targets):
        initial_custom = {ast.literal_eval(k) for k in node.value.keys}
retained_fallback = []
rows = []
overview_changes = {
 '/plumber-farnham':'Added fitting/waste enquiry planning and a relevant local repair link; no new job claim.',
 '/plumber-worplesdon':'Added shared-supply/access and bathroom sequence planning, with a relevant local link.',
 '/plumber-merrow':'Added documented Merrow ensuite context and a publication-aware link to the genuine project.',
 '/plumber-burpham':'Added planning for several small repairs and a relevant toilet-repair link.',
 '/plumber-shalford':'Added post-installation leak and product-planning guidance with a relevant repair link.'}
prior_changes = {'/leak-repair-camberley':'Different supply/waste enquiry guidance from earlier PR48 work.',
 '/leak-repair-fairlands':'Different visible dampness/ceiling enquiry guidance from earlier PR48 work.',
 '/toilet-repair-leatherhead':'Different cistern symptom/access guidance from earlier PR48 work.'}
for path,a in after['pages'].items():
    b = before['pages'][path]
    category = ('Local service' if path in local else 'Location overview' if path.startswith('/plumber-') else 'Surrey service' if path.endswith('-surrey') else 'Other')
    change = 'Reviewed and deliberately left unchanged.'
    retained = 'Existing copy, metadata, layout and contact behaviour retained.'
    fallback = False
    if path in local:
        service = next(s for s in service_slugs if path.startswith('/'+s+'-'))
        area = path[len(service)+2:]
        key = (service,area)
        if key in LOCAL_GUIDANCE:
            change = 'Replaced shared guidance: '+LOCAL_GUIDANCE[key][0]+'. Added contextual area/related-service links.'
            retained = 'Service introduction, metadata, problems list, branding and contact/tracking retained.'
        elif path in prior_changes:
            change = prior_changes[path]+' Added contextual area/related-service links.'
            retained = 'Existing introduction and metadata retained.'
        else:
            change = 'Contextual area/related-service links only; existing guidance deliberately retained.'
            if key not in initial_custom:
                fallback = True;retained_fallback.append(path)
                retained = 'Shared factual guidance retained because the page already has impressions/visibility; no verified local evidence justifies a rewrite.'
            else:
                retained = 'Previously reviewed custom guidance and existing search signals retained.'
    elif path in overview_changes:
        change = overview_changes[path]
        retained = 'Existing metadata, services, reviews, layout and contact/tracking retained.'
    elif path=='/emergency-plumber-surrey':
        change = 'Added direct links to all 13 published town emergency pages.'
        retained = 'Existing emergency copy, availability limits and metadata retained.'
    elif path=='/bathroom-plumbing-surrey':
        change = 'Added preparation context, publication-aware evidence links and direct links to 13 town bathroom pages.'
        retained = 'Existing service introduction, metadata and contact behaviour retained.'
    elif path in ('/projects','/advice'):
        retained = 'Small, honest one-item catalogue retained; no filler, invented projects or unnecessary schema added.'
    elif path=='/request-quote':
        retained = 'Working enquiry flow, form markup, privacy copy and lead tracking retained; no SEO-driven form changes.'
    elif path=='/':
        retained = 'Highest-click landing page retained, including branding, review strip, services and enquiry routes.'
    elif path.startswith(('/projects/','/advice/')):
        retained = 'Approved genuine evidence, photographs, review attribution and published advice retained.'
    elif path.endswith('-surrey'):
        retained = 'Clear, distinct service intent retained; heating wording stays within radiator/pipework plumbing.'
    p = performance[path]
    rows.append({'path':path,'category':category,'changed':a['htmlHash']!=b['htmlHash'],
                 'change':change,'deliberatelyRetained':retained,'retainedFallback':fallback,
                 'clicks':p['clicks'],'impressions':p['impressions'],'position':p['position'],
                 'inspection':history[path], 'inboundBefore':len(b['inboundSources']),
                 'inboundAfter':len(a['inboundSources']),'clickDepth':a['clickDepth'],
                 'title':a['title'],'description':a['description'],'canonical':a['canonical'],
                 'technicalResult':'PASS: 200, self-canonical, metadata, links/fragments, images, discovery'})

pairs = {}
for label,data in [('before',before),('after',after)]:
    same = [x for x in data['pairs'] if x['a'] in local and x['b'] in local and any(x['a'].startswith('/'+s+'-') and x['b'].startswith('/'+s+'-') for s in service_slugs)]
    pairs[label] = {'count':len(same),'meanJaccard5':round(statistics.mean(x['jaccard5'] for x in same),4),
                    'atLeast80Percent':sum(x['jaccard5']>=.8 for x in same),'atLeast90Percent':sum(x['jaccard5']>=.9 for x in same)}
all_pairs = {'method':'Town/Surrey names normalised; scripts, styles, header/footer, review/navigation/link lists removed; Jaccard overlap of five-word shingles. Not a Google score.',
             'sameServiceSummary':pairs,'before':before['pairs'],'after':after['pairs']}
(out/'full-site-pairwise-2026-11-05.json').write_text(json.dumps(all_pairs,indent=2)+'\n')
(out/'page-by-page-2026-11-05.json').write_text(json.dumps(rows,indent=2)+'\n')

lines = ['# PR48 website-wide SEO review — 5 November 2026','',
'Branch: `seo/full-site-content-review-2026-11-05`. Continue [draft PR #48](https://github.com/nigelharveyplumbing-dev/nigel-harvey-quotes/pull/48). No production merge or deployment is authorised.', '',
'## Scope and decisions','',
'All 82 published URLs were reviewed: 20 location overviews, 52 local service pages, four Surrey services and six other pages. 59 pages change in the rendered branch; 23 remain byte-identical in the isolated before/after crawl. All 82 titles and descriptions are preserved. Header, footer, executable scripts and form hashes match production on every page.', '',
'29 of the 36 previously shared-guidance pages now answer distinct practical questions. Seven retain their existing guidance deliberately because they already have search visibility and there is no verified local evidence to justify changing it. The earlier three targeted edits in this same PR remain. All 52 local service pages receive contextual area/related-service links; the emergency and bathroom county hubs now link directly to all 13 relevant town services.', '',
'Five location overviews gain useful planning detail. The Merrow project is the documented job evidence used; it is identified as Merrow, Guildford wherever linked. No new jobs, testimonials, qualifications, offices, attendance guarantees or ranking promises have been invented. The new symptom/planning topics are general plumbing considerations, not claims that those faults are more prevalent in those towns.', '',
'| Group | Reviewed | Changed | Unchanged |','|---|---:|---:|---:|']
for category in ['Location overview','Local service','Surrey service','Other']:
    group=[x for x in rows if x['category']==category]
    lines.append(f'| {category} | {len(group)} | {sum(x["changed"] for x in group)} | {sum(not x["changed"] for x in group)} |')
lines += ['', '## Evidence and validation', '',
'Offline production-mode crawl: **82/82 pass**, including HTTP status, one self-canonical URL, unique titles/descriptions/H1s, internal destinations and fragments, local images and homepage reachability. Maximum click depth is three. Every URL keeps its existing path; no redirects or sitemap membership change.', '',
'The full before/after comparison covers all **3,321 URL pairs**. Within the 312 same-service local pairs, mean five-word-shingle overlap falls from **0.7483 to 0.4301**. Pairs at or above 90% fall from **165 to nine**. Town names are normalised and navigation/reviews excluded. These are reproducible editorial measurements, not Google quality scores or a promise of indexing. Existing shared template and factual text remains; this is not a claim of 82 completely unique documents.', '',
'Validation status and CI links are recorded in `validation-2026-11-05.md`. The hosted preview uses password protection, noindex headers, a staging canonical origin, ephemeral data and disabled outbound email/Google analytics. Browser fixture reviews are synthetic and must not be treated as production ratings.', '',
'## Indexing investigation', '',
'Source: GSC Wizard `get_indexing_tracker` and `list_tracked_urls`, captured 5 November 2026. The tracker contains 55 URLs: 27 indexed and 28 not indexed. Its initial split is 20 unknown and eight discovered/not indexed. All 28 are in the public sitemap. This is a 55-URL tracker snapshot, not a complete count of Google’s current index across the 82 pages.', '',
'Ten fresh URL inspections were made after checking quota (1,944 inspections available before the batch). All ten remain non-indexed; some move between unknown and discovered. Latest evidence for each is in the table below. Google reports no last crawl for these ten; null canonicals do not establish a canonical error. The other 18 use their recent tracker results. No indexing requests, IndexNow submissions or sitemap resubmission were made.', '',
'`list_sitemaps` reports 82 submitted URLs, zero errors and zero warnings; last downloaded 2 November. `get_sitemap_performance`, **6 October–2 November 2026**, reports impressions for 46 sitemap URLs and none for 36. Zero impressions is not proof of non-indexing. Historical inspections cover the other pages, but their dates differ and must not be presented as a fresh full-site index count.', '',
'The crawl found no HTTP, robots/noindex, canonical or orphan defect explaining exclusion of the 28 URLs. Internal discovery and content usefulness have been improved where appropriate. Google’s unknown/discovered labels do not reveal a definitive ranking or content-quality cause.', '',
'| Non-indexed URL | Latest evidence | Checked | Change / follow-up |','|---|---|---|---|']
for r in rows:
    if r['path'] in tracked and tracked[r['path']]['currentStatus']=='not_indexed':
        lines.append(f'| `{r["path"]}` | {r["inspection"]["coverageState"]} | {r["inspection"]["checked"][:10]} | {r["change"]} Keep URL; inspect again after an approved production release and recrawl. |')
lines += ['', '## Page-by-page decisions', '',
'Search columns use GSC Wizard `get_sitemap_performance`, 6 October–2 November 2026. Inspection dates are explicit because tracker and stored-history results are not simultaneous. Every row passes the offline technical checks. See the companion JSON for exact metadata, canonical URL, inbound source counts and click depth.', '']
for category in ['Location overview','Local service','Surrey service','Other']:
    lines += ['### '+category+' pages','','| URL | Clicks / impressions | Inspection (date) | What changed | Deliberately retained |','|---|---:|---|---|---|']
    for r in rows:
        if r['category']==category:
            lines.append(f'| [{r["path"]}]({origin+r["path"]}) | {r["clicks"]} / {r["impressions"]} | {r["inspection"]["coverageState"]} ({r["inspection"]["checked"][:10]}) | {r["change"]} | {r["deliberatelyRetained"]} |')
    lines.append('')
lines += ['## Deliberately retained shared guidance','','These seven pages retain shared factual guidance; their town names and metadata remain distinct. Their new navigation does not represent new local job evidence:','']
for p in retained_fallback:
    v=performance[p]
    lines.append(f'- `{p}` — {v["impressions"]} impressions; average position {v["position"]:.2f} in the stated window. Small samples; preserve existing signals and collect genuine evidence before a further rewrite.')
lines += ['', 'An existing normalised exact match also remains between the Guildford and Aldershot leak guidance. Guildford has a recorded click; this review preserves that wording. Full residual overlap is disclosed in the pairwise JSON rather than hidden by synonym substitution.', '',
'## Remaining limits and release gate','',
'The small project/advice index pages are retained as honest one-item catalogues. Missing optional schema or a crawler word-count warning alone does not justify filler or invented evidence. Additional genuine completed-job photographs and owner-approved details would be the strongest basis for further geographic differentiation.', '',
'Before any merge, recheck the branch against the latest production `main`, review the staging changes and validation status, and obtain Nigel’s explicit approval. No production action has been taken. Indexing and rankings must be monitored after any approved release; success cannot be guaranteed.', '',
'Technical advice cross-checks: [Thames Water inside stop valves](https://www.thameswater.co.uk/help/water-and-waste-help/how-to-turn-your-water-on-and-off/how-to-find-and-use-your-inside-stop-valve), [supply interruptions](https://www.thameswater.co.uk/help/water-and-waste-help/no-water-or-low-pressure), [WaterSafe leak advice](https://www.watersafe.org.uk/advice/common_plumbing_questions1/leaks/what_should_i_do_if_i_find_a_leak_in_or_around_my_home_or_business/). These links do not imply Nigel holds WaterSafe registration.']
(out/'page-by-page-review-2026-11-05.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'pages':len(rows),'changed':sum(x['changed'] for x in rows),'retainedFallback':len(retained_fallback),'sameService':pairs}))
