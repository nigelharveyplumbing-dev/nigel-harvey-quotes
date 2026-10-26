# Company footer disclosure review — 26 October 2026

Nigel approved publication and production deployment on 26 October 2026, confirming the postal address is **125 Bushy Hill Drive**, with a single house number. The official-register discrepancy is recorded below; no Companies House filing is changed by this release.

## Verified official details

| Particular | Current official record |
| --- | --- |
| Registered name | NIGEL HARVEY LTD |
| Company number | 09507904 |
| Status / type | Active / private limited company |
| Jurisdiction | England and Wales |
| Registered office | 125 125 Bushy Hill Drive, Guildford, Surrey, England, GU1 2UG |

Verification used Companies House, not old application settings or documents:

- [Current company overview](https://find-and-update.company-information.service.gov.uk/company/09507904), also fetched directly on 26 October 2026 to avoid relying on a cached search extract.
- [Current filing history](https://find-and-update.company-information.service.gov.uk/company/09507904/filing-history): the most recent address-change filing is AD01, filed 12 March 2026. The later filings listed on 26 October contain no subsequent AD01.
- [AD01 document](https://find-and-update.company-information.service.gov.uk/company/09507904/filing-history/MzUwOTgzNTYyNGFkaXF6a2N4/document?download=0&format=pdf), downloaded directly and visually inspected: the new address explicitly begins **125 125 BUSHY HILL DRIVE**. The duplicate number is in both the filing and the current register. The owner subsequently confirmed the duplicated house number is an error. The published footer uses the owner-confirmed postal form with a single 125; the official register still contains the duplicate as verified above.
- [Incorporation filing](https://find-and-update.company-information.service.gov.uk/company/09507904/filing-history/MzExOTgxNTgwOGFkaXF6a2N4/document?download=0&format=pdf), certificate page 1 visually inspected: company 09507904 was incorporated on 25 March 2015 in England and Wales under its former name. The current overview and 16 September 2024 filing establish the change to Nigel Harvey Ltd.

These checks establish what is filed, not independent postal validation or whether the premises are residential.

## Public website comparison and minimal correction

The live homepage was fetched directly on 26 October 2026. Its footer matches `templates/public_footer.html` on main at `59b786294ccfc48bb3e4bafb0f7b8a212a4c8942`: Nigel Harvey Plumbing, Nigel Harvey Ltd and Guildford, Surrey are present; the registered number, registered office and jurisdiction are absent.

[GOV.UK website disclosure guidance](https://www.gov.uk/running-a-limited-company/signs-stationery-and-promotional-material) requires these particulars and the limited-company name.

The shared footer keeps its existing brand, company name, Guildford service-area line, project link, contact routes, analytics control and mobile contact bar. It adds only this paragraph:

> Registered in England and Wales · Company no. 09507904  
> Registered office: 125 Bushy Hill Drive, Guildford, Surrey, England, GU1 2UG

The registered office is labelled separately from the service area. No map, directions, visit invitation, structured-data address, app configuration or customer data changes are included.

## Privacy and release decision

The address may be residential; this review does not establish who lives there. A footer would expose it on every public page and make it easier for customers and search engines to encounter, beyond its existing presence on Companies House. The development repository itself is public, so a pushed branch/diff would also expose the verified public-register address. The branch was initially kept local for this review. Nigel has now explicitly authorised publishing the corrected address and deploying the footer.

The owner has reviewed the address and requested deployment using the single house number. Correcting the duplicate in the Companies House record remains a separate administrative action. If a different office is preferred, arrange an appropriate authorised address and register the change with Companies House, then re-verify and revise this proposal. Do not substitute an accountant's address, an old address, or just “Guildford, Surrey” without the corresponding official change.

Relevant official guidance: [registered-office privacy and service-provider options](https://www.gov.uk/limited-company-formation/company-address), [when company changes take effect](https://www.gov.uk/file-changes-to-a-company-with-companies-house), and [current address-removal guidance](https://www.gov.uk/guidance/removing-your-home-address-from-the-companies-house-register). A current registered office must be changed before applying to remove a home address from the register.

## Validation

The full-site integrity test now checks the exact disclosure and preserved branding on all 82 sitemap pages. Historical HTML and template byte locks reverse only this exact addition; their other protections remain in place.

- Full isolated Python suite: **310 tests passed**, including the complete sitemap crawl, HTML snapshots, private-app access controls and browser-harness fault/cleanup checks.
- Full existing local browser regression runner: **passed** (exit 0), including the app, draft and published project/advice workflows, isolated staging controls, South West London pages and mixed-catalogue Batch 8 proposals. The South West London workflow checked 18 layouts.
- Additional Chromium footer review: **21 layouts passed**, covering the home, enquiry, preview, location, service, project and advice pages at 1440px, 390px and 320px. Disclosure visible, no horizontal overflow, no page errors and no external requests. Desktop and phone footer screenshots were visually inspected.
- `git diff --check`: passed.

The local Chromium environment uses the Playwright 1.56.1 headless shell. The normal Chrome binary cannot start here because this environment denies its process-singleton socket. The fault/cleanup checks passed after selecting the supported headless shell; no application change was made to work around this environment issue.

The existing regression command was `python -B tests/run_stage6_local.py`, with `STAGE6_TEST_PYTHON`, `STAGE6_CHROMIUM_EXECUTABLE` and `CODEX_PRIMARY_RUNTIME_NODE_MODULES` set to the isolated Python environment, installed headless-shell executable and Playwright installation. All integrations were blocked by the existing disposable test harness. The corrected branch will also run the existing GitHub CI before merging.

Production merge and deployment of this correction are authorised by Nigel's follow-up request. No customer data, Companies House filings, email, Google settings, or hosting configuration changes are included.
