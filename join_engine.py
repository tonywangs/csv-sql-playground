"""Exact text joins with preflight accounting; no filesystem mutation."""
import base64
import csv
import hashlib
import io
from collections import defaultdict

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
MAX_OUTPUT = 20000
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(source):
    if not isinstance(source, dict) or not isinstance(source.get('data'), str):
        raise ValueError('Source must contain base64 data.')
    try:
        raw = base64.b64decode(source['data'], validate=True)
    except Exception as exc:
        raise ValueError('Invalid base64 source.') from exc
    if len(raw) > MAX_BYTES:
        raise ValueError('Source exceeds 2 MiB; nothing processed.')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Source must be UTF-8; nothing processed.') from exc
    if '\x00' in text:
        raise ValueError('NUL characters are not accepted.')
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except csv.Error as exc:
        raise ValueError(f'Invalid CSV: {exc}; nothing processed.') from exc
    if not rows or not rows[0] or any(not h for h in rows[0]) or len(set(rows[0])) != len(rows[0]):
        raise ValueError('A nonempty, unique header is required; duplicate/empty headers rejected.')
    headers, rows = rows[0], rows[1:]
    if len(headers) > 100 or len(rows) > MAX_ROWS:
        raise ValueError('Source exceeds 100 columns or 10,000 records; nothing processed.')
    for ordinal, row in enumerate(rows, 1):
        if len(row) != len(headers):
            raise ValueError(f'Record {ordinal} has {len(row)} fields, expected {len(headers)}; whole file rejected.')
    return {'name': str(source.get('name', 'source.csv'))[:200], 'sha256': sha(raw), 'bytes': len(raw), 'headers': headers, 'rows': rows}


def describe(table):
    return {**{k: v for k, v in table.items() if k != 'rows'}, 'records': len(table['rows']), 'sample': table['rows'][:5]}


def validate(config, tables):
    if not isinstance(config, dict):
        raise ValueError('Configuration must be an object.')
    if config.get('join') not in ['inner', 'left', 'full'] or config.get('relationship') not in ['one-to-one', 'many-to-one', 'unrestricted']:
        raise ValueError('Choose a valid join and relationship.')
    for side in ['left', 'right']:
        keys = config.get(side + '_keys')
        columns = config.get(side + '_columns')
        for values in [keys, columns]:
            if not isinstance(values, list) or any(type(i) is not int or i < 0 or i >= len(tables[side]['headers']) for i in values) or len(set(values)) != len(values):
                raise ValueError('Keys/columns must be unique valid column indexes.')
        if not keys:
            raise ValueError('Select at least one key on each side.')
    if len(config['left_keys']) != len(config['right_keys']):
        raise ValueError('Composite keys must have the same number of components in corresponding order.')
    if type(config.get('limit')) is not int or not 1 <= config['limit'] <= MAX_OUTPUT:
        raise ValueError('Output limit must be an integer from 1 to 20,000.')
    if type(config.get('acknowledge_many_to_many')) is not bool:
        raise ValueError('Expansion acknowledgment must be true or false.')
    return {k: config[k] for k in ['join', 'relationship', 'left_keys', 'right_keys', 'left_columns', 'right_columns', 'limit', 'acknowledge_many_to_many']}


