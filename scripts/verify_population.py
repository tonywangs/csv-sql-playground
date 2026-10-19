#!/usr/bin/env python3
"""Independent SQLite oracle for the complete pinned real-data comparison.

Does not import the reconciliation engine. Checks source hashes, keys, every
classification, every cell, every row reference, field diffs and accounting.
This oracle deliberately requires unique keys, as present in these revisions.
"""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(report_path):
    manifest = json.loads((ROOT / "data/population/provenance.json").read_text())
    report = json.loads(Path(report_path).read_text())
    assert report["keys"] == manifest["key"]
    db = sqlite3.connect(":memory:")
    rows_by_side = {}
    for side in ("before", "after"):
        spec = manifest["revisions"][side]
        path = ROOT / "data/population" / spec["file"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        # These real revisions have one record per physical line; explicitly
        # check that property instead of assuming line numbers equal row+1.
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(raw.splitlines()) == len(rows) + 1
        assert len(rows) == spec["records"]
        rows_by_side[side] = rows
        assert report["sources"][side] == {
            "name": spec["file"], "sha256": spec["sha256"], "bytes": len(raw),
            "columns": list(rows[0]), "record_count": len(rows)}
        db.execute(f'CREATE TABLE "{side}" (code TEXT, year TEXT, name TEXT, value TEXT, rownum INTEGER, PRIMARY KEY(code,year))')
        db.executemany(f'INSERT INTO "{side}" VALUES (?,?,?,?,?)',
                       [(r["Country Code"], r["Year"], r["Country Name"], r["Value"], n)
                        for n, r in enumerate(rows, 1)])
    expected = {}
    for code, year, name, value, rownum in db.execute('SELECT * FROM "before" WHERE NOT EXISTS (SELECT 1 FROM "after" WHERE "after".code="before".code AND "after".year="before".year)'):
        expected[(code, year)] = ("removed", rownum, None)
    for code, year, name, value, rownum in db.execute('SELECT * FROM "after" WHERE NOT EXISTS (SELECT 1 FROM "before" WHERE "before".code="after".code AND "before".year="after".year)'):
        expected[(code, year)] = ("added", None, rownum)
    for code, year, oldrow, newrow, equal in db.execute('SELECT b.code,b.year,b.rownum,a.rownum,(b.name=a.name AND b.value=a.value) FROM "before" b JOIN "after" a ON b.code=a.code AND b.year=a.year'):
        expected[(code, year)] = ("unchanged" if equal else "changed", oldrow, newrow)
    counts = {s: {"groups": 0, "before": 0, "after": 0}
              for s in ("unchanged", "changed", "added", "removed", "unresolved")}
    seen = {"before": set(), "after": set()}
    assert len(report["events"]) == len(expected)
    for event_id, event in enumerate(report["events"], 1):
        assert event["id"] == event_id
        status, oldrow, newrow = expected.pop(tuple(event["key"]))
        assert event["status"] == status
        counts[status]["groups"] += 1
        for side, rownum in (("before", oldrow), ("after", newrow)):
            if rownum is None:
                assert event[side] == []
            else:
                assert event[side] == [{"row": rownum, "line_start": rownum + 1,
                                        "line_end": rownum + 1,
                                        "values": rows_by_side[side][rownum - 1]}]
                assert rownum not in seen[side]
                seen[side].add(rownum)
                counts[status][side] += 1
        if status == "changed":
            old = rows_by_side["before"][oldrow - 1]
            new = rows_by_side["after"][newrow - 1]
            assert event["changes"] == [{"column": c, "before": old[c], "after": new[c]}
                                         for c in old if old[c] != new[c]]
    assert not expected
    assert report["summary"] == counts
    assert report["duplicate_keys"] == []
    assert report["schema"] == {"added": [], "removed": [], "order_changed": False}
    for side in seen:
        total = len(rows_by_side[side])
        assert seen[side] == set(range(1, total + 1))
        assert report["accounting"][side] == {"input": total, "accounted": total}
    db.close()
    print("Independent SQLite verification passed: every classification, value, source reference and count.")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    verify(sys.argv[1] if len(sys.argv) > 1 else ROOT / "demo-output/comparison.json")
