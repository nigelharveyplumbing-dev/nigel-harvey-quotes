"""Synthetic, loopback-only advice review server. Never uses live records."""
import os
import uvicorn
from local_browser_server import disposable_app
port=int(os.environ['STAGE6_TEST_PORT'])
stage=os.environ.get('ADVICE_TEST_STAGING')=='1'
with disposable_app(os.environ['STAGE6_TEST_USERNAME'],os.environ['STAGE6_TEST_PASSWORD'],
                    environment='staging' if stage else '',
                    public_base_url=f'http://127.0.0.1:{port}' if stage else '',
                    projects_as_drafts=False) as (module,_):
    uvicorn.run(module.app,host='127.0.0.1',port=port,log_level='warning',access_log=False)