def analyze(tables, config):
    config = validate(config, tables)
    indexes, missing = {}, {}
    for side, table in tables.items():
        groups = defaultdict(list); absent = []
        for ordinal, row in enumerate(table['rows'], 1):
            key = tuple(row[i] for i in config[side + '_keys'])
            if '' in key:
                absent.append(ordinal)
            else:
                groups[key].append(ordinal)
        indexes[side], missing[side] = groups, absent
    left, right = indexes['left'], indexes['right']
    keys = list(dict.fromkeys([*left, *right]))
    groups = [{'key': list(k), 'left': left.get(k, []), 'right': right.get(k, []), 'pairs': len(left.get(k, [])) * len(right.get(k, []))} for k in keys]
    unmatched = {s: sorted(missing[s] + [i for k, ids in indexes[s].items() if k not in indexes['right' if s == 'left' else 'left'] for i in ids]) for s in tables}
    matched_pairs = sum(g['pairs'] for g in groups)
    expected = matched_pairs + (len(unmatched['left']) if config['join'] != 'inner' else 0) + (len(unmatched['right']) if config['join'] == 'full' else 0)
    duplicates = {s: sum(len(v) > 1 for v in indexes[s].values()) for s in tables}
    expansion = [g for g in groups if len(g['left']) > 1 and len(g['right']) > 1]
    errors = []
    if config['relationship'] == 'one-to-one' and any(duplicates.values()):
        errors.append('One-to-one requires unique nonmissing keys on both sides.')
    if config['relationship'] == 'many-to-one' and duplicates['right']:
        errors.append('Many-to-one requires unique nonmissing keys on the right.')
    if expansion and not config['acknowledge_many_to_many']:
        errors.append('Acknowledge many-to-many expansion before executing.')
    if expected > config['limit']:
        errors.append(f'Expected {expected:,} rows exceeds output limit {config["limit"]:,}.')
    # Conservative UTF-8 CSV bound, computed by multiplicity without materializing pairs.
    bound = 4096 + expected * (32 + len(config['left_columns']) + len(config['right_columns']))
    for side in tables:
        other = 'right' if side == 'left' else 'left'
        for row in tables[side]['rows']:
            key = tuple(row[i] for i in config[side + '_keys'])
            copies = len(indexes[other].get(key, [])) if '' not in key else 0
            if copies == 0 and (side == 'left' and config['join'] != 'inner' or side == 'right' and config['join'] == 'full'):
                copies = 1
            bound += copies * sum(len(row[i].encode('utf-8')) + row[i].count('"') + 2 for i in config[side + '_columns'])
    bound += sum(len(h.encode('utf-8')) * 2 + 20 for t in tables.values() for h in t['headers'])
    if bound > MAX_OUTPUT_BYTES:
        errors.append('Conservative output size exceeds 8 MiB; reduce columns or inputs.')
    counts = {'left_records': len(tables['left']['rows']), 'right_records': len(tables['right']['rows']), 'matched_pairs': matched_pairs, 'expected_rows': expected, 'unmatched_left': len(unmatched['left']), 'unmatched_right': len(unmatched['right']), 'missing_left': len(missing['left']), 'missing_right': len(missing['right']), 'duplicate_left_keys': duplicates['left'], 'duplicate_right_keys': duplicates['right'], 'many_to_many_keys': len(expansion)}
    return {'config': config, 'counts': counts, 'groups': groups, 'missing': missing, 'unmatched': unmatched, 'errors': errors, 'output_byte_upper_bound': bound}


def execute(tables, config):
    report = analyze(tables, config)
    if report['errors']:
        raise ValueError(' '.join(report['errors']))
    config = report['config']; right_index = defaultdict(list)
    for i, row in enumerate(tables['right']['rows'], 1):
        key = tuple(row[k] for k in config['right_keys'])
        if '' not in key: right_index[key].append(i)
    pairs = []; seen = set()
    for i, row in enumerate(tables['left']['rows'], 1):
        key = tuple(row[k] for k in config['left_keys'])
        matches = right_index.get(key, []) if '' not in key else []
        for j in matches:
            pairs.append([i, j]); seen.add(j)
        if not matches and config['join'] != 'inner': pairs.append([i, None])
    if config['join'] == 'full':
        pairs.extend([None, j] for j in range(1, len(tables['right']['rows']) + 1) if j not in seen)
    headers = ['_left_record', '_right_record'] + [f'{side}.{tables[side]["headers"][i]}' for side in ['left', 'right'] for i in config[side + '_columns']]
    output = io.StringIO(newline=''); writer = csv.writer(output); writer.writerow(headers)
    preview = []
    for pair in pairs:
        row = ['' if i is None else str(i) for i in pair]
        for side, ordinal in zip(['left', 'right'], pair):
            row.extend('' if ordinal is None else tables[side]['rows'][ordinal - 1][i] for i in config[side + '_columns'])
        writer.writerow(row)
        if len(preview) < 100: preview.append(row)
    raw = output.getvalue().encode('utf-8')
    assert len(pairs) == report['counts']['expected_rows'] and len(raw) <= report['output_byte_upper_bound']
    manifest = {'schema': 'csv-join-desk/1', 'semantics': 'exact-text; empty component never matches; ordinals are 1-based data records; left-major then unmatched right', 'sources': {s: {k: t[k] for k in ['name', 'sha256', 'bytes', 'headers']} for s, t in tables.items()}, 'config': config, 'counts': report['counts'], 'unmatched': report['unmatched'], 'missing': report['missing'], 'pairs': pairs, 'output': {'sha256': sha(raw), 'bytes': len(raw), 'rows': len(pairs), 'headers': headers}}
    return {'csv': output.getvalue(), 'manifest': manifest, 'preview': preview, 'headers': headers}


def request(body):
    tables = {s: parse(body[s]) for s in ['left', 'right']}
    if body.get('action') == 'inspect': return {s: describe(t) for s, t in tables.items()}
    if body.get('action') == 'analyze':
        report = analyze(tables, body.get('config'))
        report['unmatched_records'] = {s: [[i, *tables[s]['rows'][i - 1]] for i in report['unmatched'][s]] for s in tables}
        return report
    if body.get('action') == 'execute': return execute(tables, body.get('config'))
    raise ValueError('Unknown action.')
