import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "check_evidence.py"
SPEC = importlib.util.spec_from_file_location("check_evidence", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class EvidenceCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        self.source = self.root / "sample.py"
        self.source.write_text("first\nsecond\nthird\n", encoding="utf-8")
        self.evidence = self.base / "evidence.json"

    def claim(self, **updates):
        item = {
            "id": "C1",
            "claim": "合成测试引用，不代表事实核验结果。",
            "file": "sample.py",
            "start_line": 1,
            "end_line": 3,
        }
        item.update(updates)
        return item

    def run_checker(self, document=None, extra=()):
        if document is not None:
            self.evidence.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        process = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(self.root), str(self.evidence), *extra],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(process.stderr, "")
        return process.returncode, json.loads(process.stdout)

    def assert_error(self, claim, code, exit_code=1):
        actual, report = self.run_checker({"claims": [claim]})
        self.assertEqual(actual, exit_code)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["errors"][0]["code"], code)
        self.assertEqual(report["errors"][0]["id"], claim["id"])

    def test_valid_reference(self):
        code, report = self.run_checker({"claims": [self.claim()]})
        self.assertEqual(code, 0)
        self.assertEqual(report, {
            "ok": True, "checked": 1, "error_count": 0, "errors": [], "truncated": False,
        })

    def test_missing_file(self):
        self.assert_error(self.claim(file="missing.py"), "FILE_NOT_FOUND")

    def test_line_out_of_range(self):
        self.assert_error(self.claim(end_line=4), "LINE_OUT_OF_RANGE")

    def test_invalid_line_ranges(self):
        for start, end in ((0, 1), (-1, 1), (3, 2), (1, 0)):
            with self.subTest(start=start, end=end):
                self.assert_error(self.claim(start_line=start, end_line=end), "INVALID_LINE_RANGE")

    def test_empty_source(self):
        self.source.write_text("", encoding="utf-8")
        self.assert_error(self.claim(end_line=1), "LINE_OUT_OF_RANGE")

    def test_directory_reference(self):
        self.assert_error(self.claim(file="."), "NOT_A_FILE")

    def test_parent_escape(self):
        outside = self.base / "outside.py"
        outside.write_text("outside\n", encoding="utf-8")
        self.assert_error(self.claim(file="../outside.py"), "PATH_OUTSIDE_ROOT")

    def test_absolute_drive_unc_and_special_paths(self):
        paths = (
            str(self.source), "/tmp/outside.py", "C:\\outside.py", "C:outside.py",
            "\\\\server\\share\\secret.py", "sample.py:stream", "bad\x00.py",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assert_error(self.claim(file=path), "PATH_OUTSIDE_ROOT")

    def test_windows_relative_separator(self):
        directory = self.root / "nested"
        directory.mkdir()
        (directory / "sample.py").write_text("one\n", encoding="utf-8")
        code, report = self.run_checker({"claims": [self.claim(file="nested\\sample.py", end_line=1)]})
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])

    def test_real_outside_symlink(self):
        outside = self.base / "outside.py"
        outside.write_text("outside\n", encoding="utf-8")
        link = self.root / "linked.py"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"当前系统不允许创建符号链接: {exc}")
        self.assert_error(self.claim(file="linked.py", end_line=1), "PATH_OUTSIDE_ROOT")

    @unittest.skipUnless(os.name == "nt", "Windows junction 测试")
    def test_real_outside_junction(self):
        outside = self.base / "outside-dir"
        outside.mkdir()
        (outside / "sample.py").write_text("outside\n", encoding="utf-8")
        link = self.root / "junction"
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.addCleanup(lambda: link.rmdir() if link.exists() else None)
        self.assert_error(self.claim(file="junction/sample.py", end_line=1), "PATH_OUTSIDE_ROOT")

    def test_resolved_outside_path_is_rejected(self):
        outside = self.base / "outside.py"
        with mock.patch.object(Path, "resolve", return_value=outside):
            result = CHECKER.check_reference(self.root, self.claim(), {})
        self.assertEqual(result["code"], "PATH_OUTSIDE_ROOT")

    def test_invalid_json(self):
        self.evidence.write_text("{broken", encoding="utf-8")
        code, report = self.run_checker()
        self.assertEqual(code, 2)
        self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_invalid_document_shapes(self):
        documents = ([], None, {}, {"claims": []}, {"claims": {}}, {"claims": ["text"]})
        for document in documents:
            with self.subTest(document=document):
                self.evidence.write_text(json.dumps(document), encoding="utf-8")
                code, report = self.run_checker()
                self.assertEqual(code, 2)
                self.assertEqual(report["checked"], 0)

    def test_invalid_field_types(self):
        updates = (
            {"id": ""}, {"id": " "}, {"claim": None}, {"file": 12},
            {"start_line": True}, {"start_line": "1"}, {"end_line": 3.0},
        )
        for update in updates:
            with self.subTest(update=update):
                code, report = self.run_checker({"claims": [self.claim(**update)]})
                self.assertEqual(code, 2)
                self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_missing_field(self):
        claim = self.claim()
        del claim["end_line"]
        code, report = self.run_checker({"claims": [claim]})
        self.assertEqual(code, 2)
        self.assertEqual(report["checked"], 0)

    def test_duplicate_ids(self):
        code, report = self.run_checker({"claims": [self.claim(), self.claim()]})
        self.assertEqual(code, 2)
        self.assertIn("重复", report["errors"][0]["message"])

    def test_invalid_source_encoding(self):
        self.source.write_bytes(b"\xff\xfe\x00")
        self.assert_error(self.claim(end_line=1), "FILE_READ_ERROR", exit_code=2)

    def test_permission_error(self):
        original_open = Path.open

        def controlled_open(path, *args, **kwargs):
            if path == self.source:
                raise PermissionError("synthetic read denial")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", new=controlled_open):
            result = CHECKER.check_reference(self.root, self.claim(), {})
        self.assertEqual(result["code"], "FILE_READ_ERROR")

    def test_utf8_bom(self):
        self.source.write_text("one\ntwo\nthree\n", encoding="utf-8-sig")
        self.evidence.write_text(json.dumps({"claims": [self.claim()]}), encoding="utf-8-sig")
        code, report = self.run_checker()
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])

    def test_crlf_without_final_newline(self):
        self.source.write_bytes(b"one\r\ntwo\r\nthree")
        code, report = self.run_checker({"claims": [self.claim()]})
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])

    def test_error_limit_preserves_total(self):
        claims = [self.claim(id=f"C{index}", end_line=10) for index in range(4)]
        code, report = self.run_checker({"claims": claims}, extra=("--max-errors", "2"))
        self.assertEqual(code, 1)
        self.assertEqual(report["checked"], 4)
        self.assertEqual(report["error_count"], 4)
        self.assertEqual(len(report["errors"]), 2)
        self.assertTrue(report["truncated"])

    def test_invalid_error_limit(self):
        for limit in ("0", "-1", "text"):
            with self.subTest(limit=limit):
                code, report = self.run_checker({"claims": [self.claim()]}, extra=("--max-errors", limit))
                self.assertEqual(code, 2)
                self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_missing_arguments_are_json(self):
        process = subprocess.run(
            [sys.executable, "-B", str(SCRIPT)], capture_output=True,
            text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stderr, "")
        self.assertEqual(json.loads(process.stdout)["errors"][0]["code"], "INPUT_ERROR")

    def test_unknown_argument(self):
        code, report = self.run_checker({"claims": [self.claim()]}, extra=("--unknown",))
        self.assertEqual(code, 2)
        self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_missing_evidence_file(self):
        code, report = self.run_checker()
        self.assertEqual(code, 2)
        self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_invalid_root(self):
        self.root = self.base / "missing-root"
        code, report = self.run_checker({"claims": [self.claim()]})
        self.assertEqual(code, 2)
        self.assertEqual(report["errors"][0]["code"], "INPUT_ERROR")

    def test_network_root_rejected(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = CHECKER.main(["//server/share", str(self.evidence)])
        self.assertEqual(code, 2)
        self.assertIn("网络共享", json.loads(output.getvalue())["errors"][0]["message"])

    def test_does_not_execute_or_modify_source(self):
        self.source.write_text("raise RuntimeError('must never run')\n", encoding="utf-8")
        before = self.source.read_bytes()
        code, report = self.run_checker({"claims": [self.claim(end_line=1)]})
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_does_not_claim_semantic_verification(self):
        code, report = self.run_checker({"claims": [self.claim(claim="这份合成源码实现了模型训练。") ]})
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])

    def test_bundled_examples(self):
        for name, expected_code, expected_errors in (
            ("evidence-valid.json", 0, 0), ("evidence-invalid.json", 1, 3),
        ):
            with self.subTest(name=name):
                process = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), str(SKILL_ROOT / "examples" / "sample-repo"),
                     str(SKILL_ROOT / "examples" / name)],
                    capture_output=True, text=True, encoding="utf-8", timeout=15,
                )
                self.assertEqual(process.returncode, expected_code)
                self.assertEqual(process.stderr, "")
                self.assertEqual(json.loads(process.stdout)["error_count"], expected_errors)


if __name__ == "__main__":
    unittest.main()
