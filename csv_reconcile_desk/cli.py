"""CLI and deterministic output serialization."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .core import InputError, read_csv, reconcile


def serialize(result):
    return json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def render_html(result):
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    # A script element is HTML raw text, even when its MIME type is JSON.
    payload = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return template.replace("__REPORT_DATA__", payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reconcile two CSVs without guessing duplicate-key matches.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--key", action="append", required=True, help="exact column name; repeat for composite keys")
    parser.add_argument("--delimiter", default=",", help="one-character delimiter; default comma")
    parser.add_argument("--json", type=Path, default=Path("comparison.json"), dest="json_path")
    parser.add_argument("--html", type=Path, default=Path("comparison.html"), dest="html_path")
    parser.add_argument("--force", action="store_true", help="replace existing report files")
    args = parser.parse_args(argv)
    try:
        if len(args.delimiter) != 1 or args.delimiter in '\r\n\x00"':
            raise InputError("delimiter must be one character other than quote, newline or NUL")
        inputs = {args.before.resolve(), args.after.resolve()}
        outputs = [args.json_path.resolve(), args.html_path.resolve()]
        if len(set(outputs)) != 2 or inputs.intersection(outputs):
            raise InputError("report paths must be distinct and must not overwrite input files")
        existing_pairs = [(output, source) for output in outputs for source in inputs]
        existing_pairs.append(tuple(outputs))
        if any(a.exists() and b.exists() and a.samefile(b) for a, b in existing_pairs):
            raise InputError("report paths must not alias inputs or each other (including hard links)")
        for path in outputs:
            if path.exists() and not args.force:
                raise InputError(f"output exists: {path}; choose another path or use --force")
        result = reconcile(read_csv(args.before, args.delimiter),
                           read_csv(args.after, args.delimiter), args.key)
        result["delimiter"] = args.delimiter
        rendered = (serialize(result), render_html(result))
        for path, content in zip(outputs, rendered):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w" if args.force else "x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        print(f"Accounted for {result['accounting']['before']['input']} before and "
              f"{result['accounting']['after']['input']} after records.")
        for status, counts in result["summary"].items():
            print(f"{status}: {counts['groups']} groups ({counts['before']} before / {counts['after']} after)")
        print(f"JSON: {args.json_path}\nOpen in your browser: {args.html_path}")
        return 0
    except (InputError, OSError, ValueError) as exc:
        print(f"csv-reconcile: {exc}", file=sys.stderr)
        return 2
