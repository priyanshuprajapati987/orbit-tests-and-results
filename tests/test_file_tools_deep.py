"""Deep tests for orbit/orbit/file_tools.py (Loop 11/4).

Covers every statement:
  * ``_expand_path`` — quote stripping, every shortcut (desktop..e),
    subdir suffixes (forward/backslash), case-insensitivity, fallback.
  * ``_categorize`` — all six categories + unknown -> Other.
  * ``_format_size`` — B/KB/MB/GB/TB/PB ladder incl. exact boundaries.
  * ``analyze_dir`` — missing path, non-dir path, empty dir, real walks
    with known sizes, category counting, largest-file sorting + 15-cap,
    per-file stat failure (logged, scan continues).
  * ``format_analysis`` — error line, full report with category bars and
    10-row largest-files cap, empty-report branches.
  * ``read_pdf_file`` — delegates to tools.pdf_reader.read_pdf.
  * ``parse_text`` — quoted paths, shortcut keywords, cleaned folder
    names, fallback ".", result envelope.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import file_tools as ft


class ExpandPathTests(unittest.TestCase):
    def test_plain_path_passthrough(self):
        self.assertEqual(ft._expand_path("foo/bar"), Path("foo/bar"))

    def test_quotes_and_spaces_stripped(self):
        self.assertEqual(ft._expand_path("  'C:/x/y'  "), Path("C:/x/y"))
        self.assertEqual(ft._expand_path('"C:/x/y"'), Path("C:/x/y"))

    def test_desktop_shortcut(self):
        self.assertEqual(ft._expand_path("desktop"),
                         Path.home() / "Desktop")

    def test_desktop_case_insensitive(self):
        self.assertEqual(ft._expand_path("Desktop"),
                         Path.home() / "Desktop")

    def test_desktop_subdir_suffix(self):
        p = ft._expand_path("desktop/sub/folder.txt")
        self.assertEqual(p, Path(str(Path.home() / "Desktop")
                                 + "/sub/folder.txt"))

    def test_desktop_backslash_suffix(self):
        p = ft._expand_path("downloads\\report.pdf")
        self.assertEqual(p, Path(str(Path.home() / "Downloads")
                                 + "\\report.pdf"))

    def test_every_exact_shortcut(self):
        cases = {
            "home": Path.home(),
            "documents": Path.home() / "Documents",
            "pictures": Path.home() / "Pictures",
            "music": Path.home() / "Music",
            "videos": Path.home() / "Videos",
            "c": Path("C:/"),
            "d": Path("D:/"),
            "e": Path("E:/"),
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                self.assertEqual(ft._expand_path(key), expected)

    def test_unknown_path_falls_through(self):
        self.assertEqual(ft._expand_path("nothing/here"),
                         Path("nothing/here"))


class CategorizeTests(unittest.TestCase):
    def test_known_categories(self):
        self.assertEqual(ft._categorize(".png"), "Images")
        self.assertEqual(ft._categorize(".PNG"), "Images")  # lowercased
        self.assertEqual(ft._categorize(".pdf"), "Documents")
        self.assertEqual(ft._categorize(".mp3"), "Audio")
        self.assertEqual(ft._categorize(".mkv"), "Video")
        self.assertEqual(ft._categorize(".rar"), "Archives")
        self.assertEqual(ft._categorize(".rs"), "Code")
        self.assertEqual(ft._categorize(".exe"), "Executables")
        self.assertEqual(ft._categorize(".sqlite"), "Data")

    def test_unknown_extension(self):
        self.assertEqual(ft._categorize(".xyz"), "Other")

    def test_missing_dot_is_other(self):
        self.assertEqual(ft._categorize("png"), "Other")


class FormatSizeTests(unittest.TestCase):
    def test_ladder(self):
        cases = [
            (0, "0.0 B"),
            (1023, "1023.0 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024**2 * 5, "5.0 MB"),
            (1024**3 * 2, "2.0 GB"),
            (1024**4 * 7, "7.0 TB"),
            (1024**5 * 3, "3.0 PB"),
        ]
        for n, expected in cases:
            with self.subTest(n=n):
                self.assertEqual(ft._format_size(n), expected)


class AnalyzeDirTests(unittest.TestCase):
    def _mkfile(self, path: Path, size: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)

    def test_missing_path(self):
        result = ft.analyze_dir("Z:/definitely/not/here")
        self.assertIn("error", result)
        self.assertIn("exists nahi karta", result["error"])

    def test_file_is_not_dir(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.txt"
            f.write_text("hi", encoding="utf-8")
            result = ft.analyze_dir(str(f))
        self.assertIn("error", result)
        self.assertIn("directory nahi hai", result["error"])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = ft.analyze_dir(td)
        self.assertEqual(result["total_files"], 0)
        self.assertEqual(result["total_dirs"], 0)
        self.assertEqual(result["total_size"], 0)
        self.assertEqual(result["categories"], {})
        self.assertEqual(result["largest_files"], [])

    def test_walk_counts_sizes_and_categories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._mkfile(root / "a.png", 10)
            self._mkfile(root / "b.pdf", 20)
            self._mkfile(root / "sub" / "c.mp3", 30)
            self._mkfile(root / "sub" / "d.py", 40)
            result = ft.analyze_dir(td)
        self.assertEqual(result["total_files"], 4)
        self.assertEqual(result["total_dirs"], 1)
        self.assertEqual(result["total_size"], 100)
        self.assertEqual(result["total_size_str"], "100.0 B")
        self.assertEqual(result["categories"],
                         {"Code": 1, "Audio": 1, "Images": 1,
                          "Documents": 1})

    def test_largest_files_sorted_desc(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._mkfile(root / "small.png", 10)
            self._mkfile(root / "big.mp3", 400)
            self._mkfile(root / "mid.pdf", 200)
            result = ft.analyze_dir(td)
        sizes = [f["size"] for f in result["largest_files"]]
        self.assertEqual(sizes, [400, 200, 10])
        self.assertTrue(result["largest_files"][0]["path"].endswith(
            "big.mp3"))
        self.assertEqual(result["largest_files"][0]["size_str"], "400.0 B")

    def test_largest_files_capped_at_15(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(20):
                self._mkfile(Path(td) / f"f{i:02d}.txt", i + 1)
            result = ft.analyze_dir(td)
        self.assertEqual(result["total_files"], 20)
        self.assertEqual(len(result["largest_files"]), 15)

    def test_stat_failure_logged_and_scan_continues(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._mkfile(root / "ok.png", 10)
            ghost = root / "ghost.txt"
            ghost.write_text("x", encoding="utf-8")
            orig_stat = Path.stat

            def flaky_stat(self, *args, **kwargs):
                if self.name == "ghost.txt":
                    raise OSError("file vanished")
                return orig_stat(self, *args, **kwargs)

            with mock.patch.object(Path, "stat", flaky_stat), \
                    mock.patch.object(ft, "logger") as lg:
                result = ft.analyze_dir(td)
        self.assertEqual(result["total_files"], 2)  # ghost still counted
        self.assertEqual(result["total_size"], 10)  # but not sized
        self.assertEqual(result["categories"], {"Images": 1})
        lg.exception.assert_called_once()


class FormatAnalysisTests(unittest.TestCase):
    def test_error_line(self):
        out = ft.format_analysis("Z:/definitely/not/here")
        self.assertTrue(out.startswith("❌ "))
        self.assertIn("exists nahi karta", out)

    def test_empty_dir_report(self):
        with tempfile.TemporaryDirectory() as td:
            out = ft.format_analysis(td)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("📁 **Directory Analysis:**"))
        self.assertIn("Files: 0 | Folders: 0 | Size: 0.0 B", out)
        # no categories / no largest files -> those sections skipped
        self.assertNotIn("Categories", out)
        self.assertNotIn("Largest Files", out)

    def test_full_report_sections(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i in range(12):
                (root / f"f{i:02d}.txt").write_bytes(b"x" * (i + 1))
            (root / "pic.png").write_bytes(b"y" * 500)
            out = ft.format_analysis(td)
        self.assertIn("**Categories:**", out)
        self.assertIn("**Largest Files:**", out)
        self.assertIn("Images", out)
        self.assertIn("Documents", out)
        # bar is exactly 20 cells wide
        bar_line = next(ln for ln in out.splitlines() if "█" in ln)
        bar = bar_line[bar_line.index("█"):]
        self.assertEqual(len(bar), 20)
        # largest list capped at 10 rows in the report
        largest_idx = out.index("**Largest Files:**")
        rows = [ln for ln in out[largest_idx:].splitlines()[1:] if ln]
        self.assertEqual(len(rows), 10)

    def test_report_path_echoed(self):
        with tempfile.TemporaryDirectory() as td:
            out = ft.format_analysis(td)
        self.assertIn(str(Path(td)), out.splitlines()[0])


class ReadPdfTests(unittest.TestCase):
    def test_delegates_to_pdf_reader(self):
        with mock.patch("orbit.orbit.tools.pdf_reader.read_pdf",
                        return_value={"pages": 3}) as reader:
            result = ft.read_pdf_file("doc.pdf")
        self.assertEqual(result, {"pages": 3})
        reader.assert_called_once_with("doc.pdf")


class ParseTextTests(unittest.TestCase):
    def _parse(self, text):
        with mock.patch.object(ft, "format_analysis",
                               return_value="REPORT") as fa:
            result = ft.parse_text(text)
        return result, fa.call_args.args[0]

    def test_envelope(self):
        result, _ = self._parse('analyze "some/quoted/path"')
        self.assertEqual(result, {"type": "result", "result": "REPORT"})

    def test_quoted_path_wins(self):
        _, path = self._parse('analyze "some/quoted/path"')
        self.assertEqual(path, "some/quoted/path")

    def test_keyword_desktop_resolves_to_home(self):
        _, path = self._parse("show files in desktop")
        self.assertEqual(path, str(Path.home() / "Desktop"))

    def test_keyword_downloads(self):
        # keyword sets "downloads", cleanup branch then resolves it to
        # the absolute home path (shortcuts dict overwrite).
        _, path = self._parse("scan downloads")
        self.assertEqual(path, str(Path.home() / "Downloads"))

    def test_keyword_drive_letter(self):
        _, path = self._parse("show me C:/temp")
        self.assertEqual(path, "c:")

    def test_bare_folder_name_not_in_shortcuts_falls_back(self):
        _, path = self._parse("analyze xyz")
        self.assertEqual(path, ".")

    def test_plain_text_falls_back_to_dot(self):
        _, path = self._parse("hello")
        self.assertEqual(path, ".")

    def test_lowercase_keyword(self):
        _, path = self._parse("dikha documents")
        self.assertEqual(path, str(Path.home() / "Documents"))


if __name__ == "__main__":
    unittest.main()
