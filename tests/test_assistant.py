import io
import json
from pathlib import Path
import sys
import unittest
import socket
from urllib.error import HTTPError, URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
from assistant import make_report, ask_openrouter, AssistantError, NoRedirect
from models import Transaction, TransactionType


class AssistantTests(unittest.TestCase):
    def rows(self):
        return [Transaction(TransactionType.INCOME,100000,'Salary','2026-10-01','private'),
                Transaction(TransactionType.EXPENSE,12345,'Food','2026-10-02','shop'),
                Transaction(TransactionType.EXPENSE,777,'Food','2026-09-02','cafe')]

    def test_totals_and_scope(self):
        r=make_report(self.rows(),'2026-10')
        self.assertEqual((r['income_paise'],r['expense_paise'],r['net_paise']),(100000,12345,87655))
        self.assertEqual(r['count'],2)
        self.assertEqual(r['categories'][0]['amount_paise'],12345)
        self.assertEqual(make_report(self.rows())['expense_paise'],13122)
        self.assertEqual(make_report([])['net_paise'],0)

    def test_privacy_and_no_mutation(self):
        rows=self.rows();r=make_report(rows)
        self.assertNotIn('note',r['transactions'][0]);self.assertEqual(rows[0].note,'private')
        self.assertTrue(all('note' in t for t in make_report(rows,include_notes=True)['transactions']))

    def test_request_and_response(self):
        def opener(req,timeout):
            self.assertEqual(req.full_url,'https://openrouter.ai/api/v1/chat/completions')
            data=json.loads(req.data)
            self.assertEqual(data['model'],'vendor/model:free');self.assertEqual(timeout,45)
            self.assertNotIn('test-key',req.data.decode())
            return io.BytesIO(json.dumps({'choices':[{'message':{'content':'Test explanation'},'finish_reason':'stop'}]}).encode())
        self.assertEqual(ask_openrouter('test-key','vendor/model:free','Explain',make_report(self.rows()),opener=opener),'Test explanation')

    def test_detailed_report_preserves_every_record(self):
        rows=self.rows();r=make_report(rows,include_notes=True)
        self.assertEqual({t['id'] for t in r['transactions']},{t.id for t in rows})
        self.assertEqual(sum(x['amount_paise'] for x in r['category_by_month']),13122)
        self.assertEqual(sum(x['amount_paise'] for x in r['spending_by_description']),13122)
        self.assertEqual(r['date_range'],{'first':'2026-09-02','last':'2026-10-02'})
        self.assertEqual(r['missing_expense_descriptions'],0)
        private=make_report(rows,include_notes=False)
        self.assertEqual(private['spending_by_description'],[])

    def test_preflight_limits(self):
        def fail(*a,**kw):self.fail('Must not contact network')
        for key,model,q,r in [('', 'v/m:free','q',{}),('key','bad','q',{}),('key','v/m:free','',{}),('key','v/m:free','q',{'data':'x'*100001})]:
            with self.assertRaises(AssistantError):ask_openrouter(key,model,q,r,opener=fail)

    def test_bad_responses(self):
        for payload in (b'bad',b'{}',b'{"choices":[]}',b'{"choices":[{"message":{"content":null}}]}'):
            with self.assertRaises(AssistantError):
                ask_openrouter('key','v/m:free','q',{},opener=lambda *a,**kw:io.BytesIO(payload))

    def test_network_errors_are_safe(self):
        for exc in (HTTPError('url',401,'secret-body',{},None),URLError('secret-body')):
            def opener(*a,**kw):raise exc
            with self.assertRaises(AssistantError) as caught:ask_openrouter('key','v/m:free','q',{},opener=opener)
            self.assertNotIn('secret',str(caught.exception))

    def test_redirect_blocked(self):
        with self.assertRaises(AssistantError):NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_dns_and_timeout_are_distinct(self):
        for reason,expected in [(socket.gaierror(11001,'test'),'DNS'),(TimeoutError(),'45 seconds')]:
            def opener(*a,**kw):raise URLError(reason)
            with self.assertRaisesRegex(AssistantError,expected):
                ask_openrouter('key','v/m:free','q',{},opener=opener)


if __name__=='__main__':unittest.main()
