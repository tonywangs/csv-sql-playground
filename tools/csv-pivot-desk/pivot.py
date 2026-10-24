"""Bounded CSV parsing, exact decimal summaries, portable audit reports."""
import base64
import csv
import hashlib
import html
import io
import json
import re
import zipfile
from decimal import Decimal, localcontext, ROUND_HALF_EVEN

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 40
MAX_GROUPS = 500
NUMBER = re.compile(r'[+-]?(?:[0-9]{1,18}(?:\.[0-9]{1,12})?|\.[0-9]{1,12})\Z')
RULES = {'encoding': 'UTF-8 (optional BOM)', 'dialect': 'comma, double quote escaping, strict parser',
         'number': 'signed base-10, <=18 integer and <=12 fractional digits; no whitespace or exponent',
         'sum': 'exact decimal', 'mean': '12 decimal places, ROUND_HALF_EVEN',
         'missing': 'exact configured tokens; categories always preserved verbatim',
         'ordinal': '1-based parsed data record, including rejected width records',
         'limits': {'bytes': MAX_BYTES, 'records': MAX_ROWS, 'columns': MAX_COLUMNS, 'groups': MAX_GROUPS}}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('CSV must contain 1 byte to 2 MiB.')
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        headers = next(reader)
        if not headers or len(headers) > MAX_COLUMNS or any(not h for h in headers) or len(set(headers)) != len(headers):
            raise ValueError('Use 1–40 nonempty, unique column headers.')
        rows, rejected = [], []
        for ordinal, values in enumerate(reader, 1):
            if ordinal > MAX_ROWS:
                raise ValueError('CSV exceeds 10,000 records; no partial result is available.')
            if any(len(v) > 10000 for v in values):
                raise ValueError('A field exceeds 10,000 characters.')
            if len(values) != len(headers):
                rejected.append({'ordinal': ordinal, 'values': values, 'reason': 'field count does not match header'})
            else:
                rows.append({'ordinal': ordinal, 'values': values})
        return {'headers': headers, 'rows': rows, 'rejected': rejected, 'records': len(rows) + len(rejected)}
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise ValueError('Invalid UTF-8 or CSV syntax; no partial results.') from exc


def default_config(headers):
    return {'types': {h: 'text' for h in headers}, 'row': headers[0], 'column': None,
            'value': None, 'aggregate': 'count', 'missing': [''], 'filters': []}


def validate(config, headers):
    if not isinstance(config, dict) or set(config) != {'types', 'row', 'column', 'value', 'aggregate', 'missing', 'filters'}:
        raise ValueError('Unsupported configuration schema.')
    if not isinstance(config['types'], dict) or set(config['types']) != set(headers) or any(t not in ('text', 'number') for t in config['types'].values()):
        raise ValueError('Declare every column as text or number.')
    if config['row'] not in headers or (config['column'] is not None and config['column'] not in headers):
        raise ValueError('Unknown grouping column.')
    if config['aggregate'] not in ('count', 'sum', 'mean'):
        raise ValueError('Unsupported aggregate.')
    if config['value'] is not None and config['value'] not in headers:
        raise ValueError('Unknown value column.')
    if config['aggregate'] != 'count' and (config['value'] is None or config['types'][config['value']] != 'number'):
        raise ValueError('Sum and mean require an explicitly numeric value column.')
    if not isinstance(config['missing'], list) or len(config['missing']) > 20 or any(not isinstance(s, str) or len(s) > 100 for s in config['missing']):
        raise ValueError('Missing tokens must be a list of at most 20 short strings.')
    if not isinstance(config['filters'], list) or len(config['filters']) > 10:
        raise ValueError('At most 10 filters are supported.')
    for f in config['filters']:
        if not isinstance(f, dict) or set(f) != {'column', 'op', 'value'} or f['column'] not in headers or f['op'] not in ('eq', 'ne', 'contains') or not isinstance(f['value'], str) or len(f['value']) > 10000:
            raise ValueError('Filters support exact equals, not equals, or contains on raw text.')


def number(s, missing):
    if s in missing:
        return 'missing', None
    if not NUMBER.fullmatch(s):
        return 'invalid', None
    return 'valid', Decimal(s)


def decimal_string(d):
    result = format(d, 'f')
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return '0' if d == 0 else result


def analyze(raw, name, config=None, expected_hash=None):
    sha = digest(raw)
    if expected_hash is not None and expected_hash != sha:
        raise ValueError('Source hash mismatch. Reconnect the original unchanged CSV.')
    table = parse(raw)
    headers = table['headers']
    config = default_config(headers) if config is None else config
    validate(config, headers)
    indexes = {h: i for i, h in enumerate(headers)}
    included, filtered, groups = [], [], {}
    for record in table['rows']:
        values = record['values']
        matches = []
        for f in config['filters']:
            v = values[indexes[f['column']]]
            matches.append(v == f['value'] if f['op'] == 'eq' else v != f['value'] if f['op'] == 'ne' else f['value'] in v)
        if not all(matches):
            filtered.append(record['ordinal'])
            continue
        included.append(record)
        key = (values[indexes[config['row']]], values[indexes[config['column']]] if config['column'] else None)
        groups.setdefault(key, []).append(record)
        if len(groups) > MAX_GROUPS:
            raise ValueError('More than 500 observed groups; narrow the configuration. No partial results.')

    def summary(records):
        valid, missing, invalid, nums = [], [], [], []
        if config['value'] is not None and config['types'][config['value']] == 'number':
            for rec in records:
                state, n = number(rec['values'][indexes[config['value']]], config['missing'])
                {'valid': valid, 'missing': missing, 'invalid': invalid}[state].append(rec['ordinal'])
                if n is not None:
                    nums.append(n)
        with localcontext() as ctx:
            ctx.prec = 64
            total = sum(nums, Decimal(0)) if nums else None
            mean = (total / len(nums)).quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_EVEN) if nums else None
        value = str(len(records)) if config['aggregate'] == 'count' else (decimal_string(total) if total is not None else None) if config['aggregate'] == 'sum' else (decimal_string(mean) if mean is not None else None)
        return {'value': value, 'count': len(records), 'valid': len(valid), 'missing': len(missing), 'invalid': len(invalid),
                'ordinals': [r['ordinal'] for r in records], 'valid_ordinals': valid, 'missing_ordinals': missing, 'invalid_ordinals': invalid}

    return {'version': 1, 'source': {'name': str(name)[:200], 'sha256': sha, 'bytes': len(raw)}, 'config': config, 'rules': RULES,
            'headers': headers, 'records': table['rows'], 'rejected': table['rejected'], 'filtered_ordinals': filtered,
            'accounting': {'total': table['records'], 'included': len(included), 'filtered': len(filtered), 'rejected': len(table['rejected'])},
            'groups': [{'row': k[0], 'column': k[1], **summary(v)} for k, v in sorted(groups.items())], 'total': summary(included)}


