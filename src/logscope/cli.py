"""Command-line interface for LogScope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .analyzer import DEFAULT_ALERT_LEVELS, KNOWN_LEVELS, LogScopeError, analyze_files


LOG_EXTENSIONS = {".log", ".txt", ".out", ".err"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logscope",
        description="Parse server logs and emit compact JSON or Markdown summaries.",
    )
    parser.add_argument("paths", nargs="+", help="One or more log files or directories to scan.")
    parser.add_argument("-f", "--format", choices=("json", "markdown"), default="json", help="Report format.")
    parser.add_argument("-o", "--output", type=Path, help="Write the report to a file instead of stdout.")
    parser.add_argument(
        "-l",
        "--level",
        action="append",
        choices=[level.lower() for level in KNOWN_LEVELS],
        help="Severity to include. Repeat for multiple levels. Defaults to warning/error/critical.",
    )
    parser.add_argument("--all-levels", action="store_true", help="Include trace/debug/info events too.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recursively scan directories.")
    parser.add_argument("--encoding", default="utf-8", help="Input file encoding. Defaults to utf-8.")
    parser.add_argument("--max-samples", type=int, default=8, help="Maximum sample events in the report.")
    parser.add_argument("--max-patterns", type=int, default=10, help="Maximum grouped message patterns in the report.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        files = resolve_inputs([Path(path) for path in args.paths], recursive=args.recursive)
        levels = KNOWN_LEVELS if args.all_levels else (args.level or DEFAULT_ALERT_LEVELS)
        result = analyze_files(
            files,
            selected_levels=levels,
            encoding=args.encoding,
            max_samples=args.max_samples,
            max_patterns=args.max_patterns,
        )
        output = render_markdown(result.to_dict()) if args.format == "markdown" else json.dumps(result.to_dict(), indent=2)
        write_output(output, args.output)
        return 0
    except LogScopeError as exc:
        parser.exit(1, f"error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "interrupted\n")


def resolve_inputs(paths: list[Path], *, recursive: bool) -> list[Path]:
    files: list[Path] = []

    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.glob("*")
            files.extend(candidate for candidate in candidates if candidate.is_file() and candidate.suffix.lower() in LOG_EXTENSIONS)
            continue
        raise LogScopeError(f"Input path was not found: {path}")

    unique_files = sorted({file.resolve() for file in files})
    if not unique_files:
        raise LogScopeError("No readable log files found. Try passing a file path or using --recursive for directories.")
    return unique_files


def render_markdown(report: dict[str, object]) -> str:
    level_counts = report["level_counts"]
    files = report["files"]
    top_patterns = report["top_patterns"]
    samples = report["samples"]

    lines = [
        "# LogScope Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Lines scanned: **{report['total_lines']}**",
        f"- Matched events: **{report['matched_events']}**",
        f"- Time window: `{report['first_timestamp'] or 'n/a'}` to `{report['last_timestamp'] or 'n/a'}`",
        "",
        "## Severity Breakdown",
        "",
        "| Level | Count |",
        "| --- | ---: |",
    ]

    for level, count in level_counts.items():
        lines.append(f"| {level} | {count} |")

    lines.extend(["", "## Files", "", "| File | Lines | Recognized Events |", "| --- | ---: | ---: |"])
    for file_summary in files:
        lines.append(f"| `{file_summary['path']}` | {file_summary['lines']} | {file_summary['recognized_events']} |")

    lines.extend(["", "## Top Patterns", "", "| Level | Count | Pattern | Example |", "| --- | ---: | --- | --- |"])
    for pattern in top_patterns:
        lines.append(
            f"| {pattern['level']} | {pattern['count']} | `{pattern['pattern']}` | {pattern['example']} |"
        )

    lines.extend(["", "## Samples", ""])
    if not samples:
        lines.append("No matching events found.")
    for sample in samples:
        lines.append(
            f"- `{sample['level']}` {sample.get('timestamp') or 'n/a'} "
            f"`{sample['file']}:{sample['line_number']}` - {sample['message']}"
        )

    return "\n".join(lines) + "\n"


def write_output(content: str, output_path: Path | None) -> None:
    if output_path is None:
        print(content)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
