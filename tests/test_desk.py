import json
from pathlib import Path
import tempfile
import unittest
import desk
from tools.verify_export import verify


def f(path='', op='eq', value='null'): return {'path':path,'op':op,'value':value}


class DeskTests(unittest.TestCase):
    def test_controls_and_independent_audit(self):
        # Labeled synthetic controls: nested arrays, missing/null, mixed types,
        # exact large integers, duplicate keys, malformed UTF-8/JSON, Unicode, CRLF.
        raw=(b'{"a":{"b":[null,9007199254740993]},"x":true}\r\n'
             b'{"a":{"b":["null",9007199254740992]},"x":1}\n'
             b'{"a":{},"x":"1"}\n'
             b'{"x":null,"a/b":{"~key":"caf\\u00e9"}}\n'
             b'null\ntrue\n42\n"snow \\u96ea"\n[1,2]\n'
             b'\n{"x":1,"x":2}\n{"bad":\xff}\n{broken}\nNaN\n'
             b'{"bad":"\\ud800"}\n'
             b'{"a":{"b":[false,9007199254740993]}}')
        source=desk.Source(raw)
        self.assertEqual(list(source.errors),[10,11,12,13,14,15])
        cases=[([f('/a/b/1','eq','9007199254740993')],[1,16]),
               ([f('/a/b/0','type','null')],[1]),
               ([f('/x','eq','true')],[1]),([f('/x','eq','1')],[2]),
               ([f('/x','eq','"1"')],[3]),([f('/x','type','null')],[4]),
               ([f('/a/b/1','gte','9007199254740993')],[1,16]),
               ([f('/a~1b/~0key','eq','"café"')],[4]),
               ([f('','type','array')],[9]),([f('','eq','"snow 雪"')],[8]),
               ([f('/a/b/0','type','missing')],[3,4,5,6,7,8,9]),
               ([f('/a/b/01','type','missing')],[1,2,3,4,5,6,7,8,9,16])]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                selected,counts=source.select(filters,[])
                self.assertEqual(selected,expected)
                self.assertEqual(sum(counts[k] for k in ('included','excluded','errors')),counts['total'])
        out,m=source.export(cases[0][0],[])
        self.assertTrue(out.startswith(source.lines[0]))
        self.assertFalse(out.endswith(b'\n'))
        self.assertEqual(source.raw,raw)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'source').write_bytes(raw);(p/'subset').write_bytes(out);(p/'manifest').write_text(json.dumps(m))
            verify(p/'source',p/'subset',p/'manifest')
            (p/'subset').write_bytes(out+b'\n')
            with self.assertRaises(AssertionError):verify(p/'source',p/'subset',p/'manifest')

    def test_empty_and_line_endings(self):
        for raw,total,errors in [(b'',0,0),(b'\n',1,1),(b'{}\n',1,0),(b'{}\r\n{}',2,0),(b'{}\r{}',1,1),(b'\xef\xbb\xbf{}\n',1,1)]:
            s=desk.Source(raw);out,m=s.export([],[])
            self.assertEqual(m['counts']['total'],total);self.assertEqual(m['counts']['errors'],errors)
            if not errors:self.assertEqual(out,raw)

    def test_limits_and_bad_filters(self):
        with self.assertRaises(ValueError):desk.Source(b' '*(desk.MAX_BYTES+1))
        with self.assertRaises(ValueError):desk.Source(b'\n'*(desk.MAX_LINES+1))
        for raw in [b'"'+b'a'*desk.MAX_LINE+b'"',b'['*65+b'0'+b']'*65,b'1e10001',b'1'*1001]:
            self.assertEqual(len(desk.Source(raw).errors),1)
        for rule in [f('bad'),f('/bad~2'),f('','gt','"1"'),f('','eq','{}'),f('','type','invalid'),f('','unknown','1')]:
            with self.assertRaises(ValueError):desk.compile_filters([rule])
        s=desk.Source(b'{}\n')
        with self.assertRaises(ValueError):s.select([],[True])
        with self.assertRaises(ValueError):s.select([],[2])

    def test_precision_and_types(self):
        s=desk.Source(b'1.00000000000000000001\n1.00000000000000000002\ntrue\n1\n"1"\n')
        self.assertEqual(s.select([f('','gt','1.00000000000000000001')],[])[0],[2])
        self.assertEqual(s.select([f('','eq','1')],[])[0],[4])
        self.assertEqual(s.select([f('','eq','1e0')],[])[0],[4])
        self.assertEqual(s.select([], [1,4])[0],[2,3,5])

    def test_extreme_exponent_audit_and_manifest_validation(self):
        source = desk.Source(b'1e999999999999999999999999\n1\n')
        out, m = source.export([], [])
        self.assertEqual(m['counts'], {'total': 2, 'included': 1, 'excluded': 0, 'errors': 1})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'source').write_bytes(source.raw); (p/'subset').write_bytes(out)
            (p/'manifest').write_text(json.dumps(m))
            verify(p/'source', p/'subset', p/'manifest')
            for rule in [f('', 'bogus', '1'), f('bad', 'eq', '1'), f('/~2', 'eq', '1')]:
                m['filters'] = [rule]
                (p/'manifest').write_text(json.dumps(m))
                with self.assertRaises(AssertionError): verify(p/'source', p/'subset', p/'manifest')

    def test_real_demo(self):
        raw=Path('data/earthquakes.jsonl').read_bytes();s=desk.Source(raw)
        self.assertEqual(len(s.errors),0)
        filters=[f('/properties/mag','gte','5')]
        out,m=s.export(filters,[])
        self.assertGreater(len(out),0);self.assertLess(len(out),len(raw))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'subset').write_bytes(out);(p/'manifest').write_text(json.dumps(m))
            verify('data/earthquakes.jsonl',p/'subset',p/'manifest')

if __name__=='__main__':unittest.main()
