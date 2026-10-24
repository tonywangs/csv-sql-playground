import copy
import json
import tempfile
import unittest
from pathlib import Path
from pivot import analyze, parse, report_files, unpack_project, default_config, MAX_BYTES
from scripts.verify_report import verify

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ('id,side,value,note\n'
           '001,A,0,"line one\nline two"\n'
           '001,A,-1.25,duplicate\n'
           '001,A,-1.25,duplicate\n'
           '001,B,,empty\n'
           '002,A,NA,missing\n'
           '002,A,nope,invalid\n'
           '雪,B,2.5,Unicode\n'
           '雪,B,3.5,Unicode\n'
           '雪,B,4.5,Unicode\n'
           ',B,0,empty category\n'
           'bad,width\n'
           '\n'
           '=1+1,B,1,<script>bad()</script>\n').encode()


def config(raw):
    c = default_config(parse(raw)['headers'])
    c['types'][parse(raw)['headers'][2]] = 'number'
    c.update(column=parse(raw)['headers'][1], value=parse(raw)['headers'][2], aggregate='mean', missing=['','NA'])
    return c


class PivotTests(unittest.TestCase):
    def independent(self, raw, c):
        r=analyze(raw,'input.csv',c)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'source.csv').write_bytes(raw)
            for name,value in report_files(r).items(): (p/name).write_bytes(value)
            verify(p/'source.csv',p)
        return r

    def test_controls_all_aggregates(self):
        for aggregate in ['count','sum','mean']:
            c=config(CONTROL);c['aggregate']=aggregate
            r=self.independent(CONTROL,c)
            self.assertEqual(r['accounting'],dict(total=13,included=11,filtered=0,rejected=2))
            self.assertEqual(r['total']['valid'],8)
            self.assertEqual(r['total']['missing'],2)
            self.assertEqual(r['total']['invalid'],1)
            self.assertEqual(r['groups'][1]['row'],'001')
            self.assertEqual(r['records'][0]['values'][3],'line one\nline two')

    def test_real_every_numeric_measure_and_aggregate(self):
        raw=(ROOT/'data/penguins.csv').read_bytes()
        for value in ['bill_length_mm','bill_depth_mm','flipper_length_mm','body_mass_g','year']:
            for aggregate in ['count','sum','mean']:
                c=default_config(parse(raw)['headers']);c.update(column='island',value=value,aggregate=aggregate,missing=['','NA']);c['types'][value]='number'
                r=self.independent(raw,c)
                self.assertEqual(r['accounting']['included'],344)

    def test_filters_empty_and_unequal_means(self):
        c=config(CONTROL)
        c['filters']=[dict(column='id',op='eq',value='001')]
        r=self.independent(CONTROL,c)
        self.assertEqual(r['total']['value'],'-0.833333333333')
        self.assertEqual(r['total']['count'],4)
        c['filters'][0]['value']='never'
        r=self.independent(CONTROL,c)
        self.assertEqual(r['groups'],[])
        self.assertIsNone(r['total']['value'])
        c['aggregate']='count';self.assertEqual(self.independent(CONTROL,c)['total']['value'],'0')
        for op in ['ne','contains']:
            c['filters']=[dict(column='id',op=op,value='00')];self.independent(CONTROL,c)

    def test_number_grammar_and_rounding(self):
        raw=b'id,side,value\nx,a,1e3\nx,a,NaN\nx,a,Infinity\nx,a, 2\nx,a,2.\nx,a,1_000\nx,a,+.5\nx,a,-0\nx,a,999999999999999999.999999999999\n'
        r=self.independent(raw,config(raw))
        self.assertEqual(r['total']['invalid'],6)
        self.assertEqual(r['total']['valid'],3)
        for value,expected in [('0.000000000001','0'),('0.000000000003','0.000000000002'),('-0.000000000003','-0.000000000002')]:
            raw=f'id,side,value\nx,a,{value}\nx,a,0\n'.encode()
            self.assertEqual(self.independent(raw,config(raw))['total']['value'],expected)

    def test_reject_bad_inputs_and_limits(self):
        for raw in [b'',b'a,a\n1,2',b'a,\n1,2',b'a\n"unclosed',b'a\n\xff',b'a'* (MAX_BYTES+1),b'a\n'+b'x\n'*10001,(','.join('h'+str(i) for i in range(41))).encode(),b'a\n'+b'x'*10001]:
            with self.assertRaises(ValueError):parse(raw)
        raw=('a\n'+'\n'.join(str(i) for i in range(501))).encode()
        with self.assertRaises(ValueError):analyze(raw,'too-many.csv')

    def test_invalid_config_no_partial_result(self):
        for key,value in [('aggregate','median'),('row','unknown'),('types',{}),('missing','NA'),('filters',[dict(column='id',op='gt',value='1')]),('value','unknown')]:
            c=config(CONTROL);c[key]=value
            with self.assertRaises(ValueError):analyze(CONTROL,'c.csv',c)
        c=config(CONTROL);c['types']['value']='text'
        with self.assertRaises(ValueError):analyze(CONTROL,'c.csv',c)

    def test_recovery_identity(self):
        from pivot import project
        r=analyze(CONTROL,'original.csv',config(CONTROL))
        c,sha=unpack_project(project(r))
        self.assertEqual(analyze(CONTROL,'renamed.csv',c,sha)['groups'],r['groups'])
        with self.assertRaisesRegex(ValueError,'hash mismatch'):analyze(CONTROL+b'\n','wrong.csv',c,sha)
        for p in [{},dict(version=2,source={'sha256':sha},config=c)]:
            with self.assertRaises(ValueError):unpack_project(p)

    def test_bom_crlf_and_quoted_strings(self):
        raw='\ufeffid,side,value\r\n"001","a,""b",1.2\r\n'.encode()
        r=self.independent(raw,config(raw))
        self.assertEqual(r['groups'][0]['column'],'a,"b')

    def test_demo_pinned_hashes(self):
        import hashlib
        m=json.loads((ROOT/'data/source.json').read_text())
        for f in m['files']:
            self.assertEqual(hashlib.sha256((ROOT/'data'/f['name']).read_bytes()).hexdigest(),f['sha256'])

    def test_independent_verifier_detects_wrong_visible_html(self):
        import hashlib
        r=analyze(CONTROL,'controls.csv',config(CONTROL))
        files=report_files(r)
        for before, after in [(b'<p class="value">0</p>',b'<p class="value">999</p>'),
                              (b'1 records',b'999 records'),
                              (b'&quot;001&quot;',b'&quot;009&quot;')]:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d); (p/'source.csv').write_bytes(CONTROL)
                changed=dict(files)
                self.assertIn(before,changed['report.html'])
                changed['report.html']=changed['report.html'].replace(before,after,1)
                # Rehash to ensure the independent visible-summary check catches it.
                manifest=json.loads(changed['manifest.json'])
                manifest['outputs']['report.html']=hashlib.sha256(changed['report.html']).hexdigest()
                changed['manifest.json']=json.dumps(manifest).encode()
                for name,value in changed.items(): (p/name).write_bytes(value)
                with self.assertRaises(AssertionError): verify(p/'source.csv',p)


if __name__ == '__main__':unittest.main()
