import copy
import unittest
from project_2027_side_by_side_v1_39 import assemble, validate_models, METHODS
from statcast_pull_air_v1_37 import FEATURES, ARMS, TARGETS
from project_2027_v1_31 import FIELDS

def model(role):
    n=len(TARGETS[role])
    return dict(n=120,mean=[0.]*4,scale=[1.]*4,arms={
        a:[[.01]*n]+[[.02]*n for _ in cols]
        for a,cols in ARMS.items() if cols is not None})

def raw(role):
    v={m:0 for m in FIELDS[role]}
    if role=='hitter':
        v.update(PA=120,AB=100,H=30,HR=5,BB=10,HBP=2,SF=1,
                 **{'1B':20,'2B':4,'3B':1},AVG=.3,OBP=42/113,SLG=.51,OPS=42/113+.51)
    else:
        v.update(IP=100,OUTS=300,H=90,BB=30,SO=100,WHIP=1.2,ER=40,ERA=3.6)
    return dict(season='2027',player_type=role,mlbam_id='123',name='Test',**v)

def board(role):
    return {(y,role,'123',m):(.2,50.) for y in (2023,2024,2025,2026) for m in FEATURES}

class ExportTests(unittest.TestCase):
    def test_anchors_and_provenance_both_roles(self):
        for role in FIELDS:
            b=raw(role);source=copy.deepcopy(b)
            rows,changes,prov=assemble([b],role,board(role),model(role),'abc')
            self.assertEqual(b,source)
            r=rows[0]
            for arm in METHODS:
                for m in ('PA','AB','1B','HR','BB') if role=='hitter' else ('IP','OUTS','BB','WHIP','QS','ERA','W','SV','HLD'):
                    self.assertEqual(r[arm+'__'+m],b[m])
            self.assertIsNone(r['hybrid_qs'])
            self.assertFalse(r['valuation_enabled'])
            self.assertEqual({p['source_season'] for p in prov},{2023,2024,2025,2026})
            self.assertEqual(len(changes),2*len(FIELDS[role]))
            if role=='hitter':
                for arm in METHODS:
                    self.assertAlmostEqual(r[arm+'__H'],sum(r[arm+'__'+m] for m in ('1B','2B','3B','HR')))
                    self.assertAlmostEqual(r[arm+'__OPS'],r[arm+'__OBP']+r[arm+'__SLG'])
            else:self.assertGreater(r['pull_air_only__SO'],r['weighted_actuals__SO'])
    def test_missing_features_all_arms_fallback(self):
        b=raw('pitcher')
        r,_,_=assemble([b],'pitcher',{},model('pitcher'),'abc')
        self.assertEqual(r[0]['status'],'MISSING_ELIGIBLE_FEATURES')
        for a in METHODS:self.assertEqual(r[0][a+'__SO'],100)
    def test_missing_component_remains_unknown(self):
        b=raw('hitter');b['2B']=None;b['H']=None;b['AVG']=None;b['SLG']=None;b['OPS']=None
        r,_,_=assemble([b],'hitter',board('hitter'),model('hitter'),'abc')
        self.assertEqual(r[0]['status'],'MISSING_BASELINE_COMPONENTS')
        self.assertIsNone(r[0]['pull_air_only__2B'])
    def test_population_not_expanded_duplicate_and_future_rejected(self):
        self.assertEqual(assemble([],'pitcher',board('pitcher'),model('pitcher'),'x')[0],[])
        for rows in ([raw('pitcher')]*2,[dict(raw('pitcher'),season='2028')]):
            with self.assertRaises(ValueError):assemble(rows,'pitcher',board('pitcher'),model('pitcher'),'x')
    def test_frozen_recipe_guard(self):
        f=dict(development_targets=[2024],reporting_fit_targets=[2024,2025],
            features=list(FEATURES),targets={r:list(t) for r,t in TARGETS.items()},
            arm_indices={a:list(c) if c is not None else None for a,c in ARMS.items()},
            frozen={r:model(r) for r in FIELDS})
        validate_models(f)
        f['reporting_fit_targets'].append(2026)
        with self.assertRaises(ValueError):validate_models(f)