def project(result):
    return {'version': 1, 'source': result['source'], 'config': result['config']}


def unpack_project(p):
    if not isinstance(p, dict) or set(p) != {'version', 'source', 'config'} or p['version'] != 1 or not isinstance(p['source'], dict) or not re.fullmatch('[0-9a-f]{64}', str(p['source'].get('sha256', ''))):
        raise ValueError('Unsupported project. Expected version 1 and a SHA-256 source identity.')
    return p['config'], p['source']['sha256']


def report_files(result):
    # JSON group labels prevent spreadsheet formula interpretation without changing category identity.
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['scope', 'row_json', 'column_json', 'value', 'count', 'valid', 'missing', 'invalid', 'ordinals_json', 'valid_ordinals_json'])
    for g in result['groups'] + [dict(result['total'], row=None, column=None)]:
        writer.writerow(['total' if g['row'] is None else 'group', json.dumps(g['row'], ensure_ascii=False), json.dumps(g['column'], ensure_ascii=False),
                         '' if g['value'] is None else g['value'], g['count'], g['valid'], g['missing'], g['invalid'], json.dumps(g['ordinals']), json.dumps(g['valid_ordinals'])])
    esc = lambda v: html.escape(str(v), quote=True)
    records = {r['ordinal']: r for r in result['records']}
    sections = []
    for i, g in enumerate(result['groups'] + [dict(result['total'], row='Grand total', column=None)]):
        rows = ''.join('<tr><td>' + str(o) + '</td><td>' + ('valid contributor' if o in g['valid_ordinals'] else 'missing value' if o in g['missing_ordinals'] else 'invalid value' if o in g['invalid_ordinals'] else 'count contributor') + '</td>' + ''.join('<td>' + esc(v) + '</td>' for v in records[o]['values']) + '</tr>' for o in g['ordinals'])
        sections.append(f'<section id="group-{i}"><h2>{esc(json.dumps(g["row"], ensure_ascii=False))} / {esc(json.dumps(g["column"], ensure_ascii=False))}</h2><p class="value">{esc(g["value"] if g["value"] is not None else "Undefined")}</p><p>{g["count"]} records · {g["valid"]} valid · {g["missing"]} missing · {g["invalid"]} invalid</p><details><summary>Inspect {g["count"]} source records</summary><table><thead><tr><th>Record</th><th>Contribution</th>' + ''.join('<th>' + esc(h) + '</th>' for h in result['headers']) + '</tr></thead><tbody>' + rows + '</tbody></table></details></section>')
    audit = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode()
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>CSV Pivot Desk report</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#142e37;background:#f5f7f4}section{background:white;padding:20px;margin:16px 0;border:1px solid #cad8d5}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:6px;white-space:pre-wrap}details{overflow:auto}.value{font-size:30px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>CSV Pivot Desk · portable report</h1><p>Source: ' + esc(result['source']['name']) + '</p><p>SHA-256: ' + esc(result['source']['sha256']) + '</p><p>All record ordinals refer to parsed data records after the header. Numeric contributors exclude missing and invalid values. Categories are JSON strings; null means no column grouping. Undefined is not zero.</p><h2>Accounting</h2><pre>' + esc(json.dumps(result['accounting'], indent=2)) + '</pre><h2>Configuration and rules</h2><pre>' + esc(json.dumps({'config': result['config'], 'rules': result['rules']}, ensure_ascii=False, indent=2)) + '</pre>' + ''.join(sections) + '<h2>Filtered and rejected records</h2><pre>' + esc(json.dumps({'filtered_ordinals': result['filtered_ordinals'], 'rejected': result['rejected']}, ensure_ascii=False, indent=2)) + '</pre></html>'
    files = {'summary.csv': out.getvalue().encode(), 'report.html': document.encode(), 'audit.json': audit,
             'project.json': json.dumps(project(result), ensure_ascii=False, indent=2).encode()}
    manifest = {'version': 1, 'source': result['source'], 'config': result['config'], 'rules': result['rules'], 'accounting': result['accounting'],
                'aggregate_definition': 'count counts included records; sum/mean use valid numeric records only; totals recomputed over all included records',
                'outputs': {name: digest(raw) for name, raw in files.items()}}
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    if any(len(raw) > 10 * 1024 * 1024 for raw in files.values()) or sum(map(len, files.values())) > 24 * 1024 * 1024:
        raise ValueError('Portable report exceeds size limit; filter the source before export.')
    return files


def bundle(result):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in report_files(result).items():
            archive.writestr(name, raw)
    return output.getvalue()
