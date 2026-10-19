import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import desk

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.a=Path(self.temp.name)/'before.sqlite';self.b=Path(self.temp.name)/'after.sqlite'
    def make(self,path,script):
        db=sqlite3.connect(path);db.executescript(script);db.close()
    def compare(self,keys=None):
        hashes=[desk.digest(p.read_bytes()) for p in (self.a,self.b)]
        result=desk.compare(desk.snapshot(self.a),desk.snapshot(self.b),{'t':keys or []})
        self.assertEqual(hashes,[desk.digest(p.read_bytes()) for p in (self.a,self.b)])
        for table in result['tables'].values():
            if table['status']!='complete':continue
            c=table['counts']
            self.assertEqual(table['before_count'],c['removed']+c['changed']+c['unchanged']+c['ambiguous_before'])
            self.assertEqual(table['after_count'],c['added']+c['changed']+c['unchanged']+c['ambiguous_after'])
        return result
    def test_key_changes_and_storage_classes(self):
        self.make(self.a,"CREATE TABLE t(id, v); INSERT INTO t VALUES (1,1),(2,x'00ff'),(3,NULL),(4,'gone'),(6,9007199254740993);")
        self.make(self.b,"CREATE TABLE t(id, v); INSERT INTO t VALUES (1,1.0),(2,x'00fe'),(3,NULL),(5,'new'),(6,9007199254740993);")
        t=self.compare(['id'])['tables']['t'];self.assertEqual(t['counts'],dict(added=1,removed=1,changed=2,unchanged=2,ambiguous_before=0,ambiguous_after=0))
        self.assertIn(('integer','9007199254740993'),[v for r in t['records'] for s in ['before','after'] for row in r[s] for v in row['values']])
    def test_duplicates_null_and_composite_keys(self):
        self.make(self.a,"CREATE TABLE t(a,b,v); INSERT INTO t VALUES(1,1,'x'),(1,1,'y'),(1,2,'a'),(NULL,1,'n');")
        self.make(self.b,"CREATE TABLE t(a,b,v); INSERT INTO t VALUES(1,1,'x'),(1,2,'b'),(NULL,1,'n'),(2,1,'z');")
        t=self.compare(['a','b'])['tables']['t'];self.assertFalse(t['identity_valid'])
        self.assertEqual(t['counts'],dict(added=1,removed=0,changed=1,unchanged=0,ambiguous_before=3,ambiguous_after=2))
    def test_multiset_preserves_occurrences(self):
        self.make(self.a,"CREATE TABLE t(v); INSERT INTO t VALUES('same'),('same'),(NULL),(x'00'),('old');")
        self.make(self.b,"CREATE TABLE t(v); INSERT INTO t VALUES('same'),(NULL),(x'00'),('new');")
        t=self.compare()['tables']['t'];self.assertEqual(t['counts'],dict(added=0,removed=0,changed=0,unchanged=3,ambiguous_before=2,ambiguous_after=1))
    def test_missing_table_and_incompatible_schema(self):
        self.make(self.a,'CREATE TABLE t(id); INSERT INTO t VALUES(1); CREATE TABLE gone(v); INSERT INTO gone VALUES(2),(2);')
        self.make(self.b,'CREATE TABLE t(id,v); INSERT INTO t VALUES(1,3); CREATE TABLE fresh(v); INSERT INTO fresh VALUES(4);')
        r=self.compare();self.assertEqual(r['status'],'incomplete');self.assertEqual(r['tables']['t']['status'],'unsupported')
        self.assertEqual(r['tables']['gone']['counts']['removed'],2);self.assertEqual(r['tables']['fresh']['counts']['added'],1)
    def test_invalid_identity(self):
        for p in (self.a,self.b):self.make(p,'CREATE TABLE t(id);')
        self.assertEqual(self.compare(['missing'])['status'],'incomplete')
        self.assertEqual(self.compare(['id','id'])['status'],'incomplete')
    def test_schema_only_objects_and_without_rowid(self):
        for p in (self.a,self.b):self.make(p,'CREATE TABLE t(a,b,PRIMARY KEY(a,b)) WITHOUT ROWID; INSERT INTO t VALUES(1,2); CREATE VIEW v AS SELECT * FROM t; CREATE INDEX i ON t(b);')
        r=self.compare(['a','b']);self.assertEqual(r['tables']['t']['counts']['unchanged'],1)
        self.assertEqual(set(r['tables']),{'t'});self.assertIn('view',[o['type'] for o in r['before']['objects']])
    def test_virtual_and_collation_unsupported(self):
        for p in (self.a,self.b):self.make(p,"CREATE VIRTUAL TABLE f USING fts5(v); INSERT INTO f VALUES('test'); CREATE TABLE t(v COLLATE NOCASE); INSERT INTO t VALUES('x');")
        r=self.compare();self.assertEqual(r['status'],'incomplete')
        self.assertTrue(all(t['status']=='unsupported' for t in r['tables'].values()))
    def test_wal_companions_and_encrypted_rejected(self):
        self.make(self.a,'CREATE TABLE t(v);')
        companion=Path(str(self.a)+'-wal');companion.write_bytes(b'')
        with self.assertRaisesRegex(desk.Unsupported,'companion'):desk.snapshot(self.a)
        companion.unlink()
        db=sqlite3.connect(self.a);db.execute('PRAGMA journal_mode=WAL');db.close()
        with self.assertRaisesRegex(desk.Unsupported,'WAL-mode'):desk.snapshot(self.a)
        self.a.write_bytes(b'not SQLite')
        with self.assertRaisesRegex(desk.Unsupported,'encrypted'):desk.snapshot(self.a)
    def test_limits_incomplete_not_truncated_success(self):
        for p in (self.a,self.b):self.make(p,"CREATE TABLE t(v);INSERT INTO t VALUES('x'),('y');")
        with patch.object(desk,'MAX_ROWS',1):self.assertEqual(self.compare()['status'],'incomplete')
        with patch.object(desk,'MAX_REPORT',50):
            with self.assertRaisesRegex(desk.Unsupported,'Report exceeds'):self.compare()
        with patch.object(desk,'MAX_DB',2):
            with self.assertRaisesRegex(desk.Unsupported,'8 MiB'):desk.snapshot(self.a)
        with patch.object(desk,'MAX_MATERIALIZED',1):
            self.assertEqual(self.compare()['status'],'incomplete')
    def test_generated_values_are_bounded(self):
        for p in (self.a,self.b):
            self.make(p,'CREATE TABLE t(id, v GENERATED ALWAYS AS (zeroblob(2000000)) VIRTUAL);INSERT INTO t(id) VALUES(1);')
        r=self.compare(['id']);self.assertEqual(r['status'],'incomplete')
        self.assertIn('too big',r['tables']['t']['warnings'][0])
    def test_text_blob_and_typed_keys_are_distinct(self):
        for p in (self.a,self.b):self.make(p,"CREATE TABLE t(id,v);INSERT INTO t VALUES(1,'1'),(1.0,x'31'),('1',NULL),(x'31','');")
        t=self.compare(['id'])['tables']['t'];self.assertTrue(t['identity_valid']);self.assertEqual(t['counts']['unchanged'],4)
    def test_declared_schema_changes_are_visible(self):
        self.make(self.a,'CREATE TABLE t(id INTEGER, v TEXT);INSERT INTO t VALUES(1,2);')
        self.make(self.b,'CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT);INSERT INTO t VALUES(1,2);')
        t=self.compare(['id'])['tables']['t'];self.assertNotEqual(t['before_schema'],t['after_schema']);self.assertEqual(t['counts']['unchanged'],1)
    def test_quoted_names_and_html_data(self):
        for p in (self.a,self.b):self.make(p,'''CREATE TABLE "odd'table" ("a""b" TEXT); INSERT INTO "odd'table" VALUES ('</script><script>alert(1)</script>');''')
        r=self.compare();self.assertEqual(r['status'],'complete');self.assertEqual(r['tables']["odd'table"]['counts']['unchanged'],1)

if __name__=='__main__':unittest.main()
