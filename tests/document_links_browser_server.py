"""Secure-link UI test server; copied storage, fictional data, no outbound I/O."""

import os
import uvicorn

from local_browser_server import disposable_app


if __name__ == "__main__":
    port = int(os.environ["STAGE6_TEST_PORT"])
    policy = os.environ["DOCUMENT_LINK_TEST_POLICY"]
    if not 1024 <= port <= 65535 or policy not in {"customer", "staging"}:
        raise ValueError("Invalid isolated browser-test configuration")
    with disposable_app(
        os.environ["STAGE6_TEST_USERNAME"], os.environ["STAGE6_TEST_PASSWORD"],
        public_base_url=f"http://127.0.0.1:{port}",
        environment="staging" if policy == "staging" else "",
        document_link_mode="secure",
    ) as (module, _):
        uvicorn.run(module.app, host="127.0.0.1", port=port,
                    log_level="warning", access_log=False)
