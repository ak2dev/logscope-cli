# LogScope CLI

LogScope is a small, production-minded command-line utility for turning noisy server logs into clean JSON or Markdown incident summaries. It recognizes common severity labels, normalizes aliases such as `WARN` and `FATAL`, groups repeated error patterns, and surfaces representative samples that are useful during triage.

## Why It Exists

Reading logs by hand is slow when you only need the answer to three practical questions:

- Which warnings and errors are happening?
- Are multiple lines really the same underlying issue?
- What examples should go into an incident note or pull request?

LogScope answers those questions without a database, agent, or external service.

## Tech Stack

- Python 3.10+
- Standard library only: `argparse`, `json`, `pathlib`, `re`, `dataclasses`, `unittest`
- Installable console script via `pyproject.toml`

## File Structure

```text
logscope-cli/
├── README.md
├── pyproject.toml
├── .gitignore
├── examples/
│   └── sample.log
├── src/
│   └── logscope/
│       ├── __init__.py
│       ├── analyzer.py
│       └── cli.py
└── tests/
    └── test_analyzer.py
```

## Prerequisites

- Python 3.10 or newer
- `pip` for editable installation

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Usage

Generate a JSON report from a single log file:

```bash
logscope examples/sample.log
```

Generate a Markdown report:

```bash
logscope examples/sample.log --format markdown --output reports/incident-summary.md
```

Scan a directory recursively:

```bash
logscope ./logs --recursive --format json --output reports/logscope.json
```

Include every recognized severity level:

```bash
logscope examples/sample.log --all-levels
```

Focus on errors only:

```bash
logscope examples/sample.log --level error --format markdown
```

## Example JSON Output

```json
{
  "matched_events": 4,
  "level_counts": {
    "WARNING": 1,
    "ERROR": 2,
    "CRITICAL": 1
  },
  "top_patterns": [
    {
      "pattern": "payment provider returned <num> for order <num>",
      "count": 2,
      "example": "payment provider returned 502 for order 99231",
      "level": "ERROR"
    }
  ]
}
```

## Testing

```bash
PYTHONPATH=src python -m unittest
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest
```

## License

MIT. See [LICENSE](LICENSE).

## Suggested Commit History

1. `chore: scaffold logscope cli package`
2. `feat: parse log severities and aggregate summaries`
3. `feat: add json and markdown report output`
4. `test: cover parser normalization and grouped patterns`
