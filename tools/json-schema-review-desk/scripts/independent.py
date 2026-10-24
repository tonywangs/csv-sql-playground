"""Independent draft-07, format-annotation comparison and pointer verification."""
import json,hashlib,pathlib,importlib.metadata
from jsonschema import Draft7Validator
root=pathlib.Path(__file__).resolve().parents[1]
schema=json.loads((root/'public/demo/vega-schema.json').read_bytes())
Draft7Validator.check_schema(schema)
validator=Draft7Validator(schema,format_checker=None)
def pointer(v,p):
    for k in p.split('/')[1:] if p else []:
        k=k.replace('~1','/').replace('~0','~');v=v[int(k)] if isinstance(v,list) else v[k]
    return v
results=[]
reports=json.loads((root/'results/sample-reports.json').read_text())
if (root/'results/browser-report.json').exists():
    reports.append(json.loads((root/'results/browser-report.json').read_text()))
for report in reports:
    path=root/'public/demo'/report['document']['name'];b=path.read_bytes();d=json.loads(b)
    assert hashlib.sha256(b).hexdigest()==report['document']['hash']
    assert hashlib.sha256((root/'public/demo/vega-schema.json').read_bytes()).hexdigest()==report['resources'][0]['hash']
    errors=list(validator.iter_errors(d));actual='invalid-document' if errors else 'valid'
    assert actual==report['status'] and report['coverage']=='complete'
    for f in report['findings']:
        assert pointer(d,f['documentPointer'])==f['value']
        assert pointer(schema,f['schemaPointer'])==f['rule']
    # Compare atomic leaves; aggregating combinator errors differ in presentation.
    def leaves(es):
        for e in es:
            if e.context:yield from leaves(e.context)
            else:yield (tuple(e.absolute_path),e.validator)
    independent=set(leaves(errors))
    # Paths as RFC6901 remove Python's int-vs-string indexing distinction.
    esc=lambda x:str(x).replace('~','~0').replace('/','~1')
    independent={(('/'+'/'.join(map(esc,p))) if p else '',kw) for p,kw in independent}
    ajv={(f['documentPointer'],f['keyword']) for f in report['findings'] if f['keyword'] not in ('anyOf','oneOf')}
    assert independent==ajv,(independent-ajv,ajv-independent)
    results.append(dict(document=path.name,status=actual,independentTopLevelErrors=len(errors),ajvFindings=len(report['findings']),pointersVerified=True,leafFailuresAgree=True))
print(json.dumps(dict(validator='python-jsonschema '+importlib.metadata.version('jsonschema'),dialect='draft-07',formats='annotation only',results=results),indent=2))
