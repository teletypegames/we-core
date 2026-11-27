"""Tests of warpstore: the WECP api 6 kind rename and the config migration."""

import json
import os
import tempfile
import unittest

import warpstore as ws


def entry(kind, path="/file/blessingofra/2.0.0/blessingofra-2.0.0.prg"):
    """A catalog entry with one release carrying one asset."""
    release = {"id": 1, "version": "2.0.0", "assets": [{"kind": kind, "path": path}]}
    return {"software": {"name": "blessingofra", "platform": "c64", "status": "released"},
            "latestRelease": release, "releases": [release]}


class CanonicalKindTest(unittest.TestCase):
    """`cartridge` (api < 6) and `package` (api 6) are the same kind."""

    def test_cartridge_reads_as_package(self):
        self.assertEqual(ws.canonical_kind("cartridge"), "package")

    def test_other_kinds_pass_through(self):
        for kind in ("package", "linux_x64", "html", "", None):
            self.assertEqual(ws.canonical_kind(kind), kind)

    def test_pick_release_matches_either_name(self):
        for asset_kind in ("cartridge", "package"):
            for wanted in ("cartridge", "package", ["package"]):
                release, name, kind, _path = ws.pick_release(entry(asset_kind), wanted, "")
                self.assertIsNotNone(release, f"{asset_kind} asset, {wanted} wanted")
                self.assertEqual(name, "blessingofra-2.0.0.prg")
                self.assertEqual(kind, "package")

    def test_survey_installs_an_old_engines_cartridge(self):
        cfg = {"catalog": {}, "platforms": {"c64": {"kind": "package", "ext": ""}}}
        games, skipped, unavailable = ws.survey_catalog(
            cfg, {"softwares": [entry("cartridge")]}, lambda spec, sw: ("c64", {}),
            {"os": "linux", "arch": "x86_64"})
        self.assertEqual([g["kind"] for g in games], ["package"])
        self.assertEqual((skipped, unavailable), ([], []))


class ConfigMigrationTest(unittest.TestCase):
    """A box keeps its old config.json; loading it renames the kind once and saves it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "config.json")
        self.defaults = {"store": {"id": "test", "base_url": "https://example.org"},
                         "behavior": {}, "platforms": {}}

    def tearDown(self):
        self.dir.cleanup()

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_renames_and_saves_back(self):
        self.write({"store": {"id": "test"}, "platforms": {
            "c64": {"system": "c64", "kind": "cartridge", "ext": ""},
            "tic80": {"kind": ["cartridge", "html"]},
            "bevy": {"kind": {"x86_64": "linux_x64", "*": "cartridge"}},
        }})
        cfg = ws.load_config(self.path, self.defaults)
        self.assertEqual(cfg["platforms"]["c64"]["kind"], "package")
        saved = self.read()["platforms"]
        self.assertEqual(saved["c64"], {"system": "c64", "kind": "package", "ext": ""})
        self.assertEqual(saved["tic80"]["kind"], ["package", "html"])
        self.assertEqual(saved["bevy"]["kind"], {"x86_64": "linux_x64", "*": "package"})

    def test_a_current_config_is_not_rewritten(self):
        self.write({"store": {"id": "test"}, "platforms": {"c64": {"kind": "package"}}})
        before = os.stat(self.path).st_mtime_ns
        with open(self.path, "rb") as fh:
            blob = fh.read()
        ws.load_config(self.path, self.defaults)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), blob)
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_migration_reports_whether_it_changed(self):
        config = {"platforms": {"c64": {"kind": "cartridge"}, "love": {"kind": "linux_x64"}}}
        self.assertTrue(ws.migrate_config_kinds(config))
        self.assertFalse(ws.migrate_config_kinds(config))
        self.assertFalse(ws.migrate_config_kinds({}))


if __name__ == "__main__":
    unittest.main()
