"""
Key findings for the README: change in surgical volume, waitlist and wait times
between fiscal 2019/20 and 2024/25, by health authority, procedure and hospital.

Usage (after running clean_wait_times.py):
    python scripts/analyze.py [path/to/wait_times_clean.csv]
"""
import sys
import pandas as pd
pd.set_option('display.width',200)
df=pd.read_csv(sys.argv[1] if len(sys.argv)>1 else 'data/processed/wait_times_clean.csv')
A='2019/20'; B='2024/25'
def yr(d,y): return d[d.fiscal_year==y]

print("== 1. Health authorities, all procedures ==")
ha=df[(df.level.isin(['health_authority','province']))&df.is_all_procedures]
rows=[]
for h,g in ha.groupby('health_authority'):
    a,b=yr(g,A).set_index('quarter'),yr(g,B).set_index('quarter')
    rows.append(dict(ha=h,
      completed_19=a.completed.sum(), completed_24=b.completed.sum(),
      waiting_Q4_19=a.loc['Q4','waiting'], waiting_Q4_24=b.loc['Q4','waiting'],
      med_19=a.median_wait_weeks.round(1).tolist(), med_24=b.median_wait_weeks.round(1).tolist(),
      p90_19=a.p90_wait_weeks.round(1).tolist(), p90_24=b.p90_wait_weeks.round(1).tolist(),
      p90_q_change=(b.p90_wait_weeks-a.p90_wait_weeks).round(1).tolist()))
r=pd.DataFrame(rows); r['completed_chg%']=((r.completed_24/r.completed_19-1)*100).round(1)
r['waiting_chg%']=((r.waiting_Q4_24/r.waiting_Q4_19-1)*100).round(1)
print(r[['ha','completed_19','completed_24','completed_chg%','waiting_Q4_19','waiting_Q4_24','waiting_chg%']].to_string(index=False))
print(r[['ha','p90_19','p90_24','p90_q_change']].to_string(index=False))
print(r[['ha','med_19','med_24']].to_string(index=False))

print("\n== 2. Fraser procedures, longest p90 in 2024/25 (completed>=20 each quarter) ==")
f=df[(df.level=='health_authority')&(df.health_authority=='Fraser')&~df.is_all_procedures&(df.fiscal_year==B)]
p=f.pivot_table(index='procedure_group',columns='quarter',values='p90_wait_weeks')
c=f.groupby('procedure_group').completed.agg(['sum','min'])
p=p.join(c).dropna()
p=p[p['min']>=20]
p['q_range']=p[['Q1','Q2','Q3','Q4']].min(axis=1).round(1).astype(str)+'-'+p[['Q1','Q2','Q3','Q4']].max(axis=1).round(1).astype(str)
print(p.sort_values('Q4',ascending=False).head(12)[['Q1','Q2','Q3','Q4','sum']].round(1).to_string())

print("\n== 3. Province procedures: p90 same-quarter change 2019/20 -> 2024/25 ==")
pr=df[(df.level=='province')&~df.is_all_procedures]
a=yr(pr,A).pivot_table(index='procedure_group',columns='quarter',values='p90_wait_weeks')
b=yr(pr,B).pivot_table(index='procedure_group',columns='quarter',values='p90_wait_weeks')
cnt=yr(pr,B).groupby('procedure_group').completed.sum()
d=(b-a).dropna(); d['med_chg']=d.median(axis=1); d['completed_24']=cnt
d=d[d.completed_24>=400]
print("Worse:\n",d.sort_values('med_chg',ascending=False).head(8).round(1).to_string())
print("Better:\n",d.sort_values('med_chg').head(8).round(1).to_string())

print("\n== 4. Fraser hospitals, all procedures, 2024/25 Q4 ==")
h=df[(df.level=='hospital')&(df.health_authority=='Fraser')&df.is_all_procedures&(df.fiscal_year==B)&(df.quarter=='Q4')]
print(h.sort_values('p90_wait_weeks',ascending=False)[['hospital_name','waiting','completed','median_wait_weeks','p90_wait_weeks']].to_string(index=False))
