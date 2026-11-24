"""Offline checks for the reviewed root-script archival layout."""
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = json.loads((ROOT / "scripts/inventory_20261124.json").read_text(encoding="utf-8"))
ENTRIES = INVENTORY["entries"]
SCRIPT_NAME = re.compile(r"[A-Za-z0-9_]+\.sh")


class ScriptLayoutTests(unittest.TestCase):
    def test_inventory_has_unique_contained_paths(self):
        self.assertEqual(len(ENTRIES), len({e["original_path"] for e in ENTRIES}))
        self.assertEqual(len(ENTRIES), len({e["path"] for e in ENTRIES}))
        for entry in ENTRIES:
            with self.subTest(script=entry["original_path"]):
                path = (ROOT / entry["path"]).resolve()
                self.assertTrue(path.is_relative_to(ROOT))
                self.assertTrue(path.is_file())
                self.assertEqual(path.name, entry["original_path"])

    def test_archives_are_unchanged_and_not_at_root(self):
        for entry in ENTRIES:
            if entry["retained"]:
                self.assertEqual(entry["path"], entry["original_path"])
                continue
            with self.subTest(script=entry["original_path"]):
                self.assertTrue(entry["path"].startswith("scripts/archive/"))
                self.assertFalse((ROOT / entry["original_path"]).exists())
                data = (ROOT / entry["path"]).read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256_lf"])

    def test_retained_shell_dependencies_are_present(self):
        reviewed_names = {e["original_path"] for e in ENTRIES}
        for entry in ENTRIES:
            if not entry["retained"]:
                continue
            path = ROOT / entry["path"]
            references = set(SCRIPT_NAME.findall(path.read_text(encoding="utf-8")))
            for name in references & reviewed_names:
                with self.subTest(caller=entry["path"], dependency=name):
                    self.assertTrue((ROOT / name).is_file())

    def test_repository_code_does_not_depend_on_archived_root_scripts(self):
        archived = {e["original_path"] for e in ENTRIES if not e["retained"]}
        suffixes = {".py", ".cpp", ".cc", ".c", ".h", ".hpp", ".sh", ".json"}
        for folder in ("tools", "tests", "src", "native", "candidates", "config"):
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or path.suffix not in suffixes:
                    continue
                text = path.read_text(encoding="utf-8")
                references = set(SCRIPT_NAME.findall(text))
                with self.subTest(caller=str(path.relative_to(ROOT))):
                    self.assertFalse(references & archived, sorted(references & archived))


if __name__ == "__main__":
    unittest.main()
