import sys
from pathlib import Path
import tempfile
import unittest
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
from planning import PlanningBook,forecast,suggestions,goal_status,money,month_date,month_index,apply_scenario
from models import Transaction,TransactionType


def tx(amount,day,category='Food',note='',kind='EXPENSE'):
    return Transaction(type=TransactionType(kind),amount_paise=amount,date=day,category=category,note=note)


def payment(amount,day='2026-01-31',kind='EXPENSE',name='Rent',monthly=True):
    return dict(id='rent',name=name,type=kind,amount=amount,date=day,monthly=monthly,category=name,note='')


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='planning-test-',dir=Path(__file__).resolve().parents[1])
        self.book=PlanningBook(Path(self.temp.name)/'plan.json')
    def tearDown(self):self.temp.cleanup()

    def test_money_is_exact_and_finite(self):
        self.assertEqual(money('1,234.56'),123456)
        for value in ('NaN','Infinity','-1','0.001','','abc','1000000000'):
            with self.subTest(value=value),self.assertRaises(ValueError):money(value)

    def test_month_end_clamping_and_leap_year(self):
        self.assertEqual(month_date(month_index(date(2024,2,1)),31),date(2024,2,29))
        self.assertEqual(month_date(month_index(date(2026,2,1)),31),date(2026,2,28))
        self.book.put('payments',payment(1800000))
        f=forecast([],self.book,date(2026,2,20))
        self.assertEqual(f['due'][0]['date'],'2026-02-28')
        self.assertEqual(f['bills'],1800000)

    def test_history_recurring_and_recorded_bill_not_double_counted(self):
        records=[]
        for m in (1,2,3):
            records.extend([tx(1000000,f'2026-{m:02d}-01',kind='INCOME'),tx(100000,f'2026-{m:02d}-15'),tx(200000,f'2026-{m:02d}-28','Rent')])
        records.extend([tx(200000,'2026-04-28','Rent'),tx(50000,'2026-04-10')])
        self.book.put('payments',payment(200000,day='2026-01-28'))
        f=forecast(records,self.book,date(2026,4,28))
        self.assertEqual(f['bills'],0)
        self.assertEqual(f['variable_total'],50000)
        self.assertEqual(len(f['paid']),1)
        self.assertEqual(f['closing'],f['balance']-50000)

    def test_overdue_is_still_due_but_future_start_is_not(self):
        self.book.put('payments',payment(10000,day='2026-04-05'))
        f=forecast([],self.book,date(2026,4,20));self.assertEqual(f['bills'],10000)
        self.assertEqual(f['due'][0]['source'],'Overdue / unrecorded')
        r=payment(20000,day='2026-05-01');r['id']='future'
        self.book.put('payments',r)
        self.assertEqual(forecast([],self.book,date(2026,4,20))['bills'],10000)

    def test_suggestion_needs_three_consecutive_single_months(self):
        records=[tx(49900,f'2026-{m:02d}-05','Subscriptions','Music') for m in (1,2,3)]
        result=suggestions(records,self.book,date(2026,4,1));self.assertEqual(len(result),1)
        candidate=result[0].copy();candidate['id']='music';self.book.put('payments',candidate)
        self.assertEqual(suggestions(records,self.book,date(2026,4,1)),[])
        self.book.remove('payments','music')
        self.assertEqual(suggestions(records+[tx(49900,'2026-03-15','Subscriptions','Music')],self.book,date(2026,4,1)),[])
        self.book.commit(lambda d:d['dismissed'].append(result[0]['id']))
        self.assertEqual(suggestions(records,self.book,date(2026,4,1)),[])

    def test_scenario_changes_only_variable_spending(self):
        records=[tx(100000,'2026-01-01'),tx(100000,'2026-02-01'),tx(100000,'2026-03-01')]
        self.book.put('payments',payment(200000,day='2026-04-20'))
        before=[t.to_dict() for t in records]
        base=forecast(records,self.book,date(2026,4,10));scenario=forecast(records,self.book,date(2026,4,10),20,30000)
        self.assertEqual(base['variable_total'],100000)
        self.assertEqual(scenario['closing']-base['closing'],-10000)
        self.assertEqual(scenario['bills'],base['bills'])
        preview=apply_scenario(base,20,30000)
        for k in ('closing','lower','upper','capacity'):self.assertEqual(preview[k],scenario[k])
        self.assertEqual([t.to_dict() for t in records],before)
        self.assertLessEqual(scenario['lower'],scenario['closing']);self.assertLessEqual(scenario['closing'],scenario['upper'])

    def test_month_end_has_no_future_variable_spending(self):
        f=forecast([tx(300000,'2026-03-01')],self.book,date(2026,4,30))
        self.assertEqual(f['variable_total'],0)

    def test_sparse_data_does_not_invent_income(self):
        f=forecast([tx(10000,'2026-04-01')],self.book,date(2026,4,3))
        self.assertEqual(f['income'],0);self.assertEqual(f['variable_total'],0)
        f=forecast([tx(10000,'2026-04-01')],self.book,date(2026,4,10))
        self.assertEqual(f['variable_total'],20000)

    def test_future_transactions_excluded(self):
        f=forecast([tx(10000,'2026-05-01')],self.book,date(2026,4,10))
        self.assertEqual(f['balance'],0)

    def test_balance_snapshot_includes_later_same_day_records(self):
        a=tx(10000,'2026-04-10');b=tx(20000,'2026-04-10')
        self.book.commit(lambda d:d.__setitem__('balance',{'date':'2026-04-10','amount':500000,'ids':[a.id]}))
        self.assertEqual(forecast([a,b],self.book,date(2026,4,10))['balance'],480000)

    def test_goal_math_and_overdue(self):
        g=dict(name='Laptop',date='2026-06-30',target=100000,saved=10000)
        status=goal_status(g,date(2026,4,10));self.assertEqual(status['monthly'],30000)
        g['target']=100001;self.assertEqual(goal_status(g,date(2026,4,10))['monthly'],30001)
        self.assertTrue(goal_status(g,date(2026,7,1))['overdue'])
        g['saved']=120000;self.assertEqual(goal_status(g,date(2026,7,1))['monthly'],0)
        self.assertTrue(goal_status(g,date(2026,7,1))['complete'])

    def test_manual_override_is_month_scoped(self):
        records=[tx(100000,'2026-03-01')]
        self.book.commit(lambda d:d.__setitem__('overrides',{'2026-04|Food':25000}))
        april=forecast(records,self.book,date(2026,4,10))
        self.assertEqual(april['variable_total'],25000)
        may=forecast(records,self.book,date(2026,5,10))
        self.assertNotEqual(may['variable_total'],25000)
        self.book.commit(lambda d:d['overrides'].__setitem__('2026-04|Food',0))
        self.assertEqual(forecast(records,self.book,date(2026,4,10))['variable_total'],0)

    def test_persistence_and_duplicate_protection(self):
        self.book.put('payments',payment(20000))
        r=payment(20000);r['id']='duplicate'
        with self.assertRaises(ValueError):self.book.put('payments',r)
        reloaded=PlanningBook(self.book.path);self.assertEqual(reloaded.data,self.book.data)
        reloaded.path.write_text('broken',encoding='utf-8');reloaded=PlanningBook(self.book.path)
        self.assertTrue(reloaded.error)
        with self.assertRaises(ValueError):reloaded.put('payments',payment(10000))
        self.assertEqual(reloaded.path.read_text(),'broken')

if __name__=='__main__':unittest.main()
