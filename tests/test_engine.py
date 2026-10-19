import io, unittest, zipfile
from unittest.mock import patch
from openpyxl import Workbook
from engine import inspect, dependencies, LIMITS

def workbook(values):
    w=Workbook();w.remove(w.active)
    for name, cells in values.items():
        s=w.create_sheet(name)
        for address,value in cells.items():s[address]=value
    b=io.BytesIO();w.save(b);return b.getvalue()

def modify(data, replacement):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as z,zipfile.ZipFile(out,'w') as target:
        for n in z.namelist():
            raw=z.read(n)
            if n=='xl/worksheets/sheet1.xml':raw=replacement(raw.decode()).encode()
            target.writestr(n,raw)
    return out.getvalue()

class EngineTests(unittest.TestCase):
    def test_quoted_mixed_ranges(self):
        m=inspect(workbook({'Main':{'A1':"=SUM('Bob''s data'!$A1:B$2)+$C$3"},"Bob's data":{'A1':1,'B2':3}}))
        self.assertEqual({e['target'] for e in m['edges']},{"'Bob''s data'!A1","'Bob''s data'!A2","'Bob''s data'!B1","'Bob''s data'!B2","'Main'!C3"})
        self.assertEqual(m['coverage']['supported'],1)
    def test_unresolved(self):
        formulas=['=INDIRECT("B2")+A1','=Missing!A1+A1','=Table1[Amount]+A1','=[Other.xlsx]Sheet1!A1','=A1#','=some_name+A1','=OFFSET(A1,0,1)','=UNKNOWN(A1)','=A1 B2','=SUM(A:A)','=A1+#REF!']
        for f in formulas:
            with self.subTest(formula=f):
                m=inspect(workbook({'Main':{'B3':f}}));self.assertNotEqual(m['cells']["'Main'!B3"]['coverage'],'supported')
    def test_literal_and_cache(self):
        raw=workbook({'S':{'A1':1,'A2':'=A1+1','A3':'=not_a_value'}})
        raw=modify(raw,lambda t:t.replace('<f>A1+1</f><v />','<f>A1+1</f><v>2</v>'))
        m=inspect(raw);self.assertEqual(m['cells']["'S'!A2"]['cached'],'2');self.assertIsNone(m['cells']["'S'!A2"]['value']);self.assertEqual(m['cells']["'S'!A1"]['value'],'1')
    def test_shared_and_array(self):
        raw=workbook({'S':{'A1':1,'B1':'=A1','B2':'=A2','C1':'=SUM(A1:A2)'}})
        raw=modify(raw,lambda t:t.replace('<f>A1</f>','<f t="shared" si="0" ref="B1:B2">A1</f>').replace('<f>A2</f>','<f t="shared" si="0"></f>').replace('<f>SUM(A1:A2)</f>','<f t="array" ref="C1:C2">SUM(A1:A2)</f>'))
        m=inspect(raw);self.assertEqual(m['cells']["'S'!B2"]['formula'],'=A2');self.assertEqual(m['cells']["'S'!B2"]['source_formula'],'');self.assertEqual(m['cells']["'S'!C1"]['coverage'],'partial')
    def test_missing_shared_master(self):
        raw=modify(workbook({'S':{'A1':'=B1'}}),lambda t:t.replace('<f>B1</f>','<f t="shared" si="10"></f>'))
        self.assertEqual(inspect(raw)['cells']["'S'!A1"]['coverage'],'unsupported')
    def test_limits(self):
        refs,issues=dependencies('=SUM(A1:XFD1048576)','S',['S']);self.assertFalse(refs);self.assertIn('Range expansion limit',issues[0])
        raw=workbook({'S':{'A1':1,'A2':2}})
        with patch.dict(LIMITS,cells=1):
            with self.assertRaisesRegex(ValueError,'Cell count'):inspect(raw)
        with patch.dict(LIMITS,expanded_bytes=10):
            with self.assertRaisesRegex(ValueError,'expansion'):inspect(raw)
        with patch.dict(LIMITS,upload_bytes=10):
            with self.assertRaisesRegex(ValueError,'upload'):inspect(raw)
        with self.assertRaisesRegex(ValueError,'unencrypted'):inspect(b'\xd0\xcfEncrypted file')
    def test_no_entity_expansion(self):
        raw=modify(workbook({'S':{'A1':1}}),lambda t:'<!DOCTYPE worksheet [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'+t.replace('<v>1</v>','<v>&secret;</v>'))
        with self.assertRaises(Exception):inspect(raw)
    def test_case_insensitive_sheet(self):
        refs,issues=dependencies('=s!a1','Main',['Main','S']);self.assertEqual(refs,[("'S'!A1",'s!a1')]);self.assertFalse(issues)
if __name__=='__main__':unittest.main()
