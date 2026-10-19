#!/usr/bin/env python3
"""Independent verifier: no application imports. Fractions + independent grouping.
Checks every aggregate, source partition, ordinal set, CSV cell, HTML drill-down,
and declared output hash against original CSV bytes.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path


def rounded_mean(value):
    scaled = value * 10**12
    sign = -1 if scaled < 0 else 1
    q, r = divmod(abs(scaled.numerator), scaled.denominator)
    if 2*r > scaled.denominator or (2*r == scaled.denominator and q % 2):
        q += 1
    return Fraction(sign*q, 10**12)


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.groups = []
        self.row = None
        self.cell = None
        self.section = False
        self.summaries = []
        self.capture = None
        self.text = ''
    def handle_starttag(self, tag, attrs):
        if tag == 'section':
            self.section = True
            self.groups.append([])
            self.summaries.append({})
        if self.section and tag in ('h2', 'p'):
            self.capture = 'label' if tag == 'h2' else 'value' if dict(attrs).get('class') == 'value' else 'counts'
            self.text = ''
        if self.section and tag == 'tr':
            self.row = []
        if self.section and tag == 'td':
            self.cell = ''
    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data
        if self.capture is not None:
            self.text += data
    def handle_endtag(self, tag):
        if tag in ('h2', 'p') and self.capture is not None:
            self.summaries[-1][self.capture] = self.text
            self.capture = None
        if tag == 'td' and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        if tag == 'tr' and self.row:
            self.groups[-1].append(self.row)
            self.row = None
        if tag == 'section':
            self.section = False


def verify(source, directory):
    raw = Path(source).read_bytes()
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest['source']['sha256']
    assert len(raw) == manifest['source']['bytes']
    assert set(manifest['outputs']) == {'summary.csv','report.html','audit.json','project.json'}
    for name, sha in manifest['outputs'].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == sha, name
    audit = json.loads((directory / 'audit.json').read_text())
    project = json.loads((directory / 'project.json').read_text())
    assert project == {'version':1,'source':audit['source'],'config':audit['config']}
    for key in ['source','config','rules','accounting']:
        assert manifest[key] == audit[key]
    c = audit['config']
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    headers = next(reader)
    assert headers == audit['headers']
    records, rejected, filtered, included = {}, [], [], []
    grouped = {}
    for ordinal, row in enumerate(reader,1):
        if len(row) != len(headers):
            rejected.append({'ordinal':ordinal,'values':row,'reason':'field count does not match header'})
            continue
        records[ordinal] = row
        values = dict(zip(headers,row))
        keep = True
        for f in c['filters']:
            a,b=values[f['column']],f['value']
            keep &= {'eq':a==b,'ne':a!=b,'contains':b in a}[f['op']]
        if not keep:
            filtered.append(ordinal)
            continue
        included.append(ordinal)
        grouped.setdefault((values[c['row']],values[c['column']] if c['column'] else None),[]).append(ordinal)
    assert audit['records'] == [{'ordinal':i,'values':r} for i,r in records.items()]
    assert audit['rejected'] == rejected
    assert audit['filtered_ordinals'] == filtered
    assert audit['accounting'] == dict(total=len(records)+len(rejected),included=len(included),filtered=len(filtered),rejected=len(rejected))
    assert [(g['row'],g['column']) for g in audit['groups']] == sorted(grouped)
    expected_sets = [grouped[k] for k in sorted(grouped)] + [included]
    outputs = audit['groups'] + [audit['total']]
    for g, ordinals in zip(outputs,expected_sets):
        assert g['ordinals'] == ordinals
        assert g['count'] == len(ordinals)
        valid,missing,invalid,nums = [],[],[],[]
        if c['value'] is not None and c['types'][c['value']] == 'number':
            index = headers.index(c['value'])
            for ordinal in ordinals:
                text = records[ordinal][index]
                if text in c['missing']:
                    missing.append(ordinal)
                else:
                    # Independently validate grammar using split parts rather than engine regex.
                    unsigned = text[1:] if text.startswith(('+','-')) else text
                    pieces = unsigned.split('.')
                    integer_ok = len(pieces[0]) <= 18 and (pieces[0] == '' or all('0' <= ch <= '9' for ch in pieces[0]))
                    decimal_ok = len(pieces) == 1 and bool(pieces[0]) or len(pieces) == 2 and 1 <= len(pieces[1]) <= 12 and all('0' <= ch <= '9' for ch in pieces[1])
                    if not integer_ok or not decimal_ok:
                        invalid.append(ordinal)
                    else:
                        valid.append(ordinal)
                        nums.append(Fraction(text))
        for key, items in [('valid',valid),('missing',missing),('invalid',invalid)]:
            assert g[key] == len(items), (key,g)
            assert g[key+'_ordinals'] == items
        expected = Fraction(len(ordinals)) if c['aggregate'] == 'count' else None if not nums else sum(nums) if c['aggregate'] == 'sum' else rounded_mean(sum(nums)/len(nums))
        assert (None if g['value'] is None else Fraction(g['value'])) == expected, g
    with (directory / 'summary.csv').open(newline='') as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == len(outputs)
    for index,(row,g) in enumerate(zip(csv_rows,outputs)):
        is_total=index==len(outputs)-1
        assert row['scope'] == ('total' if is_total else 'group')
        assert json.loads(row['row_json']) == (None if is_total else g['row'])
        assert json.loads(row['column_json']) == (None if is_total else g['column'])
        assert row['value'] == (g['value'] if g['value'] is not None else '')
        for key in ['count','valid','missing','invalid']:
            assert int(row[key]) == g[key]
        for key in ['ordinals','valid_ordinals']:
            assert json.loads(row[key+'_json']) == g[key]
    parser = ReportParser()
    parser.feed((directory / 'report.html').read_text())
    assert len(parser.groups) == len(outputs)
    for index, (summary, g) in enumerate(zip(parser.summaries, outputs)):
        row = 'Grand total' if index == len(outputs)-1 else g['row']
        column = None if index == len(outputs)-1 else g['column']
        assert summary['label'] == json.dumps(row, ensure_ascii=False) + ' / ' + json.dumps(column, ensure_ascii=False)
        assert summary['value'] == ('Undefined' if g['value'] is None else g['value'])
        assert summary['counts'] == f"{g['count']} records · {g['valid']} valid · {g['missing']} missing · {g['invalid']} invalid"
    for html_rows,g in zip(parser.groups,outputs):
        assert [int(row[0]) for row in html_rows] == g['ordinals']
        for row in html_rows:
            ordinal = int(row[0])
            assert row[2:] == records[ordinal]
            state = 'valid contributor' if ordinal in g['valid_ordinals'] else 'missing value' if ordinal in g['missing_ordinals'] else 'invalid value' if ordinal in g['invalid_ordinals'] else 'count contributor'
            assert row[1] == state
    print(f'Independent verification passed: {len(grouped)} groups, {len(included)} included, {len(filtered)} filtered, {len(rejected)} rejected; all aggregates, ordinal sets, HTML records, CSV cells and hashes.')


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source')
    p.add_argument('report_directory')
    a=p.parse_args()
    verify(a.source,a.report_directory)
