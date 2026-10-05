import gzip
import io
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import runtime_notices as notices


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return stream.getvalue()


class RuntimeNoticesTests(unittest.TestCase):
    def test_nested_notices_keep_origins_and_ignore_icon_class(self):
        data = archive(
            {
                "classes.jar": archive({"META-INF/NOTICE": b"author notice"}),
                "libs/extra.jar": archive({"LICENSE.txt": b"MIT text"}),
                "CopyrightKt.class": b"not a notice",
            }
        )
        self.assertEqual(
            notices.embedded_notices(data),
            {"classes.jar!/META-INF/NOTICE": b"author notice", "libs/extra.jar!/LICENSE.txt": b"MIT text"},
        )

    def test_distinct_source_headers_are_not_lost(self):
        data = archive(
            {
                "A.kt": "/* Copyright Alice; permission is hereby granted */\nclass A",
                "B.java": "/* Copyright Bob; redistribution and use permitted */\nclass B {}",
            }
        )
        result = notices.source_headers(data).decode()
        self.assertIn("Copyright Alice", result)
        self.assertIn("Copyright Bob", result)
        self.assertNotIn("class B", result)

    def test_public_inventory_has_no_local_paths_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "example.jar"
            artifact.write_bytes(b"artifact")
            inventory = Path(directory) / "local.json"
            row = {"coordinate": "example:library:1", "file": str(artifact)}
            inventory.write_text(json.dumps([row, row]), encoding="utf-8")
            result = notices.artifact_rows(inventory)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["artifact"], "example.jar")
            self.assertNotIn(directory, json.dumps(result))

    def test_suffix_rules_roundtrip_including_exceptions(self):
        rules, exceptions = b"*.example\ncom\n", b"www.example\n"
        raw = struct.pack(">I", len(rules)) + rules + struct.pack(">I", len(exceptions)) + exceptions
        result = notices.public_suffix_source(gzip.compress(raw))
        self.assertEqual(
            [line for line in result.splitlines() if not line.startswith(b"//")],
            [b"*.example", b"com", b"!www.example"],
        )
        with self.assertRaises(ValueError):
            notices.public_suffix_source(gzip.compress(raw + b"extra"))

    def test_unreviewed_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"artifacts": []}), encoding="utf-8")
            with (
                patch.object(notices, "EVIDENCE", root),
                patch.object(notices, "artifact_rows", return_value=[{}]),
                self.assertRaisesRegex(ValueError, "differ from reviewed"),
            ):
                notices.generate(root / "unused", root / "unused", root / "unused")

    def test_tampered_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE").write_bytes(b"tampered")
            (root / "manifest.json").write_text(
                json.dumps({"artifacts": [], "files": {"LICENSE": "original"}}), encoding="utf-8"
            )
            with (
                patch.object(notices, "EVIDENCE", root),
                patch.object(notices, "artifact_rows", return_value=[]),
                self.assertRaisesRegex(ValueError, "evidence changed"),
            ):
                notices.generate(root / "unused", root / "unused", root / "unused")

    def test_apk_verification_rejects_missing_or_changed_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected, apk = root / "notices.zip", root / "app.apk"
            expected.write_bytes(archive({"third_party/LICENSE.txt": "license"}))
            for contents in ({}, {"assets/third_party/LICENSE.txt": "wrong"}):
                apk.write_bytes(archive(contents))
                with self.assertRaises(ValueError):
                    notices.verify_apk(apk, expected)
            apk.write_bytes(archive({"assets/third_party/LICENSE.txt": "license", "classes.dex": "other"}))
            notices.verify_apk(apk, expected)


if __name__ == "__main__":
    unittest.main()
