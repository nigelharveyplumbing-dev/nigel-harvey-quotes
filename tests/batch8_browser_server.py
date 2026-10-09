"""Batch 8 mixed published/draft review server; synthetic loopback only."""
import os
from pathlib import Path
import uvicorn
from local_browser_server import disposable_app

port=int(os.environ['STAGE6_TEST_PORT'])
os.environ.setdefault('PLUMBING_ADVICE_PRIVATE_DRAFTS', str(Path(__file__).parent/'fixtures/private_advice_synthetic.json'))
with disposable_app(os.environ['STAGE6_TEST_USERNAME'],os.environ['STAGE6_TEST_PASSWORD'],
                    projects_as_drafts=False,advice_as_drafts=False) as (module,_):
    uvicorn.run(module.app,host='127.0.0.1',port=port,log_level='warning',access_log=False)
