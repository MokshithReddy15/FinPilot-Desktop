"""Deterministic planning in integer paise; estimates never mutate transactions."""
from calendar import monthrange
from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import statistics
import uuid


def money(value, allow_zero=True):
    try:
        n=Decimal(str(value).replace(',', '').strip())
        if not n.is_finite() or n<0 or n>Decimal('999999999.99') or n.as_tuple().exponent < -2:
            raise ValueError('Use a non-negative amount with at most two decimal places.')
        if not allow_zero and n==0:raise ValueError('Amount must be greater than zero.')
        return int(n*100)
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid amount.') from None


def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def month_index(d):return d.year*12+d.month-1


def month_date(index,day=1):
    y,m=divmod(index,12);m+=1
    return date(y,m,min(day,monthrange(y,m)[1]))


def key(tx):
    return (tx.type.value,tx.category.casefold().strip(),re.sub(r'\s+',' ',tx.note.casefold().strip()))


def rule_key(rule):return (rule['type'],rule['category'].casefold().strip(),re.sub(r'\s+',' ',rule['note'].casefold().strip()))


def matches(tx,rule):
    return key(tx)==rule_key(rule) and abs(tx.amount_paise-rule['amount'])<=max(100,rule['amount']//10)


class PlanningBook:
    def __init__(self,path):
        self.path=Path(path)
        self.data={'version':1,'payments':[],'goals':[],'dismissed':[],'balance':None}
        self.error=''
        if self.path.exists():
            try:
                candidate=json.loads(self.path.read_text(encoding='utf-8'))
                self.validate(candidate);self.data=candidate
            except (OSError,ValueError,KeyError,TypeError) as exc:
                self.error=f'Planning file could not be loaded: {exc}. Original file preserved.'

    @staticmethod
    def validate(data):
        if data.get('version')!=1:raise ValueError('Unsupported planning file version')
        for name in ('payments','goals','dismissed'):
            if not isinstance(data.get(name),list):raise ValueError(f'Invalid {name}')
        ids=set()
        for r in data['payments']:
            if r['id'] in ids:raise ValueError('Duplicate payment ID')
            ids.add(r['id'])
            if not r['name'].strip() or r['type'] not in ('INCOME','EXPENSE'):raise ValueError('Invalid payment')
            if type(r['amount']) is not int or r['amount']<=0:raise ValueError('Invalid payment amount')
            date.fromisoformat(r['date'])
            if type(r['monthly']) is not bool:raise ValueError('Invalid recurrence')
            if not isinstance(r['category'],str) or not isinstance(r['note'],str):raise ValueError('Invalid matching details')
        for g in data['goals']:
            date.fromisoformat(g['date'])
            if not g['name'].strip() or any(type(g[k]) is not int or g[k]<0 for k in ('target','saved')) or g['target']<=0:
                raise ValueError('Invalid goal amount')
        overrides=data.get('overrides',{})
        if not isinstance(overrides,dict) or any(not isinstance(k,str) or type(v) is not int or v<0 for k,v in overrides.items()):raise ValueError('Invalid spending override')
        b=data.get('balance')
        if b is not None:
            date.fromisoformat(b['date'])
            if type(b['amount']) is not int:raise ValueError('Invalid balance')

    def commit(self,mutator):
        if self.error:raise ValueError(self.error)
        candidate=deepcopy(self.data);mutator(candidate);self.validate(candidate)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(candidate,indent=2),encoding='utf-8');temp.replace(self.path)
        self.data=candidate

    def put(self,collection,item):
        item=deepcopy(item);item.setdefault('id',str(uuid.uuid4()))
        if collection=='payments':
            for old in self.data['payments']:
                if old['id']!=item['id'] and rule_key(old)==rule_key(item) and old['date']==item['date'] and old['monthly']==item['monthly']:
                    raise ValueError('This payment is already planned. Edit the existing payment.')
        def change(d):
            d[collection]=[r for r in d[collection] if r['id']!=item['id']]+[item]
        self.commit(change)
        return item['id']

    def remove(self,collection,identifier):
        self.commit(lambda d:d.__setitem__(collection,[r for r in d[collection] if r['id']!=identifier]))


