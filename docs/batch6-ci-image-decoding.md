# Batch 6 CI image decoding investigation

Production and main remain at `89d85b560ed83243411b0364f103d1a03473531f`.
This investigation changes only the offline project browser test and this report.
The Merrow project remains a protected draft. No application code, images,
publication settings, business records, backups or trade pricing are changed.

## Original failures

Both attempts of Actions run `37757696968` tested Batch 6 head
`142b3a015400c313a6bb62472521a13a32eddee5`:

| Attempt | Job | Time (UTC, 8 October 2026) | Exact failure |
| --- | --- | --- | --- |
| 1 | 113246195631 | 09:36:48.5301157 | `locator.evaluate: EncodingError: The source image cannot be decoded.` |
| 2 | 113248553425 | 09:42:56.5553750 | `locator.evaluate: EncodingError: The source image cannot be decoded.` |

Both stack traces point to `tests/run_project_browser.mjs:71:19` and end
with `Process completed with exit code 1.` Dependencies installed successfully;
all 240 Python tests and the complete app browser workflows passed in both jobs.

## Confirmed cause

Comparison run `37783301512`, job `113331817167`, ran the original check with
failure diagnostics and the proposed correction on the same GitHub runner.
The original test failed at 13:19:51 UTC with the same EncodingError. The
failing photograph was `stripped-back-walls`; its observed state was:

```json
{"currentSrc":"","complete":false,"naturalWidth":0,"loading":"lazy"}
```

Scrolling into view triggers lazy loading, but does not guarantee that the
browser has selected and loaded the responsive resource before `decode()` runs.
The original test asserted decoding during this transition. This is a browser
test synchronization defect, exposed by CI scheduling, rather than corrupted
WebP files or a missing decoder dependency. The corrected test passed immediately
afterwards on that same runner: desktop 1440px and mobile 390px, all nine images,
no overflow, page errors, external requests or broken images. The comparison
also passed all 240 Python tests and complete app workflows.

## Environment comparison

| Environment | Python | Node | Playwright / Chromium | Result |
| --- | --- | --- | --- | --- |
| Original CI, Ubuntu 24.04.5 | 3.12.15 | 22.23.3 | 1.56.1 / full Chromium 141.0.7390.37 | Original decode check failed twice |
| Local, Ubuntu 24.04.3 | 3.12.14 | 24.19.0 | 1.56.1 / Chromium 141 headless shell | Original and corrected checks passed |
| Previously validated Render | Version not needed for comparison | Not recorded here | 1.56.1 / full Chromium 141 | Original check passed |
| GitHub comparison runner | 3.12 | 22.23.3 | 1.56.1 / full Chromium 141 | Original failed; corrected passed |

Both original CI installations used `playwright install --with-deps chromium`.
The comparison temporarily used already-installed runner libraries and browser
installation without `--with-deps`, after diagnostic run `37782364998` stalled
downloading Ubuntu font packages and was cancelled. No missing-library launch
failure occurred; both tests used identical installed libraries and image files.
The original workflow is restored in the final review diff. Its dependency
installation, Python tests, app workflows and failure gates remain intact.

## Smallest correction

After each image scroll, wait at most five seconds for non-empty `currentSrc`,
`complete` and positive `naturalWidth`, then still require successful `decode()`.
Keep failure-state diagnostics identifying the selected resource and load state.
There are no blanket retries, skipped image checks or browser/dependency upgrades.
All existing privacy, schema, sitemap, analytics and layout assertions remain.

Local corrected desktop/mobile checks passed, including a run with 250ms added
latency on image requests. A deliberately invalid WebP response still failed
within the five-second bound, confirming that broken images cannot pass.
All 11 real-project Python regression tests, JavaScript syntax checks and
`git diff --check` passed. Temporary comparison files are removed from the
final branch. Final normal-workflow CI results are recorded in PR #6.

Recommendation: review the test-only correction in `fix/batch6-ci-image-decode`.
Do not merge or deploy it as part of this investigation. No production change
is required to correct the CI test race.
