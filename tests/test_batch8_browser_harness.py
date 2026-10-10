"""Exercise timeout and cleanup failures, not just successful page rendering."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Batch8BrowserHarnessTests(unittest.TestCase):
    def test_deadlines_privacy_and_forced_child_cleanup(self):
        result = subprocess.run(['node', str(ROOT/'tests/test_batch8_browser_support.mjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('forced child cleanup: PASS', result.stdout)

    def test_pending_image_decode_fails_and_reaps_browser_and_server(self):
        with tempfile.TemporaryDirectory(prefix='batch8-fault-') as folder:
            result = subprocess.run(['node', str(ROOT/'tests/run_batch8_browser.mjs'),
                                     '--probe', 'home', 'desktop', '--fault-image-decode'],
                                    cwd=ROOT, env={**os.environ, 'BATCH8_EVIDENCE_DIR':folder},
                                    capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 1)
            data = json.loads((Path(folder)/'batch8-browser-validation.json').read_text())
            self.assertEqual(data['failure'], {'phase':'desktop/home/image-0/decode',
                                               'errorType':'BrowserOperationTimeout'})
            self.assertTrue(data['browserProcessTerminated'])
            self.assertTrue(data['serverCleanup']['terminated'])
            self.assertNotIn('"result": "PASS"', result.stdout)
            self.assertEqual(data['externalRequests'], [])


if __name__ == '__main__':
    unittest.main()
