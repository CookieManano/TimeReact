import json
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_codex_config import generate
from package_release import package


class DistributionTests(unittest.TestCase):
    def test_generated_paths_follow_install_location(self):
        with tempfile.TemporaryDirectory(prefix="timereact space ") as folder:
            root = Path(folder).resolve()
            python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            mcp_file, hook_file = generate(root, root / "output")
            server = tomllib.loads(mcp_file.read_text())["mcp_servers"]["timereact"]
            self.assertEqual(server["command"], str(python))
            self.assertEqual(server["env"]["TIMEREACT_DB"], str(root / ".timereact/state.sqlite3"))
            hooks = json.loads(hook_file.read_text())["hooks"]
            self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "Stop"})
            for groups in hooks.values():
                self.assertIn("conversation_hook.py", groups[0]["hooks"][0]["command"])

    def test_source_archive_excludes_local_and_runtime_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            root.mkdir()
            files = {
                "pyproject.toml": '[project]\nversion = "0.2.0"\n',
                "README.md": "public readme",
                "src/timereact/example.py": "public source",
                "skills/time-awareness/SKILL.md": "public skill",
                ".github/workflows/tests.yml": "public workflow",
                ".timereact/state.sqlite3": "private chat metadata",
                ".timereact/config/codex-hooks.json": "local path",
                ".env": "private environment",
                ".venv/bin/python": "runtime",
                "src/timereact/__pycache__/example.pyc": "cache",
                "src/.DS_Store": "system data",
                "examples/private.sqlite3": "database",
                "scripts/.env.secret.txt": "private environment",
            }
            for name, body in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            archive = package(root, Path(folder) / "dist")
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertEqual(len(names), 5)
                self.assertTrue(any(name.endswith("SKILL.md") for name in names))
                for name in names:
                    self.assertNotIn(b"private", bundle.read(name))
            first = archive.read_bytes()
            self.assertEqual(first, package(root, Path(folder) / "dist").read_bytes())
            self.assertTrue(archive.with_suffix(".zip.sha256").is_file())


if __name__ == "__main__":
    unittest.main()
