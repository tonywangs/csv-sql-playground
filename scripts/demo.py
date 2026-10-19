#!/usr/bin/env python3
"""Generate the real-data report offline, optionally reacquiring pinned inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="download exact pinned revisions and verify hashes")
    parser.add_argument("--output", type=Path, default=ROOT / "demo-output")
    args = parser.parse_args()
    data = ROOT / "data" / "population"
    manifest = json.loads((data / "provenance.json").read_text())
    for source in manifest["revisions"].values():
        path = data / source["file"]
        if args.fetch:
            with urllib.request.urlopen(source["url"], timeout=60) as response:
                raw = response.read()
        else:
            raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise SystemExit(f"SHA-256 mismatch for {path}; refusing modified input")
        if args.fetch:
            path.write_bytes(raw)
    subprocess.run([sys.executable, "-m", "csv_reconcile_desk", str(data / "before.csv"),
                    str(data / "after.csv"), "--key", "Country Code", "--key", "Year",
                    "--json", str(args.output / "comparison.json"), "--html",
                    str(args.output / "comparison.html"), "--force"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_population.py"),
                    str(args.output / "comparison.json")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
