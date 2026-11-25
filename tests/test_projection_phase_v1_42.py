import copy
import unittest
from projection_phase_v1_42 import *
def fixture(role='pitcher'):
    a={}
    for y in range(2015,2027):
        for i in range(80):
            p=str(i+1)
            v=(dict(OUTS=300,H=90,BB=30,ER=40,HR=10,SO=100,W=5,SV=0,HLD=0,G=40,GS=10,QS=3,IP=100,ERA=3.6,WHIP=1.2)
              if role=='pitcher' else dict(PA=400,AB=350,BB=30,HBP=5,SF=5,SH=0,H=90,**{'1B':60,'2B':20,'3B':2},HR=8,R=40,RBI=40,SB=5,
                                          AVG=90/350,OBP=125/390,SLG=138/350,OPS=125/390+138/350))
            for m,n in v.items():a[y,role,p,m]=n
    return a

class CoreTests(unittest.TestCase):
    def test_population_future_invariance(self):
        a=fixture();b=population(a,2025)
        a.update({(2025,'pitcher','1','ER'):999999,(2026,'pitcher','1','ER'):999999})
        self.assertEqual(population(a,2025),b)
        with self.assertRaises(ValueError):population(a,2027)
    def test_regression_sample_strength_and_frozen_workload(self):
        a=fixture();b=project(a,'pitcher','1',2025);bank=population(a,2025)
        # An extreme tiny sample should be pulled toward the prior, without clipping.
        for y in range(2021,2025):
            for m in ('OUTS','H','ER','BB','HR','SO'):
                a[y,'pitcher','1',m]=1 if m=='OUTS' else 5
        b=project(a,'pitcher','1',2025)
        c,ok,trace=skill_candidate(b,a,'pitcher','1',2025,bank)
        self.assertTrue(ok);self.assertLess(c['ERA'],b['ERA']);self.assertEqual(c['OUTS'],b['OUTS'])
        self.assertEqual(c['SV'],b['SV']);self.assertEqual(c['HLD'],b['HLD'])
        self.assertEqual(trace[0]['raw_denominator'],4)
        verify_vector(c,'pitcher')
    def test_masked_component_no_population_only_fill(self):
        a=fixture();bank=population(a,2025)
        for y in range(2021,2025):del a[y,'pitcher','1','ER']
        b=project(a,'pitcher','1',2025);c,ok,_=skill_candidate(b,a,'pitcher','1',2025,bank)
        self.assertFalse(ok);self.assertEqual(c,b)
    def test_hitter_coherence_anchors(self):
        a=fixture('hitter');b=project(a,'hitter','1',2025)
        c,ok,_=skill_candidate(b,a,'hitter','1',2025,population(a,2025))
        self.assertTrue(ok);verify_vector(c,'hitter')
        for m in ('PA','AB','R','RBI','SB','BB','HBP','SF'):self.assertEqual(c[m],b[m])
    def test_workload_fit_earlier_only_and_unknown_omitted(self):
        b=project(fixture(),'pitcher','1',2025)
        ctx=dict(group='KNOWN_ZERO_RECENT|UNKNOWN')
        rr=[dict(season=2023,role='pitcher',actual_exposure=0,baseline=b,context=ctx),
            dict(season=2024,role='pitcher',actual_exposure=None,baseline=b,context=ctx)]
        m=fit_freshness(rr,2025)
        rr.append(dict(season=2025,role='pitcher',actual_exposure=999999,baseline=b,context=ctx))
        self.assertEqual(m,fit_freshness(rr,2025))
        self.assertEqual(m['pitcher'][ctx['group']]['n'],1)
        c,ok,f=workload_candidate(b,ctx,'pitcher',m)
        self.assertTrue(ok);self.assertLess(f,1);self.assertIsNone(c['QS'])
        for k in ('ERA','WHIP','SV','HLD'):self.assertEqual(c[k],b[k])
        verify_vector(c,'pitcher')
    def test_unknown_not_zero_and_preseason_context_only(self):
        a=fixture()
        for y in (2025,2026):a.pop((y,'pitcher','1','OUTS'))
        c=context(a,'pitcher','1',2026)
        self.assertEqual(c['freshness'],'UNKNOWN_RECENT')
        a[2025,'pitcher','1','OUTS']=0
        self.assertEqual(context(a,'pitcher','1',2026)['freshness'],'KNOWN_ZERO_RECENT')
        self.assertEqual(c['returner'],'EARLIER_SUBSTANTIAL_NO_RECENT_POSITIVE')
    def test_selection_future_cannot_change_gate(self):
        rows=[]
        for y in (2022,2023,2024):
            for metric in ('IP',):
                for cohort in ('ALL','LOW_HISTORY'):
                    for arm,mse in [('weighted_actuals',100),('freshness_workload',90)]:
                        rows.append(dict(season=y,role='pitcher',experiment='WORKLOAD',pool='SUPPORTED',
                          metric=metric,cohort=cohort,method=arm,n=50,mse=mse,membership_sha256='same'))
        g=gate(rows,'pitcher','WORKLOAD',2025)
        self.assertTrue(g['eligible']);self.assertFalse(g['default_changed'])
        future=[dict(r,season=2025,mse=1e9) for r in rows]
        self.assertEqual(g,gate(rows+future,'pitcher','WORKLOAD',2025))
        with self.assertRaises(ValueError):gate(rows,'pitcher','WORKLOAD',2027)
    def test_recent_bad_year_not_hidden(self):
        rows=[]
        for y in (2022,2023,2024):
            for cohort in ('ALL','LOW_HISTORY'):
                for arm,mse in [('weighted_actuals',100),('freshness_workload',10 if y<2024 else 104)]:
                    rows.append(dict(season=y,role='pitcher',experiment='WORKLOAD',pool='SUPPORTED',
                        metric='IP',cohort=cohort,method=arm,n=50,mse=mse,membership_sha256='same'))
        self.assertIn('RECENT_GUARD_2024',gate(rows,'pitcher','WORKLOAD',2025)['reasons'])
    def test_bad_coherence_rejected(self):
        b=project(fixture(),'pitcher','1',2025);b['ERA']+=1
        with self.assertRaises(ValueError):verify_vector(b,'pitcher')
    def test_historical_engine_2021_and_source_immutable(self):
        a=fixture();a.update(fixture('hitter'));before=dict(a)
        rec,scores,gates,final,bank,wm,priors,models=develop(a)
        self.assertIn(2021,{r['season'] for r in scores})
        self.assertEqual(a,before)
        self.assertTrue(all(y<2026 for y in map(int,priors)))
        for y,m in models.items():
            for role,groups in m.items():
                for g in groups.values():self.assertLess(g['max_label_year'],int(y))
        self.assertTrue(all(g['origin']==2026 for g in final))
        # 2026 outcome mutations cannot affect either experiment.
        changed={k:(99999 if k[0]==2026 else v) for k,v in a.items()}
        result=develop(changed)
        self.assertEqual(final,result[3]);self.assertEqual(bank,result[4]);self.assertEqual(wm,result[5])