if __name__=='__main__':unittest.main()

class PipelineTests(unittest.TestCase):
    def test_frozen_pipeline_bindings_backup_and_no_label_reads(self):
        import csv, json, tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        import duckdb
        from standalone_io_v1_0 import dump,sha,tree
        from project_2027_side_by_side_v1_39 import run
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);base=root/'base';lb=root/'lb';exp=root/'exp'
            for p in (base,lb,exp):p.mkdir()
            dump(base/'report.json',dict(version='1.31.0',valuation_enabled=False,
                actual_input_years=[2023,2024,2025,2026],model_selection_uses_2026=False,
                forecast_counts=dict(hitter=1,pitcher=1)))
            dump(base/'model_choice_freeze.json',dict(pitcher_default='accepted_ip'))
            for role in FIELDS:
                r=raw(role)
                with (base/f'homegrown_2027_{role}s.csv').open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(r));w.writeheader();w.writerow(r)
            dump(lb/'leaderboard_build_report.json',dict(version='1.21.0',training_uses_2026_data=False))
            for split,years in [('historical',(2023,2024,2025)),('quarantine_2026',(2026,))]:
                p=lb/split;p.mkdir();data=[]
                for year in years:
                    for role in FIELDS:
                        for m in FEATURES:
                            data.append(dict(source_season=year,player_type=role,mlbam_id='123',
                                family='batted_ball',metric=m,eligible=True,sample_eligible=True,
                                definition_supported=True,sample_basis='EXPORTED_BBE',
                                definition='EXPORTED_FRACTION_OF_ALL_BBE',unit='fraction',
                                denominator=100.,minimum_observations=30,value=.2,reason='SUPPORTED'))
                j=p/'x.json';j.write_text(json.dumps(data))
                with duckdb.connect() as db:db.read_json(str(j)).write_parquet(str(p/'leaderboard_features.parquet'))
                j.unlink()
            dump(exp/'report.json',dict(version='1.37.0',selection_uses_2026=False,promotion_performed=False))
            dump(exp/'frozen_models.json',dict(development_targets=[2024],reporting_fit_targets=[2024,2025],
                features=list(FEATURES),targets={r:list(v) for r,v in TARGETS.items()},
                arm_indices={a:list(c) if c is not None else None for a,c in ARMS.items()},
                frozen={r:model(r) for r in FIELDS}))
            watched={str(p):sha(p) for p in [base/'report.json',base/'model_choice_freeze.json',
                lb/'leaderboard_build_report.json',lb/'historical/leaderboard_features.parquet']}
            dump(exp/'input_hashes.json',watched)
            for p in (base,lb,exp):dump(p/'output_sha256.json',tree(p))
            before={str(p):tree(p) for p in (base,lb,exp)}
            args=SimpleNamespace(baseline=base,leaderboards=lb,experiment=exp,
                output=root/'out',backup_root=root/'backups')
            with patch('statcast_pull_air_v1_37.fit',side_effect=AssertionError('NO FIT')):
                r=run(args)
            self.assertFalse(r['models_refitted'])
            self.assertEqual(tree(root/'out'),tree(Path(r['backup'])))
            self.assertEqual(before,{str(p):tree(p) for p in (base,lb,exp)})
            with self.assertRaises(FileExistsError):run(args)
            # A changed manifest-valid historical source still fails the experiment binding.
            p=lb/'leaderboard_build_report.json';p.write_text(p.read_text()+' ')
            manifest=json.loads((lb/'output_sha256.json').read_text())
            manifest['leaderboard_build_report.json']=sha(p);dump(lb/'output_sha256.json',manifest)
            args.output=root/'bad'
            with self.assertRaises(ValueError):run(args)
            self.assertFalse(args.output.exists())
