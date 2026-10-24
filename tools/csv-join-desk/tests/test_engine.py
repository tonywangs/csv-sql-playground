import base64
import copy
import csv
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from join_engine import parse, analyze, execute, request, MAX_BYTES
from scripts.verify_export import verify


def source(text, name='test.csv'):
    raw = text.encode() if isinstance(text, str) else text
    return {'name': name, 'data': base64.b64encode(raw).decode()}


def cfg(**updates):
    config = dict(left_keys=[0], right_keys=[0], left_columns=[0,1], right_columns=[0,1], join='full', relationship='unrestricted', limit=20000, acknowledge_many_to_many=False)
    return {**config, **updates}


class JoinTests(unittest.TestCase):
    def tables(self, left, right):
        return {'left': parse(source(left)), 'right': parse(source(right))}

    def test_duplicate_expansion_and_limits(self):
        tables = self.tables('k,v\na,1\na,2\nb,3\n', 'k,v\na,x\na,y\nz,z\n')
        report = analyze(tables, cfg())
        self.assertEqual(report['counts']['expected_rows'], 6)
        self.assertEqual(report['counts']['many_to_many_keys'], 1)
        with self.assertRaisesRegex(ValueError, 'Acknowledge'): execute(tables, cfg())
        with self.assertRaisesRegex(ValueError, 'One-to-one'): execute(tables, cfg(relationship='one-to-one', acknowledge_many_to_many=True))
        with self.assertRaisesRegex(ValueError, 'Many-to-one'): execute(tables, cfg(relationship='many-to-one', acknowledge_many_to_many=True))
        with self.assertRaisesRegex(ValueError, 'exceeds output limit'): execute(tables, cfg(limit=5, acknowledge_many_to_many=True))
        result = execute(tables, cfg(acknowledge_many_to_many=True))
        self.assertEqual(result['manifest']['pairs'], [[1,1],[1,2],[2,1],[2,2],[3,None],[None,3]])

    def test_composite_missing_unicode_multiline_exact_text(self):
        left='k,v,text\n01,é,"hello\nworld"\n1,é,plain\n01,é,combining\n,é,missing\nA,x,capital\n a,x,space\nNA,x,namibia\n'
        right='k,v,text\n01,é,yes\n01,é,decomposed\n,é,missing\na,x,lower\nNA,x,yes\n'
        tables=self.tables(left,right)
        c=cfg(left_keys=[0,1],right_keys=[0,1],left_columns=[0,1,2],right_columns=[0,1,2])
        result=execute(tables,c)
        self.assertEqual(result['manifest']['pairs'],[[1,1],[2,None],[3,2],[4,None],[5,None],[6,None],[7,5],[None,3],[None,4]])
        self.assertIn('"hello\nworld"',result['csv'])
        self.assertEqual(result['manifest']['missing'], {'left':[4],'right':[3]})

    def test_empty_source_field_provenance(self):
        result=execute(self.tables('k,v\na,\nb,z\n','k,v\na,\n'), cfg())
        self.assertEqual(result['preview'][0],['1','1','a','','a',''])
        self.assertEqual(result['preview'][1],['2','','b','z','',''])

    def test_rejection_is_whole_file(self):
        for text in ['a,a\n1,2\n','a,\n1,2\n','a,b\n1\n','a,b\n"unclosed,2\n', b'a\n\xff', 'a\n\x00', '']:
            with self.subTest(text=text), self.assertRaises(ValueError): parse(source(text))
        with self.assertRaises(ValueError): parse(source(b'a'*(MAX_BYTES+1)))
        with self.assertRaises(ValueError): parse(source('a\n'+'v\n'*10001))
        self.assertEqual(parse(source(b'\xef\xbb\xbfa,b\r\n1,2\r\n'))['rows'],[['1','2']])

    def test_header_only_and_invalid_config(self):
        tables=self.tables('k,v\n','k,v\nx,y\n')
        self.assertEqual(execute(tables,cfg())['manifest']['pairs'],[[None,1]])
        for bad in [cfg(left_keys=[]),cfg(left_keys=[0,0]),cfg(right_keys=[0,1]),cfg(left_columns=[-1]),cfg(limit=True),cfg(join='invalid'),cfg(acknowledge_many_to_many='yes')]:
            with self.assertRaises(ValueError): execute(tables,bad)

    def test_byte_limit_preflight(self):
        tables=self.tables('k,v\n'+'a,'+'x'*1000+'\n', 'k,v\n'+'a,y\n'*9000)
        report=analyze(tables,cfg())
        self.assertEqual(report['counts']['expected_rows'],9000)
        self.assertTrue(any('8 MiB' in e for e in report['errors']))
        with self.assertRaisesRegex(ValueError,'8 MiB'): execute(tables,cfg())

    def test_randomized_oracle(self):
        random.seed(7239)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for trial in range(12):
                inputs={}
                for side in ['left','right']:
                    stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(['key','component','value'])
                    writer.writerows([random.choice(['a','b','','é','01','1']),random.choice(['x','y','']),random.choice(['','multi\nline','a,b','"quoted"'])] for _ in range(9))
                    inputs[side]=source(stream.getvalue());(root/side).write_bytes(stream.getvalue().encode())
                for kind in ['inner','left','full']:
                    config=cfg(join=kind,left_keys=[0,1],right_keys=[0,1],left_columns=[2,0],right_columns=[1,2],acknowledge_many_to_many=True)
                    result=request({'action':'execute',**inputs,'config':config})
                    (root/'out').write_bytes(result['csv'].encode());(root/'manifest').write_text(json.dumps(result['manifest']))
                    verify(root/'left',root/'right',root/'out',root/'manifest')

    def test_real_demo_and_tamper_detection(self):
        verify('data/airports.csv','data/countries.csv','examples/joined.csv','examples/joined.manifest.json')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.csv';p.write_bytes(Path('examples/joined.csv').read_bytes()+b'bad')
            with self.assertRaises(AssertionError):verify('data/airports.csv','data/countries.csv',p,'examples/joined.manifest.json')

if __name__=='__main__':unittest.main()
