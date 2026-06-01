"""Core parsing and aggregation logic for LogScope."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Iterable


LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}
KNOWN_LEVELS = ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_ALERT_LEVELS = ("WARNING", "ERROR", "CRITICAL")

_LEVEL_WORDS = "CRITICAL|WARNING|TRACE|DEBUG|ERROR|FATAL|WARN|INFO"
_TIMESTAMP = (
    r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_LINE_PATTERN = re.compile(
    rf"^\s*(?:(?P<timestamp>{_TIMESTAMP})\s*)?"
    rf"(?:[-|:]\s*)?(?:\[(?P<bracket_level>{_LEVEL_WORDS})\]|(?P<level>{_LEVEL_WORDS}))"
    rf"(?P<message>.*)$",
    re.IGNORECASE,
)
_FALLBACK_LEVEL_PATTERN = re.compile(rf"(?:\[|\b)(?P<level>{_LEVEL_WORDS})(?:\]|\b)", re.IGNORECASE)
_TIMESTAMP_PATTERN = re.compile(_TIMESTAMP)


class LogScopeError(RuntimeError):
    """Raised when LogScope cannot read or analyze a requested input."""


@dataclass(frozen=True)
class LogEvent:
    """A parsed log line that contains a recognized severity level."""

    file: str
    line_number: int
    level: str
    message: str
    raw: str
    timestamp: str | None = None

    @property
    def fingerprint(self) -> str:
        """Return a stable grouping key that removes noisy IDs and numbers."""

        text = self.message.lower()
        text = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", text)
        text = re.sub(r"\b\d+\b", "<num>", text)
        text = re.sub(r"['\"][^'\"]+['\"]", '"<value>"', text)
        text = re.sub(r"\s+", " ", text).strip(" .:-")
        return text or self.level.lower()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AnalyzeResult:
    """Serializable analysis payload used by the JSON and Markdown renderers."""

    generated_at: str
    selected_levels: list[str]
    files: list[dict[str, object]]
    total_lines: int
    matched_events: int
    level_counts: dict[str, int]
    first_timestamp: str | None
    last_timestamp: str | None
    top_patterns: list[dict[str, object]]
    samples: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_level(level: str) -> str:
    """Normalize aliases such as WARN and FATAL into canonical severities."""

    normalized = level.upper()
    return LEVEL_ALIASES.get(normalized, normalized)


def parse_line(raw_line: str, file_name: str = "<stdin>", line_number: int = 0) -> LogEvent | None:
    """Parse a single log line and return a LogEvent when a severity is found."""

    raw = raw_line.rstrip("\n")
    if not raw.strip():
        return None

    match = _LINE_PATTERN.search(raw)
    if match:
        level = normalize_level(match.group("bracket_level") or match.group("level"))
        timestamp = match.group("timestamp")
        message = _clean_message(match.group("message") or raw)
        return LogEvent(file=file_name, line_number=line_number, level=level, message=message, raw=raw, timestamp=timestamp)

    fallback = _FALLBACK_LEVEL_PATTERN.search(raw)
    if not fallback:
        return None

    level = normalize_level(fallback.group("level"))
    timestamp_match = _TIMESTAMP_PATTERN.search(raw)
    message = _clean_message(raw[fallback.end() :])
    return LogEvent(
        file=file_name,
        line_number=line_number,
        level=level,
        message=message or raw.strip(),
        raw=raw,
        timestamp=timestamp_match.group(0) if timestamp_match else None,
    )


def analyze_files(
    files: Iterable[Path],
    *,
    selected_levels: Iterable[str] = DEFAULT_ALERT_LEVELS,
    encoding: str = "utf-8",
    max_samples: int = 8,
    max_patterns: int = 10,
) -> AnalyzeResult:
    """Analyze one or more files and return aggregate severity metrics."""

    selected = [normalize_level(level) for level in selected_levels]
    selected_set = set(selected)
    file_summaries: list[dict[str, object]] = []
    all_events: list[LogEvent] = []
    total_lines = 0

    for file_path in files:
        summary, events = _read_events(file_path, encoding=encoding)
        total_lines += int(summary["lines"])
        file_summaries.append(summary)
        all_events.extend(event for event in events if event.level in selected_set)

    level_counts = Counter(event.level for event in all_events)
    pattern_counts = Counter(event.fingerprint for event in all_events)
    examples_by_pattern: dict[str, LogEvent] = {}
    timestamps = sorted(event.timestamp for event in all_events if event.timestamp)

    for event in all_events:
        examples_by_pattern.setdefault(event.fingerprint, event)

    top_patterns = [
        {
            "pattern": pattern,
            "count": count,
            "example": examples_by_pattern[pattern].message,
            "level": examples_by_pattern[pattern].level,
        }
        for pattern, count in pattern_counts.most_common(max_patterns)
    ]

    samples = [event.to_dict() for event in all_events[: max(0, max_samples)]]
    return AnalyzeResult(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        selected_levels=selected,
        files=file_summaries,
        total_lines=total_lines,
        matched_events=len(all_events),
        level_counts={level: level_counts.get(level, 0) for level in selected},
        first_timestamp=timestamps[0] if timestamps else None,
        last_timestamp=timestamps[-1] if timestamps else None,
        top_patterns=top_patterns,
        samples=samples,
    )


def _read_events(file_path: Path, *, encoding: str) -> tuple[dict[str, object], list[LogEvent]]:
    if not file_path.exists():
        raise LogScopeError(f"Input does not exist: {file_path}")
    if not file_path.is_file():
        raise LogScopeError(f"Input is not a file: {file_path}")

    events: list[LogEvent] = []
    level_counts: dict[str, int] = defaultdict(int)
    line_count = 0

    try:
        with file_path.open("r", encoding=encoding, errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                line_count += 1
                event = parse_line(line, str(file_path), line_number)
                if event:
                    events.append(event)
                    level_counts[event.level] += 1
    except OSError as exc:
        raise LogScopeError(f"Could not read {file_path}: {exc}") from exc

    return (
        {
            "path": str(file_path),
            "lines": line_count,
            "recognized_events": len(events),
            "levels": dict(sorted(level_counts.items())),
        },
        events,
    )


def _clean_message(value: str) -> str:
    return value.strip().lstrip("-:|] ").strip() or "(no message)"
