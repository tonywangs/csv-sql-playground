"""Generate the same full-outer real-data export as the browser demo."""
import base64, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from join_engine import request
sources = {s: {'name': n, 'data': base64.b64encode((ROOT / 'data' / n).read_bytes()).decode()} for s, n in [('left','airports.csv'), ('right','countries.csv')]}
config = {'left_keys':[8], 'right_keys':[1], 'left_columns':[1,3,8,10], 'right_columns':[1,2,3], 'join':'full', 'relationship':'many-to-one', 'limit':10000, 'acknowledge_many_to_many':False}
result = request({'action':'execute', **sources, 'config':config})
(ROOT / 'examples' / 'joined.csv').write_bytes(result['csv'].encode())
(ROOT / 'examples' / 'joined.manifest.json').write_text(json.dumps(result['manifest'], indent=2) + '\n')
print(result['manifest']['counts'])