if __name__=='__main__':unittest.main()

class PipelineTests(unittest.TestCase):
    def test_freeze_before_2026_export_backup_and_tamper(self):
        import csv,sys,tempfile,types
        from unittest.mock import patch
        from types import SimpleNamespace
        # Isolate the already-tested data adapters; use real manifest/publication IO.
        from pathlib import Path
        fake_duck=types.ModuleType('duckdb')
        with patch.dict(sys.modules,{'duckdb':fake_duck}):
            from standalone_io_v1_0 import dump,sha,tree
            actual=fixture();actual.update(fixture('hitter'))
            history={k:v for k,v in actual.items() if k[0]<2026}
            future={k:v for k,v in actual.items() if k[0]==2026}
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);paths={k:root/k for k in ('audit','review','baseline','labels','overlay','research','evaluation')}
                for p in paths.values():p.mkdir()
                def put(p,rows):
                    keys=list(dict.fromkeys(k for r in rows for k in r))
                    with p.open('w',newline='') as f:
                        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
                train=paths['labels']/'training_labels.parquet';train.write_bytes(b'train fixture')
                hold=paths['labels']/'holdout_labels.parquet';hold.write_bytes(b'future fixture')
                hp=paths['research']/'historical_forecasts.csv';hp.write_text('fixture')
                dump(paths['overlay']/'report.json',dict(version='1.27.0'))
                op=paths['overlay']/'participation_label_overlay.csv';op.write_text('fixture')
                dump(paths['baseline']/'report.json',dict(version='1.31.0',forecast_counts=dict(hitter=1,pitcher=1)))
                dump(paths['evaluation']/'report.json',dict(version='1.29.0',season_certified=True,
                    complete_pool_scored=True,preseason_pool=1))
                put(paths['evaluation']/'evaluation_label_overlay_2026.csv',[dict(season='2026',mlbam_id='1',
                    status='VERIFIED_APPEARED',evaluation_g='40',evaluation_outs='300')])
                for role in FIELDS:
                    b=project(actual,role,'1',2027)
                    put(paths['review']/f'named_2027_{role}s.csv',[dict(season='2027',player_type=role,mlbam_id='1',
                        name='Test',**{'weighted_actuals__'+m:b[m] for m in FIELDS[role]})])
                dump(paths['audit']/'report.json',dict(version='1.41.0',baseline_numeric_replay_verified=True))
                bindpaths=[train,hold,hp,paths['overlay']/'report.json',op,paths['evaluation']/'report.json',
                    paths['evaluation']/'evaluation_label_overlay_2026.csv']
                dump(paths['baseline']/'input_hashes.json',{str(p):sha(p) for p in bindpaths})
                ab={str(p):sha(p) for p in bindpaths+[paths['baseline']/'report.json']+
                    [paths['review']/f'named_2027_{r}s.csv' for r in FIELDS]}
                dump(paths['audit']/'input_hashes.json',ab)
                for p in paths.values():dump(p/'output_sha256.json',tree(p))
                before={k:tree(p) for k,p in paths.items()}
                args=SimpleNamespace(**paths,output=root/'out',backup_root=root/'backups')
                def labels(p,year=None):
                    if year==2026:
                        staged=list(root.glob('out.staging-*'))
                        self.assertEqual(len(staged),1)
                        self.assertTrue((staged[0]/'frozen_choices.json').exists())
                        return dict(future)
                    return dict(history)
                def overlay(root,source,train,hp,watched):
                    for p in (root/'report.json',root/'participation_label_overlay.csv'):watched[str(p)]=sha(p)
                    return source,{}
                inputs=types.ModuleType('recent_skill_inputs_v1_23');inputs.labels=labels
                ov=types.ModuleType('participation_label_overlay_v1_27');ov.apply_overlay=overlay
                with patch.dict(sys.modules,{'recent_skill_inputs_v1_23':inputs,'participation_label_overlay_v1_27':ov}):
                    r=run(args)
                    self.assertFalse(r['defaults_changed'])
                    self.assertEqual(tree(root/'out'),tree(Path(r['backup'])))
                    self.assertEqual(before,{k:tree(p) for k,p in paths.items()})
                    for role in FIELDS:
                        row=read(root/'out'/f'default_2027_{role}s.csv')[0]
                        self.assertEqual(float(row['PA' if role=='hitter' else 'IP']),400 if role=='hitter' else 100)
                        self.assertEqual(row['hybrid_qs'],'')
                    with self.assertRaises(FileExistsError):run(args)
                    train.write_bytes(b'tampered')
                    args.output=root/'bad'
                    with self.assertRaises(ValueError):run(args)
                    self.assertFalse(args.output.exists())
