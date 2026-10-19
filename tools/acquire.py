"""Rebuild the JSONL fixture from pinned GeoJSON; --fetch refreshes upstream."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2024-01-01&endtime=2024-01-02&minmagnitude=2.5&orderby=time-asc'
POLICY = 'https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits'


def convert(raw):
    obj = json.loads(raw)
    return b''.join((json.dumps(feature, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8') for feature in obj['features'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Replace pinned source and provenance with current catalog revision')
    parser.add_argument('--check', action='store_true', help='Check pinned conversion and hashes without writes or network')
    args = parser.parse_args()
    source = ROOT / 'data/usgs-source.geojson'
    if args.fetch:
        with urllib.request.urlopen(URL, timeout=60) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024: raise ValueError('Upstream unexpectedly large')
        source.write_bytes(raw)
    raw = source.read_bytes()
    output = convert(raw)
    hashes = {'source_sha256': hashlib.sha256(raw).hexdigest(), 'jsonl_sha256': hashlib.sha256(output).hexdigest()}
    if args.check:
        saved = json.loads((ROOT / 'data/PROVENANCE.json').read_text())
        assert all(saved[k] == v for k, v in hashes.items())
        assert (ROOT / 'data/earthquakes.jsonl').read_bytes() == output
        assert saved['records'] == len(json.loads(raw)['features'])
        print('Pinned source hashes and deterministic GeoJSON → JSONL conversion verified')
        return
    (ROOT / 'data/earthquakes.jsonl').write_bytes(output)
    doc = {'credit': 'U.S. Geological Survey, Department of the Interior', 'source_url': URL,
           'format_documentation': 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php',
           'acquired_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'revision': {'catalog_metadata': json.loads(raw)['metadata'], 'identity': 'SHA-256 of retained GeoJSON response; catalog events may be revised upstream'},
           'rights': {'status': 'USGS-produced data: U.S. Public Domain', 'policy_url': POLICY,
                     'evidence_excerpt': 'USGS-authored or produced data and information are considered to be in the U.S. Public Domain.',
                     'scope': 'Event catalog data only; no third-party photographs, illustrations or branding included.'},
           'conversion': 'Each GeoJSON features[] object is serialized by Python json.dumps(ensure_ascii=False,separators=(comma,colon),allow_nan=False), UTF-8, followed by LF. Feature order and nested data retained. These JSONL bytes are a conversion, not the original HTTP bytes.',
           'records': len(json.loads(raw)['features']), **hashes,
           'reproduce_pinned': ['python3', 'tools/acquire.py', '--check'],
           'refresh_upstream': ['python3', 'tools/acquire.py', '--fetch']}
    (ROOT / 'data/PROVENANCE.json').write_text(json.dumps(doc, indent=2) + '\n')
    print(f"Converted {doc['records']} USGS features; {len(output)} JSONL bytes")


if __name__ == '__main__': main()
