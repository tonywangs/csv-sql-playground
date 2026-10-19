"""Independent standard-library CSV parser and coordinate/error verification.
Does not import application math. Uses endpoint interpolation (ln-space for logs).
"""
import argparse,csv,hashlib,json,math,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--exports',default='samples');p.add_argument('--write-report',action='store_true');p.add_argument('--require-tolerances',action='store_true',help='Exit 1 for any measured tolerance miss (the frozen experiment has one).');a=p.parse_args()
load=lambda p:json.loads((ROOT/p).read_text())
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def check(ok,message):
    if not ok: raise AssertionError(message)
def independent(axis,pixel):
    u,v=axis['anchors']; fraction=(pixel-u['pixel'])/(v['pixel']-u['pixel'])
    if axis['scale']=='linear': return (1-fraction)*u['value']+fraction*v['value']
    return math.exp((1-fraction)*math.log(u['value'])+fraction*math.log(v['value']))
for manifest in ['fixtures/owid/provenance.json','fixtures/owid/rasterization.json']:
    for f in load(manifest)['files']: check(sha('fixtures/owid/'+f['file'])==f['sha256'],'Source hash mismatch: '+f['file'])
check(sha('fixtures/reference-plan.json')==(ROOT/'fixtures/reference-plan.sha256').read_text().split()[0],'Frozen reference plan changed')
plan=load('fixtures/reference-plan.json'); selections=load('fixtures/selections.json')['charts']; report=[]; failures=[]
for chart in plan['charts']:
    slug=chart['id']; stem=pathlib.Path(a.exports)/slug
    project=load(str(stem)+'.project.json'); manifest=load(str(stem)+'.manifest.json')
    check(project['calibration']==chart['calibration'],'Calibration differs from frozen reference')
    check(project['image']['sha256']==chart['image_sha256']==sha(f'fixtures/owid/{slug}.png'),'Image identity mismatch')
    check(sha(f'fixtures/owid/{slug}.csv')==chart['csv_sha256'],'Reference CSV changed')
    check(manifest['image']==project['image'] and manifest['calibration']==project['calibration'],'Manifest identity/calibration mismatch')
    check(manifest['series']==project['series'],'Manifest series mismatch')
    for name,suffix in [('points.csv','.csv'),('project.json','.project.json')]: check(sha(str(stem)+suffix)==manifest['outputs'][name]['sha256'],'Output hash mismatch: '+name)
    rows=list(csv.DictReader((ROOT/(str(stem)+'.csv')).open(newline='')))
    check(len(rows)==len(chart['reference'])==len(project['points'])==len(manifest['points']),'Missing or extra selections')
    original={int(r['Year']):float(list(r.values())[-1]) for r in csv.DictReader((ROOT/f'fixtures/owid/{slug}.csv').open()) if r['Entity']=='World'}
    records=[]
    for i,(r,p,mp,ref,selection) in enumerate(zip(rows,project['points'],manifest['points'],chart['reference'],selections[slug]),1):
        check([p['px'],p['py']]==selection,'Selections changed after freezing')
        check(original[ref['year']]==ref['value'],'Reference not found in original source data')
        check(r['point_id']==p['id']==mp['id'] and r['series_id']==p['series']==mp['series'],'Point identity mismatch')
        check(r['series']==next(s['name'] for s in project['series'] if s['id']==p['series']),'Series label mismatch')
        check(int(r['order'])==i,'Point order mismatch')
        for key,pkey in [('pixel_x','px'),('pixel_y','py')]:check(float(r[key])==p[pkey]==mp[pkey],'Pixel mismatch')
        x=independent(project['calibration']['x'],p['px']);y=independent(project['calibration']['y'],p['py'])
        check(math.isclose(float(r['approximate_x']),x,rel_tol=1e-12,abs_tol=1e-10),'Independent X transform mismatch')
        check(math.isclose(float(r['approximate_y']),y,rel_tol=1e-12,abs_tol=1e-10),'Independent Y transform mismatch')
        check(math.isclose(mp['x'],x,rel_tol=1e-12) and math.isclose(mp['y'],y,rel_tol=1e-12),'Manifest values mismatch')
        ex=x-ref['year'];ey=y-ref['value'];passed=abs(ex)<=chart['tolerance']['x'] and abs(ey)<=chart['tolerance']['y']
        record={'point':i,'reference_x':ref['year'],'reference_y':ref['value'],'pixel_x':p['px'],'pixel_y':p['py'],'approximate_x':x,'approximate_y':y,'signed_error_x':ex,'signed_error_y':ey,'absolute_error_x':abs(ex),'absolute_error_y':abs(ey),'within_tolerance':passed}
        records.append(record)
        if not passed:failures.append({'chart':slug,**record})
    report.append({'chart':slug,'tolerance':chart['tolerance'],'max_absolute_error_x':max(r['absolute_error_x'] for r in records),'max_absolute_error_y':max(r['absolute_error_y'] for r in records),'mae_y':sum(r['absolute_error_y'] for r in records)/len(records),'rmse_y':math.sqrt(sum(r['signed_error_y']**2 for r in records)/len(records)),'points':records})
