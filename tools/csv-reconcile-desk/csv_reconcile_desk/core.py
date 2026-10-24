"""Reconcile CSV records as multisets within explicitly selected keys."""
from collections import defaultdict, deque
import csv
import hashlib
import io
from pathlib import Path


class InputError(ValueError):
    """An input cannot be safely reconciled."""


def read_csv(path, delimiter=","):
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"{path}: expected UTF-8 text (UTF-8 BOM is allowed)") from exc
    if "\x00" in text:
        raise InputError(f"{path}: NUL bytes are not supported")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        columns = next(reader, None)
        if not columns or any(not name.strip() for name in columns):
            raise InputError(f"{path}: a header with nonempty column names is required")
        if len(columns) != len(set(columns)):
            raise InputError(f"{path}: duplicate column names are not supported")
        records = []
        previous_line = reader.line_num
        for values in reader:
            start = previous_line + 1
            previous_line = reader.line_num
            if len(values) != len(columns):
                raise InputError(
                    f"{path}: lines {start}-{reader.line_num}: expected {len(columns)} "
                    f"fields, got {len(values)} (blank records are not silently skipped)"
                )
            records.append({"row": len(records) + 1, "line_start": start,
                            "line_end": reader.line_num,
                            "values": dict(zip(columns, values))})
    except csv.Error as exc:
        raise InputError(f"{path}: CSV error near line {reader.line_num}: {exc}") from exc
    return {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "columns": columns, "records": records}


def reconcile(before, after, keys):
    if not keys or len(keys) != len(set(keys)):
        raise InputError("select one or more distinct key columns using --key")
    for label, source in (("before", before), ("after", after)):
        missing = [key for key in keys if key not in source["columns"]]
        if missing:
            raise InputError(f"{label}: key columns absent from header: {missing}")
    all_columns = list(dict.fromkeys(before["columns"] + after["columns"]))
    groups = [defaultdict(list), defaultdict(list)]
    missing_keys = [[], []]
    for index, source in enumerate((before, after)):
        for row in source["records"]:
            key = tuple(row["values"][column] for column in keys)
            if any(value == "" for value in key):
                missing_keys[index].append(row)
            else:
                groups[index][key].append(row)
    events = []
    duplicates = []

    def emit(status, key, left, right, reason=None):
        event = {"id": len(events) + 1, "status": status,
                 "key": list(key) if key is not None else None,
                 "before": left, "after": right}
        if reason:
            event["reason"] = reason
        if status == "changed":
            event["changes"] = [
                {"column": c, "before": left[0]["values"].get(c),
                 "after": right[0]["values"].get(c)}
                for c in all_columns
                if left[0]["values"].get(c) != right[0]["values"].get(c)
            ]
        events.append(event)

    def signature(row):
        return tuple(row["values"].get(column) for column in all_columns)

    for key in sorted(set(groups[0]) | set(groups[1])):
        left, right = groups[0][key], groups[1][key]
        if len(left) > 1 or len(right) > 1:
            duplicates.append({"key": list(key), "before_count": len(left),
                               "after_count": len(right)})
        buckets = defaultdict(deque)
        for row in right:
            buckets[signature(row)].append(row)
        remaining_left, used_right = [], set()
        for row in left:
            bucket = buckets[signature(row)]
            if bucket:
                match = bucket.popleft()
                used_right.add(match["row"])
                emit("unchanged", key, [row], [match])
            else:
                remaining_left.append(row)
        remaining_right = [row for row in right if row["row"] not in used_right]
        if remaining_left and remaining_right:
            if len(left) == len(right) == 1:
                emit("changed", key, remaining_left, remaining_right)
            else:
                emit("unresolved", key, remaining_left, remaining_right, "duplicate_key")
        elif remaining_left:
            for row in remaining_left:
                emit("removed", key, [row], [])
        elif remaining_right:
            for row in remaining_right:
                emit("added", key, [], [row])
    # Missing keys never establish identity, even for otherwise equal records.
    for side, rows in enumerate(missing_keys):
        for row in rows:
            emit("unresolved", None, [row] if side == 0 else [],
                 [row] if side == 1 else [], "missing_key")
    counts = {status: {"groups": 0, "before": 0, "after": 0}
              for status in ("unchanged", "changed", "added", "removed", "unresolved")}
    for event in events:
        count = counts[event["status"]]
        count["groups"] += 1
        count["before"] += len(event["before"])
        count["after"] += len(event["after"])
    sources = {}
    for side, source in (("before", before), ("after", after)):
        refs = [row["row"] for event in events for row in event[side]]
        if sorted(refs) != list(range(1, len(source["records"]) + 1)):
            raise RuntimeError(f"internal accounting error: {side}")
        sources[side] = {k: v for k, v in source.items() if k != "records"}
        sources[side]["record_count"] = len(source["records"])
    return {"format_version": 1, "keys": list(keys), "sources": sources,
            "schema": {"added": [c for c in after["columns"] if c not in before["columns"]],
                       "removed": [c for c in before["columns"] if c not in after["columns"]],
                       "order_changed": before["columns"] != after["columns"] and
                       set(before["columns"]) == set(after["columns"])},
            "summary": counts, "duplicate_keys": duplicates,
            "accounting": {side: {"input": sources[side]["record_count"],
                                  "accounted": sum(c[side] for c in counts.values())}
                           for side in ("before", "after")},
            "events": events}
