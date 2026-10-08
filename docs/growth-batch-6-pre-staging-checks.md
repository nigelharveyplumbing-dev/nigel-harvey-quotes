# Growth Batch 6 — pre-staging checks

6 October 2026. No staging, merge, deployment or production notification.

## Original photograph exposure

The initial Batch 6 head exposed nine JPEGs under `docs/project-sources/merrow-ensuite/`. The source filenames were:

- `IMG_62220E2A-FCB3-49BF-B87C-71D90B031A95.jpeg`
- `IMG_090B8A9A-E070-4FAD-AA0E-D82090D343B8.jpeg`
- `IMG_91A5E28F-73A1-4757-BEAD-AAF15544B351.jpeg`
- `IMG_28F4FED5-CED2-446C-976E-EE810ED4BBA5(1).jpeg`
- `IMG_B8DAE440-64B5-418D-800F-BE0EAF4F7138(1).jpeg`
- `IMG_83B0B113-EAA7-4BFF-A04C-747ED0E02DE6(1).jpeg`
- `IMG_2394.jpeg`
- `IMG_2395.jpeg`
- `IMG_2393.jpeg`

An anonymous HTTP download of an original returned 200 and matched its SHA-256. All nine originals were verified byte-exact against copies outside Git; all nine original uploaded items remain in Nigel's private owner files. None is required for build or runtime. They have been removed from the Batch 6 tree and its single-commit history has been rewritten directly on the unchanged main baseline, rather than retaining the exposing commit as a parent.

The public project image directory now contains only the 18 reviewed WebP derivatives. The unchanged rendered HTML preview embeds only derivatives and screenshots contain rendered page evidence. No original-byte dependency remains in tests or production code. All derivatives were checked through Pillow and RIFF chunk inspection: no EXIF, XMP or ICC metadata. Original provenance hashes and derivative hashes/dimensions/byte counts remain in `docs/project-images/merrow-ensuite/manifest.json`; source filenames, private storage paths and file/account IDs are excluded. The workflow now requires all future originals to stay private, and ignore rules and regression checks guard against reintroduction.

History rewriting removes the old commit from the branch ancestry, but does not provide server-side object deletion. [GitHub documents](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) that old commit links/caches may remain after a force push and describes GitHub Support follow-up. No repository visibility change, main rewrite, unrelated ref deletion or support message was performed. Old-object accessibility is checked and reported separately after the branch replacement; complete server-side erasure must not be claimed without that evidence.

## Sitemap baseline

Main `8ab4f6494de3823b4150fc611e698a91295faa56` has exactly **72** unique sitemap URLs; every URL returned **200** in an isolated copy of that exact commit. Composition:

- Homepage and request-quote: 2.
- Area overview pages: 14.
- Surrey service overview pages: 4.
- Emergency / toilet / leak / bathroom local families: 4 × 13 = 52.

Growth Batch 5 `7348ed293f6ccc8f6580ba34b3cd46095d3216b7` had 85. Its exact URL-set difference from current main is **13 blocked-drain pages only**. Main ancestor `c4c36c0eeed939e944f5952fb139f2534376b1a1` intentionally retired that unsupported service family. All 13 old paths return a direct 301 to their matching existing plumber-area overview, which returns 200. No supported public page was unintentionally lost and no obsolete page was restored.

Batch 6 draft sitemap equals main exactly: 72 URLs, no additions/removals. A simulated approved published record adds only `/projects` and `/projects/ensuite-renovation-merrow-guildford`, producing 74. Canonical and lastmod handling remain as designed. `docs/sitemap-baseline-reconciliation.json` records every current-main path/status and all 13 redirects.

## Validation

Full relevant checks after the fixes: 180 Python tests, both Node suites, analytics workflow, existing isolated Chromium app workflows, and desktop/mobile project Chromium workflows. Tests require the exact main sitemap URL set, preserve retired redirects, forbid source originals in public project directories and ensure embedded preview images are cleared derivatives. Browser rendering remains unchanged.

Verification after the first clean rewrite: a fresh public single-branch clone contained zero original blobs or paths in its reachable history, exactly one Batch 6 commit directly on current main, and the same tested tree. All nine original-file requests against the clean head returned 404. All nine requests against the old commit `3679d74110c9b430ad63f13c98ef281042b9eaf6` returned 200 and matched the original SHA-256 hashes. The only changed remote reference was Batch 6; main and PR #4 were unchanged. A later documentation-only amendment retains the same clean ancestry and assets.

**Privacy closure remains blocked by GitHub-side retention; do not proceed to staging yet.** The code and sitemap checks pass, but this branch rewrite cannot erase GitHub's retained old objects. Do not imply complete source-photo removal from GitHub until the old-object checks stop succeeding. Support must assess the removal request; its policy does not guarantee removal of every kind of data.

## GitHub Support request draft — not sent

Repository: `nigelharveyplumbing-dev/nigel-harvey-quotes`.

Original full-resolution customer/job photographs were mistakenly committed to the public, unmerged branch `growth/website-batch-6-real-projects`. These source photographs were not intended for public repository distribution and are not runtime/build assets. We have rewritten only that branch directly on the unchanged main baseline, keeping only the cleared optimised derivatives. No merge or deployment occurred. No PR was created for this branch and no other remote reference was changed.

First exposing commit: `3679d74110c9b430ad63f13c98ef281042b9eaf6`. The nine affected files are listed above, all under `docs/project-sources/merrow-ensuite/`. Anonymous raw downloads through that old commit still return 200 and match the original source hashes; requests against the rewritten clean head return 404. Please assess removal of the retained original-photo objects and cached views associated with this old commit. Preserve main, PR #4 and all unrelated branches. No Git LFS objects were used. Please advise on any additional cleanup needed to eliminate the remaining public access.

Submit through the [GitHub Support portal](https://support.github.com/). This is a prepared draft only; no third party has been contacted. Keep staging on hold until the privacy issue is resolved or Nigel explicitly decides how to handle the remaining exposure.
