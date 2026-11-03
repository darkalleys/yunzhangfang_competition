from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tax_harness.store import ROOT,initialize,connect,BusinessError
from tax_harness.state import Memory,upgrade
from tax_harness.service import Service
from tax_harness.chat import ChatSession
from tax_harness.knowledge import import_rules,status,list_rules


class StateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='test-state-',dir=ROOT/'data');self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name);self.db=self.directory/'state.sqlite3';initialize(self.db)
        self.memory=Memory(self.db,'U001','C001')

    def track(self): self.memory.track(Service(self.db).check('U001','C001','2026-09'))

    def test_task_restored_without_authorization_and_refreshed(self):
        self.track()
        Service(self.db).update('U001','C001','F002',{'purpose':'其他会话已填写'})
        session=ChatSession('U001','C001',self.db,trace_dir=self.directory)
        self.assertEqual('2026-09',session.month);self.assertIsNone(session.pending)
        self.assertEqual(4,len(session.memory.snapshot()['task']['missing_ids']))
        self.assertIn('没有待确认',session.turn('/confirm'))

    def test_isolation(self):
        self.track();self.memory.preference('style','简洁')
        for user,company in [('U002','C001'),('U001','C002')]:
            other=Memory(self.db,user,company).snapshot()
            self.assertIsNone(other['task']);self.assertEqual([],other['preferences'])
        with self.assertRaises(BusinessError): Memory(self.db,'U002','C002')

    def test_preference_correction_deletion_and_restart(self):
        self.memory.preference('style','简洁');self.memory.preference('style','详细')
        other=Memory(self.db,'U001','C001')
        self.assertEqual('详细',other.snapshot()['preferences'][0]['value'])
        other.preference('style');self.assertEqual([],self.memory.snapshot()['preferences'])

    def test_single_task_and_task_deletion(self):
        self.track();self.track()
        with connect(self.db) as con:self.assertEqual(1,con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0])
        self.memory.clear_task();self.assertIsNone(self.memory.snapshot()['task'])

    def test_task_completion_removes_active_task(self):
        self.track()
        for invoice in self.memory.snapshot()['task']['missing_ids']:
            Service(self.db).update('U001','C001',invoice,{'purpose':'用户提供的用途'})
        self.assertIsNone(self.memory.refresh()['task'])

    def test_rule_failure_preserves_task(self):
        self.track();status(self.db,'R002','2.0','inactive')
        with self.assertRaises(BusinessError):self.memory.refresh()
        self.assertIsNotNone(self.memory.snapshot()['task'])

    def test_new_rule_version_changes_current_checks(self):
        r=next(x for x in list_rules(self.db) if x['rule_id']=='R002' and x['version']=='2.0')
        r.update(version='2.1',status='inactive',kind='purpose_threshold',threshold_cents=100000,text='模拟新版本：金额达到1000元必填用途。')
        import_rules(self.db,[r]);status(self.db,'R002','2.0','inactive');status(self.db,'R002','2.1','active')
        result=Service(self.db).check('U001','C001','2026-09')
        self.assertEqual(['F006'],[x['invoice_id'] for x in result['missing']])
        self.assertEqual('2.1',result['rule']['version'])

    def test_rule_immutable_conflict_and_atomic_import(self):
        r=next(x for x in list_rules(self.db) if x['rule_id']=='R002' and x['version']=='2.0')
        r['text']='覆盖旧正文'
        with self.assertRaises(BusinessError):import_rules(self.db,[r])
        r['version']='2.1'
        with self.assertRaises(BusinessError):import_rules(self.db,[r])
        self.assertFalse(any(x['version']=='2.1' for x in list_rules(self.db)))

    def test_invalid_rule_conditions(self):
        r=next(x for x in list_rules(self.db) if x['rule_id']=='R003');r['threshold_cents']=True
        with self.assertRaises(BusinessError):import_rules(self.db,[r])

    def test_migration_preserves_business_and_has_backup(self):
        service=Service(self.db);service.update('U001','C001','F002',{'purpose':'升级前数据'})
        with connect(self.db) as con:
            con.executescript('DROP TABLE tasks;DROP TABLE preferences;DROP TABLE state_events;DROP TABLE rule_events;')
        result=upgrade(self.db,self.directory/'backups')
        self.assertTrue(result['migrated']);self.assertTrue((Path(result['backup'])/'manifest.json').exists())
        self.assertEqual('升级前数据',service.invoice('U001','C001','F002')['purpose'])
        self.assertFalse(upgrade(self.db)['migrated'])

    def test_legacy_backup_restore_remains_supported(self):
        from tax_harness.maintenance import backup,restore
        with connect(self.db) as con:con.executescript('DROP TABLE tasks;DROP TABLE preferences;DROP TABLE state_events;DROP TABLE rule_events;')
        snapshot=backup(self.db,self.directory/'backups')
        restored=restore(snapshot,self.directory/'restored.sqlite3')
        self.assertEqual('9622.06',Service(restored).totals('U001','C001','2026-09')['invoice_total'])
        with self.assertRaises(BusinessError): Memory(restored,'U001','C001')

    def test_preference_commands_are_explicit(self):
        session=ChatSession('U001','C001',self.db,trace_dir=self.directory)
        session.turn('/pref style 回答简洁')
        self.assertIn('回答简洁',session.turn('/prefs'))
        session.turn('/forget style');self.assertEqual([],self.memory.snapshot()['preferences'])
