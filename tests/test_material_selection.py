"""Keep the browser material-choice regression in the normal test run."""

import shutil
import subprocess
import unittest
from pathlib import Path


class MaterialSelectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is unavailable in this environment")
    def test_site_survey_material_choice_and_override(self):
        script = Path(__file__).with_name("test_material_selection.cjs")
        result = subprocess.run(["node", str(script)], capture_output=True, text=True,
                                timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Material selection regression: PASS", result.stdout)
