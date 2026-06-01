from pathlib import Path
import unittest

from logscope.analyzer import analyze_files, parse_line


class AnalyzerTests(unittest.TestCase):
    def test_parse_line_normalizes_warning_alias(self) -> None:
        event = parse_line("2026-06-01 10:15:01 WARN cache retry took 250ms", "app.log", 7)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.level, "WARNING")
        self.assertEqual(event.timestamp, "2026-06-01 10:15:01")
        self.assertIn("cache retry", event.message)

    def test_analyze_files_counts_selected_levels(self) -> None:
        test_dir = Path.cwd() / ".test-data"
        test_dir.mkdir(exist_ok=True)
        log_path = test_dir / "service.log"

        try:
            log_path.write_text(
                "\n".join(
                    [
                        "2026-06-01 10:00:00 INFO started",
                        "2026-06-01 10:01:00 WARNING request 123 timed out",
                        "2026-06-01 10:02:00 ERROR request 456 timed out",
                        "2026-06-01 10:03:00 DEBUG ignored detail",
                    ]
                ),
                encoding="utf-8",
            )

            result = analyze_files([log_path])
        finally:
            log_path.unlink(missing_ok=True)

        self.assertEqual(result.total_lines, 4)
        self.assertEqual(result.matched_events, 2)
        self.assertEqual(result.level_counts["WARNING"], 1)
        self.assertEqual(result.level_counts["ERROR"], 1)
        self.assertEqual(result.top_patterns[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
