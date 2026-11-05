"""All published pages under the real staging controls, with synthetic storage."""
import os
import uvicorn
from local_browser_server import disposable_app
from test_public_review_badges import REVIEW_HTML

port = int(os.environ["STAGE6_TEST_PORT"])
with disposable_app(os.environ["STAGE6_TEST_USERNAME"], os.environ["STAGE6_TEST_PASSWORD"],
                    public_base_url=f"http://127.0.0.1:{port}", environment="staging",
                    projects_as_drafts=False, advice_as_drafts=False) as (module, _):
    module._google_reviews_html = lambda: REVIEW_HTML
    uvicorn.run(module.app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