def suggestions(transactions,book,today):
    groups=defaultdict(list)
    for tx in transactions:
        if date.fromisoformat(tx.date)<=today:groups[key(tx)].append(tx)
    confirmed={rule_key(r) for r in book.data['payments'] if r['monthly']}
    result=[]
    for signature,items in groups.items():
        token=json.dumps(signature)
        if signature in confirmed or token in book.data['dismissed']:continue
        months=defaultdict(list)
        for tx in items:months[month_index(date.fromisoformat(tx.date))].append(tx)
        indexes=sorted(months)[-3:]
        if len(indexes)<3 or indexes[-1]-indexes[0]!=2 or indexes[-1]<month_index(today)-1:continue
        if any(len(months[m])!=1 for m in indexes):continue
        sample=[months[m][0] for m in indexes]
        amounts=[t.amount_paise for t in sample];days=[date.fromisoformat(t.date).day for t in sample]
        amount=rounded(statistics.median(amounts))
        if max(amounts)-min(amounts)>max(100,amount//10) or max(days)-min(days)>4:continue
        tx=sample[-1];day=rounded(statistics.median(days))
        result.append({'id':token,'name':tx.note or tx.category,'category':tx.category,'note':tx.note,
                       'type':tx.type.value,'amount':amount,'date':month_date(month_index(today),day).isoformat(),'monthly':True})
    return result


def forecast(transactions,book,today,reduction=0,purchase=0):
    """Closing balance = as-of balance + unpaid income - unpaid bills - variable spend.

    Historical recurring matches are removed one occurrence per rule/month.
    A recorded payment consumes at most one schedule occurrence.
    Uncertainty is a historical spending scenario range, not a confidence interval.
    """
    if not 0<=reduction<=50 or purchase<0:raise ValueError('Invalid scenario')
    end=date(today.year,today.month,monthrange(today.year,today.month)[1])
    txs=sorted([t for t in transactions if date.fromisoformat(t.date)<=today],key=lambda t:t.date)
    current=[t for t in txs if t.date[:7]==today.strftime('%Y-%m')]
    balance_record=book.data.get('balance')
    if balance_record and date.fromisoformat(balance_record['date'])<=today:
        anchor=date.fromisoformat(balance_record['date'])
        balance=balance_record['amount']+sum(t.amount_paise*(1 if t.type.value=='INCOME' else -1) for t in txs if date.fromisoformat(t.date)>anchor or (date.fromisoformat(t.date)==anchor and t.id not in balance_record.get('ids',[])))
        balance_source=f"Balance snapshot on {anchor.isoformat()}; later records included"
    else:
        balance=sum(t.amount_paise*(1 if t.type.value=='INCOME' else -1) for t in txs)
        balance_source='Recorded net balance (assumes zero before first transaction); set your actual balance for a bank-balance forecast'
    consumed=set();due=[];paid=[]
    for r in sorted(book.data['payments'],key=lambda r:r['date']):
        start=date.fromisoformat(r['date'])
        if r['monthly']:
            occurrence=month_date(month_index(today),start.day)
            if occurrence<start:continue
        else:occurrence=start
        if occurrence.year!=today.year or occurrence.month!=today.month:continue
        found=next((t for t in current if t.id not in consumed and matches(t,r) and abs((date.fromisoformat(t.date)-occurrence).days)<=7),None)
        if found:consumed.add(found.id);paid.append((r,found));continue
        due.append({'name':r['name'],'amount':r['amount'],'type':r['type'],'date':occurrence.isoformat(),
                    'source':'Overdue / unrecorded' if occurrence<today else 'Confirmed schedule'})
    # Exclude exactly one matching historical occurrence per scheduled rule/month.
    excluded=set(consumed)
    for r in book.data['payments']:
        if not r['monthly']:continue
        groups=defaultdict(list)
        for t in txs:
            if t.id not in excluded and matches(t,r):groups[t.date[:7]].append(t)
        for period,items in groups.items():
            if period==today.strftime('%Y-%m'):continue
            y,m=map(int,period.split('-'));occ=month_date(y*12+m-1,date.fromisoformat(r['date']).day)
            near=sorted(items,key=lambda t:abs((date.fromisoformat(t.date)-occ).days))
            if abs((date.fromisoformat(near[0].date)-occ).days)<=7:excluded.add(near[0].id)
    first=min((date.fromisoformat(t.date) for t in txs),default=today)
    # Discard partial first month: a mid-month import is not a complete spending sample.
    first_index=month_index(first)+(first.day!=1)
    sample_months=list(range(max(first_index,month_index(today)-3),month_index(today)))
    cats=sorted({t.category for t in txs if t.type.value=='EXPENSE' and t.id not in excluded})
    variable=[]
    for cat in cats:
        spent=sum(t.amount_paise for t in current if t.type.value=='EXPENSE' and t.category==cat and t.id not in excluded)
        totals=[sum(t.amount_paise for t in txs if t.type.value=='EXPENSE' and t.category==cat and t.id not in excluded and month_index(date.fromisoformat(t.date))==m) for m in sample_months]
        if totals:
            base=max(0,rounded(statistics.mean(totals))-spent)
            low=max(0,min(totals)-spent);high=max(base,max(totals)-spent)
            source=f'{len(totals)} complete months; less recorded spending'
        elif today.day>=7:
            base=rounded(Decimal(spent)*(end.day-today.day)/today.day)
            low=base*75//100;high=(base*125+99)//100;source='Current daily pace; illustrative ±25% range'
        else:base=low=high=0;source='Insufficient history; enter planned expenses'
        override_key=today.strftime('%Y-%m')+'|'+cat
        if override_key in book.data.get('overrides',{}):
            base=low=high=book.data['overrides'][override_key];source='Your remaining-spend estimate for this month'
        if today==end:base=low=high=0
        variable.append({'name':cat,'amount':base,'low':low,'high':high,'source':source})
    income=sum(r['amount'] for r in due if r['type']=='INCOME')
    bills=sum(r['amount'] for r in due if r['type']=='EXPENSE')
    total=sum(r['amount'] for r in variable);low=sum(r['low'] for r in variable);high=sum(r['high'] for r in variable)
    saved=rounded(Decimal(total)*Decimal(str(reduction))/100)
    adjusted=total-saved
    lower=balance+income-bills-rounded(Decimal(high)*(100-Decimal(str(reduction)))/100)-purchase
    upper=balance+income-bills-rounded(Decimal(low)*(100-Decimal(str(reduction)))/100)-purchase
    income_month=sum(t.amount_paise for t in current if t.type.value=='INCOME')+income
    expense_month=sum(t.amount_paise for t in current if t.type.value=='EXPENSE')+bills+adjusted+purchase
    return dict(asof=today.isoformat(),balance=balance,balance_source=balance_source,income=income,bills=bills,variable=variable,variable_total=total,
                closing=balance+income-bills-adjusted-purchase,lower=lower,upper=upper,due=due,paid=paid,
                remaining_days=end.day-today.day,history=len(sample_months),saved=saved,purchase=purchase,
                surplus=income_month-expense_month,capacity=max(0,income_month-expense_month),end=end.isoformat())


def goal_status(goal,today):
    target,saved=goal['target'],goal['saved'];deadline=date.fromisoformat(goal['date'])
    left=max(0,target-saved)
    months=max(1,month_index(deadline)-month_index(today)+1)
    return dict(remaining=left,monthly=(left+months-1)//months,progress=min(100,saved*100/target),
                overdue=deadline<today and left>0,complete=left==0,months=months)


def apply_scenario(base,reduction=0,purchase=0):
    """Cheap, pure preview from the unchanged baseline; safe for slider animation."""
    if not 0<=reduction<=50 or purchase<0:raise ValueError('Invalid scenario')
    result=dict(base)
    fraction=Decimal(str(reduction))/100
    saved=rounded(Decimal(base['variable_total'])*fraction)
    delta=saved-purchase
    result.update(saved=saved,purchase=purchase,closing=base['closing']+delta,
                  lower=base['balance']+base['income']-base['bills']-rounded(Decimal(sum(r['high'] for r in base['variable']))*(1-fraction))-purchase,
                  upper=base['balance']+base['income']-base['bills']-rounded(Decimal(sum(r['low'] for r in base['variable']))*(1-fraction))-purchase,
                  surplus=base['surplus']+delta,capacity=max(0,base['surplus']+delta))
    return result
