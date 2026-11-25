import copy
import unittest
from skill_regressed_release_v1_43 import *
from projection_phase_v1_42 import population
def actuals():
    actual={}
    for y in range(2022,2027):
        for i in range(80):
            p=str(i+1)
            for role,v in (
             ('hitter',dict(PA=400,AB=350,BB=30,HBP=5,SF=5,SH=0,H=90,**{'1B':60,'2B':20,'3B':2},HR=8,R=40,RBI=40,SB=5,
                          AVG=90/350,OBP=125/390,SLG=138/350,OPS=125/390+138/350)),
             ('pitcher',dict(OUTS=300,H=90,BB=30,ER=40,HR=10,SO=100,W=5,SV=4,HLD=3,G=40,GS=10,QS=3,ERA=3.6,WHIP=1.2))):
                for m,n in v.items():actual[y,role,p,m]=n
    return actual
def frozen_input(role):
    a=actuals();b=project(a,role,'1',2027)
    c,ok,_=skill_candidate(b,a,role,'1',2027,population(a,2026))
    return dict(b,name='Test',exceptions='LOW_HISTORY',skill_method='weighted_actuals'),dict(
        season='2027',player_type=role,mlbam_id='1',skill_supported='True',
        **{'baseline__'+m:b[m] for m in FIELDS[role]},
        **{'skill_regression__'+m:c[m] for m in FIELDS[role]})
class ReleaseTests(unittest.TestCase):
    def test_publish_exact_candidate_and_anchors(self):
        for role in FIELDS:
            b,c=frozen_input(role);b['season']='2027'
            rows,exc,changes,anchors=publish_rows([b],[c],role);r=rows[0]
            for m in FIELDS[role]:self.assertEqual(r[m],c['skill_regression__'+m])
            for m in set(FIELDS[role])-MUTABLE[role]:self.assertEqual(r[m],b[m])
            self.assertEqual(r['skill_method'],'skill_regression')
            self.assertIsNone(r['hybrid_qs']);self.assertFalse(r['valuation_enabled'])
            if role=='pitcher':self.assertEqual(anchors[0]['SV'],b['SV'])
    def test_fallback_never_fills_missing(self):
        b,c=frozen_input('hitter');b['season']='2027'
        c['skill_supported']='False'
        for m in FIELDS['hitter']:c['skill_regression__'+m]=b[m]
        for m in ('1B','H','AVG','OBP','SLG','OPS'):
            b[m]=None;c['baseline__'+m]=None;c['skill_regression__'+m]=None
        rows,ex,_,_=publish_rows([b],[c],'hitter')
        self.assertIsNone(rows[0]['H'])
        self.assertEqual(rows[0]['skill_method'],'weighted_actuals_fallback')
        self.assertTrue(any(r['issue']=='BASELINE_FALLBACK_UNSUPPORTED_SKILL' for r in ex))
    def test_changed_workload_or_saves_rejected(self):
        for m in ('IP','SV','HLD','W','QS'):
            b,c=frozen_input('pitcher');b['season']='2027';c['skill_regression__'+m]+=1
            with self.assertRaises(ValueError):publish_rows([b],[c],'pitcher')
    def test_eval_forecasts_are_prehistory_only(self):
        a=actuals();hist={k:v for k,v in a.items() if k[0]<2026}
        before=copy.deepcopy(hist)
        rows=evaluation_forecasts(hist,population(hist,2026))
        self.assertTrue(rows);self.assertEqual(hist,before)
        with self.assertRaises(ValueError):evaluation_forecasts(a,population(hist,2026))
    def test_eval_matched_exposure_and_known_zero_vs_missing(self):
        a=actuals();hist={k:v for k,v in a.items() if k[0]<2026};bank=population(hist,2026)
        rows=evaluation_forecasts(hist,bank)
        # CSV reader returns strings; simulate frozen publication output.
        rr=[{k:str(v) if v is not None else '' for k,v in r.items()} for r in rows if r['mlbam_id'] in ('1','2')]
        truth={k:v for k,v in a.items() if k[0]==2026}
        for m in list(FIELDS['pitcher']):
            truth.pop((2026,'pitcher','2',m),None)
        truth[2026,'pitcher','2','OUTS']=0;truth[2026,'pitcher','2','G']=0
        scores,details,cov=score_evaluation(rr,truth)
        self.assertTrue(any(r['metric']=='IP' and r['mlbam_id']=='2' and r['actual']==0 for r in details))
        self.assertFalse(any(r['metric'] in ('ERA','WHIP','SO','W') and r['player_type']=='pitcher' and r['mlbam_id']=='2' for r in details))
        self.assertTrue(any(r['actual_exposure_band']=='ACTUAL_IP_GE100' for r in details if r['player_type']=='pitcher'))
        grouped={}
        for r in scores:
            k=r['player_type'],r['metric'],r['cohort'],r['pool'];grouped.setdefault(k,set()).add((r['n'],r['membership_sha256']))
        self.assertTrue(all(len(v)==1 for v in grouped.values()))
    def test_duplicate_future_population_rejected(self):
        b,c=frozen_input('pitcher');b['season']='2027'
        with self.assertRaises(ValueError):publish_rows([b,b],[c],'pitcher')
        c['season']='2028'
        with self.assertRaises(ValueError):publish_rows([b],[c],'pitcher')
    def test_decision_uses_only_original_passed_skill_gates(self):
        gates=[dict(role=r,experiment='SKILL',eligible=True,selected_for_research='skill_regression',origin=2026) for r in FIELDS]
        f=dict(selection_max_year=2025,skill_population_origin=2026,skill_population=population(actuals(),2026),final_historical_gates=gates)
        r=dict(version='1.42.0',selection_uses_2026=False,defaults_changed=False,final_historical_gates=gates)
        decision(r,f,CONTRACT)
        c=copy.deepcopy(CONTRACT);c['skill_prior_exposure']['hitter_AB']=300
        with self.assertRaises(ValueError):decision(r,f,c)
        f['selection_max_year']=2026
        with self.assertRaises(ValueError):decision(r,f,CONTRACT)

