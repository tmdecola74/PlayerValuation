import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from collections import defaultdict
from contextlib import closing
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backtest_projection_blends_v1_0 import fit_weights,inverse_mae_weights,expand_weights,eligible_players,backtest


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


class BlendTests(unittest.TestCase):
    def fixture(self,temp):
        root=Path(temp);(root/'config').mkdir()
        path=root/'warehouse.sqlite'
        with closing(sqlite3.connect(path)) as db:
            for typ in ('hitter','pitcher'):
                db.execute(f'CREATE TABLE {typ}_actuals(record_id TEXT PRIMARY KEY,player_id TEXT,season INTEGER,identity_conflict INTEGER,metrics_json TEXT)')
                db.execute(f'CREATE TABLE analytical_{typ}_projections(record_id TEXT PRIMARY KEY,player_id TEXT,season INTEGER,source TEXT,name TEXT,actual_record_id TEXT,match_status TEXT,metrics_json TEXT)')
            for year in (2024,2025):
                for pid in range(1,5):
                    actual_id=f'a{year}_{pid}';actual=dict(HR=pid*10,PA=500)
                    db.execute('INSERT INTO hitter_actuals VALUES (?,?,?,?,?)',(actual_id,str(pid),year,0,json.dumps(actual)))
                    sources=['A','B']+(['C'] if year==2025 else [])
                    for source in sources:
                        predicted=dict(HR=pid*10+(0 if source=='A' else 10 if source=='B' else 5),PA=500)
                        db.execute('INSERT INTO analytical_hitter_projections VALUES (?,?,?,?,?,?,?,?)',(f'p{year}_{source}_{pid}',str(pid),year,source,str(pid),actual_id,'matched',json.dumps(predicted)))
            db.commit()
        cfg=dict(warehouse='warehouse.sqlite',output='results',folds=[dict(name='primary',train_seasons=[2024],test_season=2025,primary=True)],
            inverse_mae_shrinkage=.5,ridge_strength=.1,minimum_training_pairs=2,minimum_training_pairs_per_season=2,
            minimum_test_pairs=2,correlation_min_n=2,minimum_mae_gain_pct=1,maximum_rmse_decline_pct=1,
            player_types={'hitter':dict(exposure='PA',metrics=['HR'],headline_cohort='all',cohorts=[dict(name='all',minimum_actual=0,minimum_projected=0)])})
        config=root/'config/blend.json';config.write_text(json.dumps(cfg));return config,path

    def test_simplex_optimizer_and_inverse_weights_known_cases(self):
        x=[[1,3],[2,4],[3,5]];y=[1,2,3]
        weights,status=fit_weights(x,y,ridge_strength=0)
        self.assertTrue(status['converged']);self.assertAlmostEqual(weights[0],1);self.assertAlmostEqual(weights[1],0)
        reversed_weights,_=fit_weights([row[::-1] for row in x],y,ridge_strength=0)
        self.assertAlmostEqual(reversed_weights[1],1)
        weights,_=fit_weights([[1,1],[2,2]], [1,2]);self.assertEqual(weights,[.5,.5])
        weights,_=inverse_mae_weights(x,y,[1/3]*3,.5);self.assertEqual(weights,[.75,.25])
        expanded=expand_weights({'A':.75,'B':.25},['A','B','C'])
        for source,value in {'A':.5,'B':1/6,'C':1/3}.items():self.assertAlmostEqual(expanded[source],value)

    def test_test_actuals_cannot_change_training_weights_and_database_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,path=self.fixture(temp)
            before=hashlib.sha256(path.read_bytes()).hexdigest();backtest(cfg)
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
            initial=read_csv(Path(temp)/'results/fold_weights.csv')
            self.assertTrue(all(abs(sum(float(r['weight']) for r in initial if r['sample_id']==sample and r['method']==method)-1)<1e-12 for sample,method in {(r['sample_id'],r['method']) for r in initial}))
            new=[r for r in initial if r['source']=='C' and r['method']!='equal']
            self.assertTrue(all(abs(float(r['weight'])-1/3)<1e-12 for r in new))
            with closing(sqlite3.connect(path)) as db:
                for rec,raw in db.execute('SELECT record_id,metrics_json FROM hitter_actuals WHERE season=2025').fetchall():
                    values=json.loads(raw);values['HR']=1000
                    db.execute('UPDATE hitter_actuals SET metrics_json=? WHERE record_id=?',(json.dumps(values),rec))
                db.commit()
            backtest(cfg,Path(temp)/'perturbed')
            later=read_csv(Path(temp)/'perturbed/fold_weights.csv')
            key=lambda r:(r['sample_id'],r['method'],r['source'],r['weight'])
            self.assertEqual(sorted(map(key,initial)),sorted(map(key,later)))
            first=read_csv(Path(temp)/'results/fold_accuracy.csv');second=read_csv(Path(temp)/'perturbed/fold_accuracy.csv')
            self.assertNotEqual(first[0]['mae'],second[0]['mae'])
            with self.assertRaises(ValueError):backtest(cfg)

    def test_future_training_and_duplicate_primary_test_year_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,path=self.fixture(temp);values=json.loads(cfg.read_text())
            values['folds'][0]['train_seasons']=[2025];cfg.write_text(json.dumps(values))
            with self.assertRaises(ValueError):backtest(cfg)
            values['folds'][0]['train_seasons']=[2024]
            values['folds'].append(dict(values['folds'][0],name='duplicate'));cfg.write_text(json.dumps(values))
            with self.assertRaises(ValueError):backtest(cfg)

    def test_closer_cohort_uses_projections_including_actual_zero_saves(self):
        index=defaultdict(dict)
        for source in ['A','B']:
            for pid,projected,actual in [('1',5,0),('2',0,25)]:
                index[('pitcher',2024,source)][pid]=dict(matched=True,projected={'SV':projected,'IP':20},actual={'SV':actual,'IP':20},actual_record_id='a'+pid,name=pid,record_id=source+pid)
        selected=eligible_players(index,'pitcher',2024,['A','B'],'SV',dict(minimum_actual=0,projected_any_sv_minimum=5),'IP')
        self.assertEqual([r['player_id'] for r in selected],['1']);self.assertEqual(selected[0]['actual'],0)


if __name__=='__main__':unittest.main()
