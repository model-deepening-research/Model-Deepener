"""End-to-end Windows test for the real application batch warning."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "Windows desktop integration")
class RealApplicationBatchTests(unittest.TestCase):
    """Test real application batch."""
    def test_real_application_batch_warning_accepts_clicks(self):
        """Check real application batch warning accepts clicks."""
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(root), str(root / "src")))
        env["BATCH_SMOKE_PLANTUML"] = "1"
        run = subprocess.run([sys.executable, "-u", "src/testing/gui_batch_smoke.py"], cwd=root,
                             env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("bad window path", run.stdout + run.stderr)
        line = next((line for line in run.stdout.splitlines() if line.startswith("BATCH_SMOKE ")), None)
        self.assertIsNotNone(line, run.stdout + run.stderr)
        result = json.loads(line[len("BATCH_SMOKE "):])
        self.assertEqual(result.get("callback_errors"), [])
        self.assertEqual(result.get("selected"), 60)
        self.assertTrue(result.get("progress_was_shown"), result)
        self.assertFalse(result.get("handoff_progress_mapped"), result)
        self.assertFalse(result.get("handoff_progress_grab"), result)
        self.assertFalse(result.get("progress_mapped"), result)
        self.assertFalse(result.get("progress_grab"), result)
        self.assertTrue(result.get("mapped"), result)
        self.assertTrue(result.get("grab_is_dialog"), result)
        self.assertTrue(result.get("focus_is_dialog"), result)
        x, y, width, height = result["geometry"]
        root_x, root_y, root_width, root_height = result["root_geometry"]
        self.assertLess(abs((x + width / 2) - (root_x + root_width / 2)), 60)
        self.assertLess(abs((y + height / 2) - (root_y + root_height / 2)), 60)
        self.assertEqual(result.get("show_result"), "Hide Details")
        self.assertTrue(result.get("closed"), result)
        self.assertEqual(result.get("final_grab"), "None")
        self.assertEqual(result.get("overlay_count"), 0)


if __name__ == "__main__":
    unittest.main()
