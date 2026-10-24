"""One-time preregistration. Run before selecting/evaluating raster points."""
import csv,datetime,hashlib,json,pathlib
out=pathlib.Path('fixtures/reference-plan.json')
if out.exists(): raise SystemExit('Reference already frozen; refusing overwrite.')
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
plan={'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Manual visual reading of rasterized published lines at predefined World years. No y coordinates calculated from reference data or SVG path geometry. Five ordered points per chart; no exclusions, nearest-neighbor rematching, or tolerance adjustment after evaluation.','years':[1960,1980,2000,2020,2023],'matching':'One-to-one by chart and insertion order against the listed years; a missing or extra point is a failure.','tolerance_rationale':'Absolute x tolerance = 2 source pixels times x-axis units/pixel; absolute y tolerance = 3 source pixels times y-axis units/pixel. Budgets allow 1 pixel of anchor reading plus 1 pixel x placement / 2 pixels y line-center placement. These are engineering acceptance thresholds, not confidence intervals. Endpoint extrapolation and line interpolation may add error; failures are retained.','charts':[]}
for slug,x0,x1,y0,y1,v1 in [('population',164,643,512,79,8000000000),('life-expectancy',167,644,532,110,80)]:
    rows={int(r['Year']):r for r in csv.DictReader(open(f'fixtures/owid/{slug}.csv')) if r['Entity']=='World'}
    refs=[{'year':year,'value':float(list(rows[year].values())[-1])} for year in plan['years']]
    plan['charts'].append({'id':slug,'image_sha256':sha(f'fixtures/owid/{slug}.png'),'csv_sha256':sha(f'fixtures/owid/{slug}.csv'),'calibration':{'x':{'scale':'linear','anchors':[{'pixel':x0,'value':1960},{'pixel':x1,'value':2010}]},'y':{'scale':'linear','anchors':[{'pixel':y0,'value':0},{'pixel':y1,'value':v1}]}},'tolerance':{'x':2*50/(x1-x0),'y':3*v1/(y0-y1)},'reference':refs})
out.write_text(json.dumps(plan,indent=2)+'\n')
pathlib.Path('fixtures/reference-plan.sha256').write_text(sha(out)+'  reference-plan.json\n')
print('Reference, matching, calibration and tolerances frozen; no selections evaluated.')
