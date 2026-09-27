"""Offline tests for Spellbook location bar (no TTY required)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))
sys.path.insert(0, str(Path.home() / "bin"))


def _load_spellbook():
    path = BIN / "spellbook"
    name = "fae_spellbook_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sb = _load_spellbook()


class TestPathHelpers(unittest.TestCase):
    def test_path_crumbs_unix_root(self):
        crumbs = sb.path_crumbs(Path("/"))
        self.assertEqual(crumbs, [("/", Path("/"))])

    def test_path_crumbs_nested(self):
        # A fixture path, same depth as before. It used to be this machine's
        # real home directory, which leaked the username into a public repo
        # (audit F-5) and made the test read as if it were about the operator
        # rather than about breadcrumb splitting.
        crumbs = sb.path_crumbs(Path("/srv/faeos/bin"))
        self.assertEqual([label for label, _ in crumbs], ["/", "srv", "faeos", "bin"])
        self.assertEqual(crumbs[-1][1], Path("/srv/faeos/bin"))
        self.assertEqual(crumbs[1][1], Path("/srv"))

    def test_clean_pasted_path_quotes_and_newline(self):
        self.assertEqual(sb.clean_pasted_path('  "/tmp/foo"\nextra\n'), "/tmp/foo")
        self.assertEqual(sb.clean_pasted_path("'/tmp/bar'"), "/tmp/bar")
        self.assertEqual(sb.clean_pasted_path(""), "")

    def test_resolve_goto_dir(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest, select, err = sb.resolve_goto(tmp, str(tmp))
            self.assertIsNone(err)
            self.assertEqual(dest, tmp.resolve())
            self.assertIsNone(select)

    def test_resolve_goto_file_selects_parent(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            f = tmp / "scroll.txt"
            f.write_text("hi", encoding="utf-8")
            dest, select, err = sb.resolve_goto(tmp, str(f))
            self.assertIsNone(err)
            self.assertEqual(dest, tmp.resolve())
            self.assertEqual(select, f.resolve())

    def test_resolve_goto_relative_and_missing(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            nested = tmp / "tomes"
            nested.mkdir()
            dest, select, err = sb.resolve_goto(tmp, "tomes")
            self.assertIsNone(err)
            self.assertEqual(dest, nested.resolve())
            dest, select, err = sb.resolve_goto(tmp, "no-such-shelf")
            self.assertIsNone(dest)
            self.assertEqual(err, "missing")

    def test_resolve_goto_tilde(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            docs = tmp / "docs"
            docs.mkdir()
            old = os.environ.get("HOME")
            os.environ["HOME"] = str(tmp)
            try:
                dest, select, err = sb.resolve_goto(Path("/"), "~/docs")
            finally:
                if old is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old
            self.assertIsNone(err)
            self.assertEqual(dest, docs.resolve())


class TestFileManagerPathBar(unittest.TestCase):
    def test_apply_goto_and_path_edit_keys(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            (tmp / "alpha").mkdir()
            (tmp / "note.md").write_text("x", encoding="utf-8")
            fm = sb.FileManager(start_path=str(tmp))
            fm._begin_path_edit()
            self.assertTrue(fm.path_editing)
            self.assertEqual(fm.path_buf, str(tmp))
            fm._handle_path_edit_key("ctrl-u")
            self.assertEqual(fm.path_buf, "")
            for ch in str(tmp / "alpha"):
                fm._handle_path_edit_key(ch)
            fm._handle_path_edit_key("enter")
            self.assertFalse(fm.path_editing)
            self.assertEqual(fm.current_path, (tmp / "alpha").resolve())

            fm._apply_goto(str(tmp / "note.md"))
            self.assertEqual(fm.current_path, tmp.resolve())
            files = fm.get_files()
            self.assertEqual(files[fm.selected_index].name, "note.md")

            fm._apply_goto("ghost-path")
            self.assertIn("not on the shelf", fm.status)

    def test_ctrl_w_deletes_path_component(self):
        with tempfile.TemporaryDirectory() as raw:
            fm = sb.FileManager(start_path=raw)
            fm._begin_path_edit()
            fm.path_buf = "/srv/faeos/bin"
            fm.path_caret = len(fm.path_buf)
            fm._handle_path_edit_key("ctrl-w")
            self.assertEqual(fm.path_buf, "/srv/faeos/")
            fm._handle_path_edit_key("esc")
            self.assertFalse(fm.path_editing)

    def test_header_crumb_hits_cover_labels(self):
        os.environ["PIXIE_UNICODE"] = "1"
        with tempfile.TemporaryDirectory() as raw:
            nested = Path(raw) / "a" / "b"
            nested.mkdir(parents=True)
            fm = sb.FileManager(start_path=str(nested))
            _frame, rel_y, hits, content_x0, body_w = fm.draw_header()
            self.assertEqual(rel_y, 2)
            self.assertEqual(content_x0, 3)
            self.assertGreaterEqual(body_w, 1)
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[-1][2].name, "b")


if __name__ == "__main__":
    unittest.main()
