"""Disposable local migrated server; credentials and DB exist only for this test."""
import os
from local_browser_server import disposable_app
import uvicorn
port=int(os.environ['STAGE6_TEST_PORT'])
assert 1024<=port<=65535
with disposable_app(os.environ['STAGE6_TEST_USERNAME'],os.environ['STAGE6_TEST_PASSWORD'],environment='staging',public_base_url=f'http://127.0.0.1:{port}',projects_as_drafts=False,advice_as_drafts=False) as (m,root):
    from business.schema_migrations import migrate
    migrate(root/'quotes.db',apply=True)
    uvicorn.run(m.app,host='127.0.0.1',port=port,log_level='error',access_log=False)
