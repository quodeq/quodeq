"""Export command: writes a report to a user-supplied path."""
import sys
from pathlib import Path


def main():
    # dest is read from a command-line argument.
    dest = sys.argv[1]
    report = build_report()
    Path(dest).write_text(report, encoding="utf-8")


def build_report() -> str:
    return "report contents"


if __name__ == "__main__":
    main()
