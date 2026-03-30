import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from source import profile_store


class ProfileStoreTests(unittest.TestCase):
    def test_load_master_profile_uses_real_profile_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            real_path = profile_dir / "master_profile.json"
            example_path = profile_dir / "master_profile.example.json"
            real_path.write_text(json.dumps({"basics": {"name": "Real"}}), encoding="utf-8")
            example_path.write_text(json.dumps({"basics": {"name": "Example"}}), encoding="utf-8")

            with patch.object(profile_store, "PROFILE_DIR", profile_dir), patch.object(
                profile_store, "MASTER_PROFILE_PATH", real_path
            ), patch.object(profile_store, "MASTER_PROFILE_EXAMPLE_PATH", example_path):
                payload = profile_store.load_master_profile()

        self.assertEqual(payload["basics"]["name"], "Real")

    def test_load_master_profile_falls_back_to_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            real_path = profile_dir / "master_profile.json"
            example_path = profile_dir / "master_profile.example.json"
            example_path.write_text(json.dumps({"basics": {"name": "Example"}}), encoding="utf-8")

            with patch.object(profile_store, "PROFILE_DIR", profile_dir), patch.object(
                profile_store, "MASTER_PROFILE_PATH", real_path
            ), patch.object(profile_store, "MASTER_PROFILE_EXAMPLE_PATH", example_path):
                payload = profile_store.load_master_profile()

        self.assertEqual(payload["basics"]["name"], "Example")


if __name__ == "__main__":
    unittest.main()
