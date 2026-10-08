# Private Plumbing Advice architecture

Stage 2 is an owner-review draft only. The status in `business/advice_content.json`
remains `draft`; deploy, publication and Stage 3 need separate approval.

## Content model

| Field | Use |
| --- | --- |
| `slug`, `topic_key` | One stable topic/URL; no town variants |
| `title`, `summary` | Visible title and direct answer |
| `sections` | Problem, explanation, diagnosis considerations and solutions |
| `safety`, `faqs` | Homeowner boundaries and useful questions |
| `author`, `author_note` | Nigel's verified role and relevant experience |
| `services`, `locations` | Existing public page references; private paths rejected |
| `project_slugs` | Known real projects; only published projects rendered |
| `sources` | Current HTTPS manufacturer/technical references |
| `seo_title`, `meta_description` | Page and social metadata |
| `updated_on` | Visible draft update or genuine public modification date |
| `status`, `approved_at`, `published_at` | Explicit manual review/publication gate |

Canonical is derived from `absolute_url`, which already validates the public
base URL. Draft Article JSON-LD omits publication and modification dates.
Unknown fields are forbidden. Duplicate slug/title/topic and narrative similarity
of at least 82% are rejected; human semantic/topic review is still required.

## Privacy and discovery

The index and article handlers independently check owner Basic Auth. Anonymous
access is 404 while all advice is drafted, including incorrect credentials and
preview query strings. Owner responses have HTTP/HTML noindex,nofollow,
private,no-store and disabled analytics sending. No draft is in sitemap,
public navigation, service/project links or publicly listed advice.
The existing staging middleware protects the entire stage environment. It is
not altered by this system. Local tests of that middleware are regression
checks, not a remote staging deployment.

## Genuine photos and projects

The first guide links the approved nine-photo Merrow case study instead of
embedding its photographs under a new reuse scope. No generated photos,
customer originals, full addresses, invoices or private job records are used.
For a later article, first obtain permission for that specific photo placement,
then review stripped derivatives, captions and alt text. Prefer reusing the
existing reviewed project image pipeline; do not add arbitrary upload paths or
copy customer data into advice records. Linking to a published project is the
current reusable evidence relationship.

## Publication boundary

No endpoint publishes or modifies records. An eventual publication commit must
refer to Nigel's approval of the exact content revision and photo scope, set
real timezone-aware approval/publication timestamps, and validate date order.
The code gate checks record consistency; it does not verify the approver's
identity or bind an approval to a content hash. Owner/code review must ensure
an edited approved revision returns to draft.
After a separately authorised release, published articles alone can enter
index/sitemap and selected service/project backlinks. A footer Advice link is a
later owner-reviewed discovery change; no empty hub is exposed now.

## Job-to-content process — no integration implemented

Completed job -> public-safe facts/photos -> scoped customer permission -> topic
and duplicate review -> private draft -> Nigel factual/editorial review -> exact
revision approval -> separate publication approval -> discovery checks ->
Search Console and enquiry monitoring. Completing or invoicing a job never
publishes. No DB migration, private job API or automatic generator is added.

## Local validation

Use `tests/run_stage6_local.py` with `STAGE6_TEST_PYTHON` and
`STAGE6_CHROMIUM_EXECUTABLE` pointing to the known working Python and Chromium
headless shell. Run `tests/test_material_selection.cjs` and
`tests/test_trade_comparison.cjs`. Optional `ADVICE_EVIDENCE_DIR` writes private
local desktop/mobile previews and browser diagnostics. Captures use synthetic
stores and blocked outbound requests. Do not place review screenshots or
standalone draft HTML under publicly served static paths.
