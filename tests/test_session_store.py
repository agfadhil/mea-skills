"""Readable session folders preserve identity, isolation, and old sessions."""

import importlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "trivy-porter" / "scripts"


class ReadableStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        try:
            cls.store = importlib.import_module("session_store")
        finally:
            sys.path.pop(0)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="porter-readable-store-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.project = self.workspace / "project"
        self.project.mkdir()
        self.base = self.workspace / "reports"
        self.root, self.base, self.legacy = self.store.project_context(self.project, self.base)

    def create(self, action="image"):
        return self.store.create_data({"stage": "complete", "scan": {"method": action}},
                                      self.root, self.base, self.legacy)

    def test_folder_uses_local_minute_and_action_with_collision_suffix(self):
        class FakeClock:
            @staticmethod
            def now(*_args):
                from datetime import datetime
                return datetime(2026, 10, 23, 14, 30)

        # The clock only controls the folder label, while timestamp metadata
        # remains valid ISO text from the ordinary timestamp helper.
        with patch.object(self.store, "datetime", FakeClock), patch.object(self.store, "timestamp", return_value="2026-10-23T07:30:00Z"):
            first, second = self.create(), self.create()
            third = self.create("fs")
        self.assertEqual(self.store.session_directory(first, self.base, self.legacy).name, "20261023-1430-image")
        self.assertEqual(self.store.session_directory(second, self.base, self.legacy).name, "20261023-1430-image-2")
        self.assertEqual(self.store.session_directory(third, self.base, self.legacy).name, "20261023-1430-fs")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.store.read(SimpleNamespace(session=first["session_id"]), self.root, self.legacy), first)

    def test_shared_root_keeps_projects_isolated_and_does_not_ignore_application(self):
        first = self.create()
        other = self.workspace / "other"
        other.mkdir()
        root, base, legacy = self.store.project_context(other, self.base)
        second = self.store.create_data({"stage": "complete"}, root, base, legacy)
        self.assertEqual([data["session_id"] for data in self.store.load_sessions(self.legacy, self.root)], [first["session_id"]])
        self.assertEqual([data["session_id"] for data in self.store.load_sessions(legacy, root)], [second["session_id"]])
        with self.assertRaises(self.store.StoreError):
            self.store.read(SimpleNamespace(session=second["session_id"]), self.root, self.legacy)
        self.assertFalse((base / ".gitignore").exists())

    def test_concurrent_creates_keep_distinct_readable_sessions(self):
        with ThreadPoolExecutor(max_workers=8) as workers:
            created = list(workers.map(lambda _: self.create(), range(8)))
        sessions = self.store.load_sessions(self.legacy, self.root)
        self.assertEqual({item["session_id"] for item in sessions},
                         {item["session_id"] for item in created})
        folders = {self.store.session_directory(item, self.base, self.legacy) for item in created}
        self.assertEqual(len(folders), 8)
        self.assertTrue(all((folder / "session.json").is_file() for folder in folders))

    def test_legacy_session_is_read_saved_and_cleaned_in_place(self):
        legacy_data = self.create()
        new_folder = self.store.session_directory(legacy_data, self.base, self.legacy)
        self.legacy.mkdir()
        self.store.ensure_storage_ignore(self.legacy)
        old_file = self.legacy / (legacy_data["session_id"] + ".json")
        self.store.write_atomic(old_file, legacy_data)
        (new_folder / "session.json").unlink()
        legacy_data["last_report"] = "legacy recap"
        saved = self.store.save_data(legacy_data, legacy_data["session_id"], self.root, self.base, self.legacy)
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(self.store.session_directory(saved, self.base, self.legacy), self.legacy)
        plan = self.store.cleanup_plan(self.root, self.base, saved["session_id"])
        self.store.delete_sessions(plan)
        self.assertFalse(old_file.exists())

    @unittest.skipIf(os.name == "nt", "Fixture symlinks may require Windows privileges")
    def test_discovery_does_not_follow_a_linked_session_folder_or_metadata(self):
        data = self.create()
        folder = self.store.session_directory(data, self.base, self.legacy)
        metadata = folder / "session.json"
        external = self.workspace / "external.json"
        external.write_bytes(metadata.read_bytes())
        metadata.unlink()
        metadata.symlink_to(external)
        with self.assertRaises(self.store.StoreError):
            self.store.read(SimpleNamespace(session=data["session_id"]), self.root, self.legacy)
        metadata.unlink()
        metadata.write_bytes(external.read_bytes())
        moved = self.workspace / "moved-folder"
        folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
        self.assertEqual(self.store.load_sessions(self.legacy, self.root), [])
        self.assertEqual(json.loads(external.read_text())["session_id"], data["session_id"])

    def test_malformed_new_metadata_and_invalid_id_types_raise_store_errors(self):
        data = self.create()
        metadata = self.store.session_directory(data, self.base, self.legacy) / "session.json"
        payload = dict(data)
        del payload["session_id"]
        metadata.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(self.store.StoreError):
            self.store.load_sessions(self.legacy, self.root)
        for value in (None, 7, [], {}, False):
            with self.subTest(value=value), self.assertRaises(self.store.StoreError):
                self.store.validate_id(value)

    def test_foreign_session_with_invalid_stage_does_not_block_current_project(self):
        first = self.create()
        other = self.workspace / "other"
        other.mkdir()
        root, base, legacy = self.store.project_context(other, self.base)
        second = self.store.create_data({"stage": "complete"}, root, base, legacy)
        metadata = self.store.session_directory(second, base, legacy) / "session.json"
        second["stage"] = "damaged-stage"
        metadata.write_text(json.dumps(second), encoding="utf-8")
        self.assertEqual([data["session_id"] for data in self.store.load_sessions(self.legacy, self.root)], [first["session_id"]])
        with self.assertRaises(self.store.StoreError):
            self.store.load_sessions(legacy, root)

    def test_new_folder_revision_conflicts_and_cleanup_preview_changes_are_rejected(self):
        first = self.create()
        plan = self.store.cleanup_plan(self.root, self.base, first["session_id"])
        updated = dict(first, last_report="updated")
        self.store.save_data(updated, first["session_id"], self.root, self.base, self.legacy)
        with self.assertRaises(self.store.StoreError):
            self.store.save_data(first, first["session_id"], self.root, self.base, self.legacy)
        with self.assertRaises(self.store.StoreError):
            self.store.delete_sessions(plan)
        self.assertTrue((self.store.session_directory(first, self.base, self.legacy) / "session.json").is_file())


if __name__ == "__main__":
    unittest.main()
