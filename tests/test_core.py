import base64, io, json, sqlite3, tempfile, time, unittest, zipfile
from pathlib import Path
from desk.core import bundle, execute, inspect, parameters, settings, sha, validate_header
from desk.server import State

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'control.sqlite'
        con = sqlite3.connect(self.path)
        con.execute('CREATE TABLE controls(id INTEGER, label TEXT, payload BLOB)')
        con.executemany('INSERT INTO controls VALUES(?,?,?)', [(2**63-1,None,b'\x00\xff'),(-2**63,'',b''),(7,'=SUM(A1)',b'ab')])
        con.commit(); con.close()
        self.original = self.path.read_bytes()
        self.source = {'name':'labeled synthetic controls','sha256':sha(self.original),'bytes':len(self.original)}
    def tearDown(self):
        self.assertEqual(self.path.read_bytes(),self.original)
        self.tmp.cleanup()
    def query(self,sql,params=None,limits=None):
        return execute(self.path,{'sql':sql,'parameters':params or {},'settings':limits or {},'source':self.source})
    def test_typed_values_and_duplicate_column_positions(self):
        r=self.query('SELECT id AS x, label AS x, payload FROM controls ORDER BY id DESC')
        self.assertEqual(r['columns'],['x','x','payload'])
        self.assertEqual(r['rows'][0],[{'type':'integer','value':str(2**63-1)},{'type':'null','value':None},{'type':'blob','value':'AP8='}])
        self.assertEqual(r['rows'][2][0]['value'],str(-2**63))
        self.assertEqual(r['rows'][2][1],{'type':'text','value':''})
        self.assertTrue(r['source_unchanged'])
    def test_parameters(self):
        params={'i':{'type':'integer','value':str(2**63-1)},'r':{'type':'real','value':'1.25'},'t':{'type':'text','value':"x'; DROP TABLE controls;--"},'n':{'type':'null','value':None},'b':{'type':'blob','value':'AP8='}}
        r=self.query('SELECT :i,:r,:t,:n,:b',params)
        self.assertEqual([c['type'] for c in r['rows'][0]],['integer','real','text','null','blob'])
        self.assertEqual(r['rows'][0][2]['value'],params['t']['value'])
        for spec in [{'type':'integer','value':9007199254740993},{'type':'integer','value':str(2**63)},{'type':'real','value':'nan'},{'type':'null','value':''},{'type':'blob','value':'!'}]:
            with self.assertRaises(ValueError): parameters({'x':spec})
    def test_readonly_actions(self):
        statements=['DELETE FROM controls','UPDATE controls SET id=0','INSERT INTO controls VALUES(1,2,3)','DROP TABLE controls','CREATE TABLE stolen(x)','ATTACH DATABASE ":memory:" AS stolen','PRAGMA query_only=OFF','PRAGMA table_info(controls)','BEGIN','VACUUM','SELECT load_extension("x")','SELECT readfile("/etc/passwd")','SELECT 1; SELECT 2']
        for sql in statements:
            with self.subTest(sql=sql): self.assertEqual(self.query(sql)['status'],'error')
    def test_malformed_empty_and_complete(self):
        self.assertEqual(self.query('SELCT 1')['status'],'error')
        r=self.query('SELECT * FROM controls WHERE 0')
        self.assertEqual((r['status'],r['row_count']),('complete',0))
        r=self.query('SELECT * FROM controls',limits={'rows':3})
        self.assertEqual((r['status'],r['row_count']),('complete',3))
    def test_row_and_byte_truncation(self):
        r=self.query('SELECT * FROM controls ORDER BY id',limits={'rows':2})
        self.assertEqual((r['status'],r['row_count'],r['reason']),('truncated',2,'row limit'))
        r=self.query("SELECT 'long string' AS x",limits={'bytes':30})
        self.assertEqual((r['status'],r['row_count']),('truncated',0))
        r=self.query('SELECT 1 AS long_column',limits={'bytes':1})
        self.assertEqual(r['status'],'truncated')
    def test_timeout(self):
        r=self.query('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n',limits={'seconds':1})
        self.assertEqual(r['status'],'interrupted')
        self.assertEqual(r['reason'],'time limit')
    def test_export_checksums_acknowledgment_and_csv(self):
        r=self.query('SELECT * FROM controls ORDER BY id',limits={'rows':2})
        with self.assertRaises(ValueError):bundle(r)
        with zipfile.ZipFile(io.BytesIO(bundle(r,True))) as z:
            m=json.loads(z.read('manifest.json')); j=json.loads(z.read('results.json'))
            self.assertEqual(j,r)
            self.assertTrue(m['partial_acknowledged'])
            for name,digest in m['output_hashes'].items(): self.assertEqual(sha(z.read(name)),digest)
            self.assertIn(b'=SUM(A1)',z.read('results.csv'))
        with self.assertRaises(ValueError):bundle(self.query('bad sql'))
    def test_snapshot_hash_mismatch(self):
        self.source['sha256']='0'*64
        r=self.query('SELECT * FROM controls')
        self.assertEqual(r['status'],'error')
        self.assertFalse(r['source_unchanged'])
        self.assertEqual(r['rows'],[])
    def test_schema_and_snapshot_validation(self):
        self.assertEqual(inspect(self.path)[0]['columns'][0]['name'],'id')
        validate_header(self.original)
        for data in [b'bad',self.original[:18]+b'\x02\x02'+self.original[20:],self.original+b'\x00'*(8*1024*1024)]:
            with self.assertRaises(ValueError):validate_header(data)
        for raw in [{'seconds':11},{'rows':True},{'bytes':0},{'unknown':1}]:
            with self.assertRaises(ValueError):settings(raw)
    def test_allocation_limit(self):
        self.assertEqual(self.query('SELECT zeroblob(5000000)')['status'],'error')
    def test_cancel_and_reconnection(self):
        s=State()
        try:
            with self.assertRaises(ValueError):s.connect(self.original,'control.sqlite',False)
            s.connect(self.original,'control.sqlite',True)
            req={'sql':'WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n','settings':{'seconds':10},'source_hash':self.source['sha256']}
            s.start(req)
            with self.assertRaises(ValueError):s.start(req)
            with self.assertRaises(ValueError):s.connect(self.original,'other',True)
            s.job['cancel'].set()
            deadline=time.monotonic()+3
            while s.busy() and time.monotonic()<deadline:time.sleep(.02)
            self.assertFalse(s.busy())
            self.assertEqual(s.job['result']['status'],'interrupted')
            self.assertEqual(s.job['result']['reason'],'cancelled')
            s.connect(self.original,'same',True)
            self.assertIsNone(s.job)
            with self.assertRaises(ValueError):s.start(req|{'source_hash':'bad'})
        finally:s.directory.cleanup()
    def test_empty_database(self):
        p=Path(self.tmp.name)/'empty.sqlite'
        c=sqlite3.connect(p);c.execute('VACUUM');c.close()
        s=State()
        try:self.assertEqual(s.connect(p.read_bytes(),'empty.sqlite',True)['schema'],[])
        finally:s.directory.cleanup()
if __name__ == '__main__':unittest.main()
