import contextlib
import csv
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from csv_reconcile_desk.cli import main, render_html, serialize
from csv_reconcile_desk.core import InputError, read_csv, reconcile


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, text, name):
        path = self.root / name
        path.write_bytes(text.encode('utf-8'))
        return read_csv(path)

    def compare(self, before, after, keys=('id',)):
        return reconcile(self.source(before, 'before.csv'), self.source(after, 'after.csv'), keys)

    def test_unique_changes_and_complete_accounting(self):
        result = self.compare('id,v\na,old\nb,same\nc,gone\n', 'id,v\nb,same\na,new\nd,added\n')
        self.assertEqual([e['status'] for e in result['events']], ['changed','unchanged','removed','added'])
        self.assertEqual(result['events'][0]['changes'], [{'column':'v','before':'old','after':'new'}])
        self.assertEqual(result['events'][0]['after'][0]['row'], 2)
        self.assertEqual(result['accounting'], {'before': {'input':3,'accounted':3},'after':{'input':3,'accounted':3}})

    def test_duplicate_multiplicity_preserved(self):
        result = self.compare('id,v\na,x\na,x\na,x\n', 'id,v\na,x\na,x\n')
        self.assertEqual([e['status'] for e in result['events']], ['unchanged','unchanged','removed'])
        self.assertEqual(result['events'][2]['before'][0]['row'], 3)
        self.assertEqual(result['duplicate_keys'], [{'key':['a'],'before_count':3,'after_count':2}])

    def test_duplicate_residuals_never_become_definite_change(self):
        result = self.compare('id,v\na,x\na,y\n', 'id,v\na,x\na,z\n')
        self.assertEqual([e['status'] for e in result['events']], ['unchanged','unresolved'])
        event = result['events'][1]
        self.assertEqual(event['reason'],'duplicate_key')
        self.assertNotIn('changes', event)
        self.assertEqual(event['before'][0]['values']['v'],'y')
        self.assertEqual(event['after'][0]['values']['v'],'z')

    def test_unequal_ambiguous_groups_do_not_invent_additions(self):
        result = self.compare('id,v\na,x\na,y\n', 'id,v\na,q\na,r\na,s\n')
        self.assertEqual(len(result['events']),1)
        self.assertEqual(result['summary']['unresolved'], {'groups':1,'before':2,'after':3})
        self.assertEqual(result['summary']['added']['groups'],0)

    def test_one_sided_duplicate_group_is_fully_added(self):
        result = self.compare('id,v\n', 'id,v\na,x\na,x\n')
        self.assertEqual(result['summary']['added']['after'],2)
        self.assertEqual(len(result['duplicate_keys']),1)

    def test_reordered_duplicate_records_match_by_value(self):
        result = self.compare('id,v\na,x\na,y\n', 'id,v\na,y\na,x\n')
        self.assertEqual(result['summary']['unchanged']['groups'],2)
        self.assertEqual(result['events'][0]['after'][0]['row'],2)

    def test_missing_keys_are_unresolved_even_if_equal(self):
        result = self.compare('id,v\n,x\n', 'id,v\n,x\n')
        self.assertEqual(result['summary']['unresolved'], {'groups':2,'before':1,'after':1})
        self.assertTrue(all(e['reason']=='missing_key' for e in result['events']))

    def test_composite_key_missing_component_and_exact_strings(self):
        result = self.compare('id,part,v\na,1,01\na,,x\n ,2,y\n', 'id,part,v\na,1,1\na,,x\n ,2,y\n', ('id','part'))
        self.assertEqual(result['summary']['changed']['groups'],1)
        self.assertEqual(result['summary']['unchanged']['groups'],1)
        self.assertEqual(result['summary']['unresolved']['groups'],2)

    def test_quoted_multiline_crlf_and_bom_references(self):
        source = self.source('\ufeffid,v\r\na,"one\r\ntwo, \"\"three\"\""\r\nb,end\r\n','multi.csv')
        self.assertEqual(source['records'][0], {'row':1,'line_start':2,'line_end':3,'values':{'id':'a','v':'one\r\ntwo, "three"'}})
        self.assertEqual(source['records'][1]['line_start'],4)
        result = reconcile(source,source,['id'])
        self.assertEqual(result['summary']['unchanged']['groups'],2)

    def test_schema_absence_is_different_from_empty_string(self):
        result = self.compare('id,old\na,\n', 'id,new\na,\n')
        self.assertEqual(result['schema'], {'added':['new'],'removed':['old'],'order_changed':False})
        self.assertEqual(result['events'][0]['changes'], [{'column':'old','before':'','after':None}, {'column':'new','before':None,'after':''}])

    def test_reordering_columns_is_not_a_row_change(self):
        result = self.compare('id,v\na,x\n', 'v,id\nx,a\n')
        self.assertTrue(result['schema']['order_changed'])
        self.assertEqual(result['summary']['unchanged']['groups'],1)

    def test_empty_tables_with_headers(self):
        result = self.compare('id,v\n','id,v\n')
        self.assertEqual(result['events'],[])
        self.assertEqual(result['accounting']['before']['input'],0)

    def test_invalid_header_width_encoding_and_quotes_fail(self):
        for text in ['', '\n', 'id,id\na,b\n', 'id, \na,b\n','id,v\na\n','id,v\na,b,c\n','id,v\n\n','id,v\na,"unterminated\n','id,v\na,\x00\n']:
            with self.subTest(text=text), self.assertRaises(InputError):
                self.source(text,'bad.csv')
        path = self.root/'bad-encoding.csv'
        path.write_bytes(b'id,v\na,\xff\n')
        with self.assertRaises(InputError): read_csv(path)

    def test_missing_key_header_and_repeated_key_fail(self):
        for keys in [[],['missing'],['id','id']]:
            with self.subTest(keys=keys), self.assertRaises(InputError):
                self.compare('id,v\na,x\n','id,v\na,x\n',keys)
        with self.assertRaises(InputError): self.compare('id,v\na,x\n','other,v\na,x\n')

    def test_semicolon_input(self):
        path = self.root/'semicolon.csv'
        path.write_text('id;v\na;"x;y"\n')
        self.assertEqual(read_csv(path,';')['records'][0]['values']['v'],'x;y')

    def test_json_determinism_and_html_script_injection(self):
        result = self.compare('id,v\na,</script><script>alert(1)</script>\n', 'id,v\na,<img src=x onerror=alert(1)>\n')
        self.assertEqual(serialize(result),serialize(result))
        html = render_html(result)
        self.assertNotIn('</script><script>alert(1)</script>',html)
        self.assertIn('\\u003c/script\\u003e',html)
        payload = html.split('<script id="report-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(payload),result)

    def test_seeded_randomized_record_conservation_and_multisets(self):
        from collections import Counter
        rng = random.Random(20261019)
        for case in range(100):
            tables = []
            for side in range(2):
                stream = io.StringIO(newline='')
                writer = csv.writer(stream)
                writer.writerow(['id','v'])
                writer.writerows([(rng.choice(['','a','b','c']),rng.choice(['x','y','z','comma,quote"\nline'])) for _ in range(rng.randrange(30))])
                tables.append(self.source(stream.getvalue(),f'{side}.csv'))
            result = reconcile(*tables,['id'])
            for side,table in zip(['before','after'],tables):
                observed = [row for event in result['events'] for row in event[side]]
                self.assertEqual(sorted(observed,key=lambda r:r['row']),table['records'])
            original = [Counter(tuple(row['values'].items()) for row in table['records'] if row['values']['id']) for table in tables]
            equal = Counter(tuple(e['before'][0]['values'].items()) for e in result['events'] if e['status']=='unchanged')
            self.assertEqual(equal,original[0] & original[1])
            for event in result['events']:
                if event['status']=='changed':
                    key = event['key'][0]
                    self.assertTrue(all(sum(row['values']['id']==key for row in t['records'])==1 for t in tables))

    def test_cli_errors_and_output_preservation(self):
        self.source('id,v\na,x\n','before.csv')
        self.source('id,v\na,y\n','after.csv')
        args = [str(self.root/'before.csv'),str(self.root/'after.csv'),'--key','id','--json',str(self.root/'result.json'),'--html',str(self.root/'result.html')]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args),0)
            original = (self.root/'result.json').read_bytes()
            self.assertEqual(main(args),2)
            self.assertEqual((self.root/'result.json').read_bytes(),original)
            self.assertEqual(main(args+['--force']),0)
            self.assertEqual((self.root/'result.json').read_bytes(),original)
            self.assertEqual(main(args+['--force','--json',str(self.root/'before.csv')]),2)
            self.assertEqual(main(args+['--force','--html',str(self.root/'result.json')]),2)
            self.assertEqual(main(args+['--delimiter','xx']),2)
        self.assertEqual((self.root/'before.csv').read_text(),'id,v\na,x\n')

    def test_hard_link_output_cannot_overwrite_input(self):
        self.source('id,v\na,x\n','before.csv')
        self.source('id,v\na,y\n','after.csv')
        linked = self.root/'alias.json'
        linked.hardlink_to(self.root/'before.csv')
        args = [str(self.root/'before.csv'),str(self.root/'after.csv'),'--key','id',
                '--json',str(linked),'--html',str(self.root/'r.html'),'--force']
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args),2)
        self.assertEqual((self.root/'before.csv').read_text(),'id,v\na,x\n')

    def test_separate_process_determinism(self):
        self.source('id,v\na,x\na,y\nb,z\n','before.csv')
        self.source('id,v\na,y\na,q\nc,z\n','after.csv')
        args = [sys.executable,'-m','csv_reconcile_desk',str(self.root/'before.csv'),str(self.root/'after.csv'),'--key','id','--json',str(self.root/'r.json'),'--html',str(self.root/'r.html'),'--force']
        subprocess.run(args,check=True,capture_output=True)
        first = [(self.root/name).read_bytes() for name in ['r.json','r.html']]
        subprocess.run(args,check=True,capture_output=True)
        self.assertEqual(first,[(self.root/name).read_bytes() for name in ['r.json','r.html']])


if __name__ == '__main__':
    unittest.main()