# Synthetic controls supplement the real-chart evaluation. Independently computed here.
controls=json.loads(subprocess.check_output(['node','scripts/control-results.mjs'],cwd=ROOT))
for c in controls:
    if c['valid']:
        expected=independent(c['axis'],c['pixel']);check(math.isclose(c['result'],expected,rel_tol=1e-12,abs_tol=1e-10),'Control transform mismatch: '+c['name'])
        check(math.isclose(c['result'],c['expected'],rel_tol=1e-12,abs_tol=1e-10),'Control expected value mismatch')
    else: check(c['rejected'],'Invalid calibration accepted: '+c['name'])
result={'reference_plan_sha256':sha('fixtures/reference-plan.json'),'method':'Independent Python csv.DictReader; endpoint interpolation in linear or natural-log space. No application transformation imports. All points retained.','charts':report,'failed_tolerances':failures,'synthetic_controls':controls}
if a.write_report:
    (ROOT/'results/accuracy.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Real-chart digitization error','', 'Ten manually selected points from two published Our World in Data charts, World 1950–2023. Source: UN World Population Prospects 2024, processed by OWID. These are digitized estimates, not original measurements.','', 'The reference years, one-to-one insertion-order matching, calibration, and tolerances were frozen in `fixtures/reference-plan.json` before selections and evaluation. `fixtures/selections.json` records visual raster readings, not coordinates calculated from reference values.','', 'Independent verification uses Python’s CSV parser and endpoint interpolation, separately from the JavaScript application. Every selected point is reported below; no outliers were excluded.','']
    for c in report:
        lines += [f"## {c['chart']}",'',f"Absolute tolerances: X ≤ {c['tolerance']['x']:.6g} years; Y ≤ {c['tolerance']['y']:.9g}. X uses 2 source pixels and Y uses 3. Population Y units are people; life-expectancy Y units are years.",'','| Reference year | Source value | Selected pixels | Approx. X | Approx. Y | Signed X error | Signed Y error | Pass |','|---:|---:|:---|---:|---:|---:|---:|:---|']
        for r in c['points']:lines.append(f"| {r['reference_x']} | {r['reference_y']:.10g} | {r['pixel_x']}, {r['pixel_y']} | {r['approximate_x']:.9g} | {r['approximate_y']:.10g} | {r['signed_error_x']:.6g} | {r['signed_error_y']:.9g} | {'yes' if r['within_tolerance'] else 'NO'} |")
        lines += ['',f"Maximum absolute Y error: {c['max_absolute_error_y']:.9g}; mean absolute Y error: {c['mae_y']:.9g}; Y RMSE: {c['rmse_y']:.9g}.",'']
    lines += ['## Limits','',f"Failed tolerances: {len(failures)} / 10. Exact per-point values and labeled synthetic controls are in `accuracy.json`.",'','Only two clean linear, axis-aligned charts and one set of manual selections were measured. Both charts use the same publisher and related data source. Logarithmic and reversed axes are supported and checked with labeled synthetic controls; this is not a real-chart accuracy study of those cases. No repeated-operator study or statistical confidence interval was performed.','', 'The chosen tolerance budgets represent pixel placement and calibration reading sensitivity, not uncertainty in the underlying demographic estimates. Rasterization used browser fallback fonts without cropping; source SVGs and numerical CSVs remain unchanged. Interpolation between years, anchor rounding, raster line width, and operator judgment can all affect results. Do not treat these figures as scientific validation of the source data.','', 'Verification checks reproducibility, hashes, independent transforms, and the complete recorded result (including the miss). Add `--require-tolerances` for a strict experimental gate; it exits 1 for this frozen result.','', 'Reproduce: `python3 scripts/verify.py` (frozen sample exports) or, after the browser test, `python3 scripts/verify.py --exports test-results/exports` (fresh browser exports).']
    (ROOT/'results/accuracy.md').write_text('\n'.join(lines)+'\n')
else:
    saved=load('results/accuracy.json')
    check(saved==result,'Recorded accuracy differs from independently recomputed results')
print(json.dumps({'charts':len(report),'real_points':sum(len(c['points']) for c in report),'failed_tolerances':len(failures),'synthetic_controls':len(controls),'max_errors':[{k:c[k] for k in ['chart','max_absolute_error_x','max_absolute_error_y']} for c in report]},indent=2))
if failures:
    print('Observed negative result: 1/10 frozen selections exceeded tolerance; retained unchanged.')
    if a.require_tolerances:sys.exit(1)
