# Growth Batch 2 measurement

GA4 web stream: `G-Q9Z2WWNF6F`. The public measurement ID is not a secret. The
customer-facing pages show an optional analytics choice. Until accepted, no
Google tag is loaded and no events are queued. The footer's Analytics settings
control reopens the choice. The staff application at `/app` has no analytics
tag.

The existing isolated staging environment (`APP_ENVIRONMENT=staging`) keeps
the consent interface and queues accepted events locally for testing, but
never loads Google's script or sends hits to the live property. It must stay
that way when reviewing this branch. Do not copy a production credential or
data into staging.

| Event | When it fires |
| --- | --- |
| `generate_lead` | Once after the quote form receives a successful API response. A button click or failed request does not count. |
| `click_phone` | A customer-facing `tel:` link is clicked. |
| `click_whatsapp` | A customer-facing `wa.me` link is clicked. |
| `click_get_quote` | A link to `/request-quote` is clicked. |

Only `page_path` and the public measurement ID accompany custom events;
form fields, phone numbers and customer information are not included. GA4
automatically collects `page_view` after consent on a live environment.
Enhanced measurement may separately emit `form_submit`; configure
`generate_lead`, not `form_submit`, as the successful enquiry key event in
GA4 after production deployment is approved. Review the event stream and
consent behavior in GA4 then, without submitting artificial live leads.

Search Console's supplied three-month figures are the baseline for future
comparisons: homepage 2,004 impressions/25 clicks; Guildford 1,172/0;
Aldershot 729/0; Camberley 676/1. Ranking and click changes need time after
Google recrawls the approved pages and cannot be inferred from staging.
