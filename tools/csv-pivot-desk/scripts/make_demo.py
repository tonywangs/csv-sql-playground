#!/usr/bin/env python3
"""Generate reproducible real-data portable sample outputs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pivot import analyze, report_files
ROOT = Path(__file__).resolve().parents[1]
raw = (ROOT / 'data/penguins.csv').read_bytes()
c = analyze(raw, 'penguins.csv')['config']
c.update(column='island', value='body_mass_g', aggregate='mean', missing=['', 'NA'])
c['types']['body_mass_g'] = 'number'
result = analyze(raw, 'penguins.csv', c)
for name, content in report_files(result).items():
    (ROOT / 'examples' / name).write_bytes(content)
print('Wrote sample reports for', result['accounting'])