if __name__=='__main__':unittest.main()

class PublicationPipelineTests(unittest.TestCase):
    def test_publication_then_separate_evaluation_and_tamper(self):
        import csv,sys,tempfile,types
        from types import SimpleNamespace
        from unittest.mock import patch
        fake=types.ModuleType('duckdb')
        with patch.dict(sys.modules,{'duckdb':fake}):
            from standalone_io_v1_0 import dump,sha,tree
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);phase=root/'phase';lab=root/'lab';ov=root/'ov';research=root/'research';ev=root/'ev'
                for p in (phase,lab,ov,research,ev):p.mkdir()
                actual=actuals();hist={k:v for k,v in actual.items() if k[0]<2026};truth={k:v for k,v in actual.items() if k[0]==2026}
                bank=population(hist,2026)
                gates=[dict(role=r,experiment='SKILL',eligible=True,selected_for_research='skill_regression',origin=2026) for r in FIELDS]
                dump(phase/'release_report.json',dict(version='1.42.0',selection_uses_2026=False,defaults_changed=False,
                     final_historical_gates=gates,forecast_counts=dict(hitter=1,pitcher=1)))
                dump(phase/'frozen_choices.json',dict(selection_max_year=2025,skill_population_origin=2026,
                     skill_population=bank,final_historical_gates=gates))
                dump(phase/'experiment_contract.json',CONTRACT)
                def put(p,rows):
                    fields=list(dict.fromkeys(k for r in rows for k in r))
                    with p.open('w',newline='') as f:
                        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
                for role in FIELDS:
                    b,c=frozen_input(role);b['season']='2027'
                    c.update({'freshness_workload__'+m:b[m] if m!='QS' else None for m in FIELDS[role]})
                    put(phase/f'default_2027_{role}s.csv',[b])
                    put(phase/f'research_candidates_2027_{role}s.csv',[c])
                train=lab/'training_labels.parquet';train.write_bytes(b'train')
                hold=lab/'holdout_labels.parquet';hold.write_bytes(b'outcomes')
                hp=research/'historical_forecasts.csv';hp.write_text('historical')
                dump(ov/'report.json',dict(version='1.27.0'))
                op=ov/'participation_label_overlay.csv';op.write_text('fixture')
                dump(ev/'report.json',dict(version='1.29.0',season_certified=True,complete_pool_scored=True,preseason_pool=1))
                ep=ev/'evaluation_label_overlay_2026.csv'
                put(ep,[dict(season='2026',mlbam_id='1',status='VERIFIED_APPEARED',evaluation_g=40,evaluation_outs=300)])
                bp=[train,hold,hp,ov/'report.json',op,ev/'report.json',ep]
                dump(phase/'input_hashes.json',{str(p):sha(p) for p in bp})
                for p in (phase,lab,ov,research,ev):dump(p/'output_sha256.json',tree(p))
                before={str(p):tree(p) for p in (phase,lab,ov,research,ev)}
                state={'eval':False}
                def label_loader(p,year=None):
                    if year==2026:
                        self.assertTrue(state['eval'],'Publisher may not open outcome labels')
                        return dict(truth)
                    return dict(hist)
                def overlay(p,source,train,hp,w):
                    for x in (p/'report.json',p/'participation_label_overlay.csv'):w[str(x)]=sha(x)
                    return source,{}
                inputs=types.ModuleType('recent_skill_inputs_v1_23');inputs.labels=label_loader
                overlays=types.ModuleType('participation_label_overlay_v1_27');overlays.apply_overlay=overlay
                with patch.dict(sys.modules,{'recent_skill_inputs_v1_23':inputs,'participation_label_overlay_v1_27':overlays}):
                    args=SimpleNamespace(phase=phase,labels=lab,overlay=ov,research=research,output=root/'release',backup_root=root/'backups')
                    result=build(args)
                    self.assertFalse(result['evaluation_outcomes_read'])
                    self.assertEqual(tree(root/'release'),tree(Path(result['backup'])))
                    originalpub=tree(root/'release')
                    self.assertEqual(before,{str(p):tree(p) for p in (phase,lab,ov,research,ev)})
                    state['eval']=True
                    ea=SimpleNamespace(release=root/'release',labels=lab,evaluation=ev,output=root/'eval',backup_root=root/'backups')
                    er=evaluate(ea)
                    self.assertFalse(er['choices_changed']);self.assertEqual(originalpub,tree(root/'release'))
                    self.assertEqual(tree(root/'eval'),tree(Path(er['backup'])))
                    # Different 2026 outcomes can change reporting only; never publication.
                    truth[2026,'pitcher','1','ERA']=99
                    ea.output=root/'eval2';evaluate(ea)
                    self.assertEqual(originalpub,tree(root/'release'))
                    with self.assertRaises(FileExistsError):build(args)
                    hold.write_bytes(b'tampered')
                    ea.output=root/'bad'
                    with self.assertRaises(ValueError):evaluate(ea)
                    self.assertFalse(ea.output.exists())
