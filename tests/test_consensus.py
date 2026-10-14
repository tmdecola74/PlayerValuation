import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_consensus_projections_v1_0 import aggregate,derive,build


class ConsensusTests(unittest.TestCase):
    def fixture(self,temp):
        root=Path(temp);(root/'config').mkdir();db_path=root/'warehouse.sqlite'
        with closing(sqlite3.connect(db_path)) as db:
            db.executescript('CREATE TABLE projection_runs(season INTEGER,source TEXT);CREATE TABLE players(player_id TEXT,preferred_name TEXT);CREATE TABLE player_id_crosswalk(player_id TEXT,namespace TEXT,external_id TEXT);')
            db.executemany('INSERT INTO projection_runs VALUES (2026,?)',[('A',),('B',)])
            db.executemany('INSERT INTO players VALUES (?,?)',[('1','Hitter'),('2','Prospect'),('3','Pitcher')])
            db.executemany('INSERT INTO player_id_crosswalk VALUES (?,?,?)',[('1','fangraphs','100'),('1','mlbam','200')])
            for typ in ['hitter','pitcher']:
                db.execute(f'CREATE TABLE analytical_{typ}_projections(season INTEGER,source TEXT,player_id TEXT,name TEXT,team TEXT,record_id TEXT,metrics_json TEXT,identity_method TEXT,match_status TEXT)')
            entries=[('hitter','A','1',dict(G=30,PA=120,H=30,AB=100,HR=5,**{'1B':20,'2B':5,'3B':0},BB=10,HBP=1,SF=2,AVG=.3), 'matched'),
                     ('hitter','B','1',dict(G=20,PA=65,H=10,AB=50,HR=1,**{'1B':8,'2B':1,'3B':0},BB=5,HBP=0,SF=1,AVG=.2),'unmatched'),
                     ('hitter','B','2',dict(PA=1,AB=0,H=0),'unmatched'),
                     ('pitcher','A','3',dict(IP=100,ER=30,H=80,BB=20,SO=100,SV=0,HLD=4,QS=5),'matched'),
                     ('pitcher','B','3',dict(IP=50,ER=20,H=40,BB=15,SO=45,SV=2,QS=3),'unmatched')]
            for typ,source,pid,stats,status in entries:
                db.execute(f'INSERT INTO analytical_{typ}_projections VALUES (?,?,?,?,?,?,?,?,?)',(2026,source,pid,'Name '+pid,'ATL',source+pid,json.dumps(stats),'identifier',status))
            db.commit()
        shipped=Path(__file__).resolve().parents[1]/'config/consensus_projections.json'
        cfg=json.loads(shipped.read_text());cfg.update(warehouse='warehouse.sqlite',output='results',source_weights={'A':1,'B':1})
        cfg['rate_difference_thresholds']['AVG']=.01
        path=root/'config/consensus.json';path.write_text(json.dumps(cfg));return path,db_path

    def test_available_weights_include_zero_and_exclude_missing(self):
        value,info=aggregate({'A':0,'B':None,'C':10},{'A':1,'B':1,'C':3})
        self.assertEqual(value,7.5);self.assertEqual(info['normalized_weights'],{'A':.25,'C':.75})
        self.assertIsNone(aggregate({'A':None},{'A':1})[0])
        self.assertEqual(aggregate({'A':10,'B':20},{'A':1,'B':0})[0],10)

    def test_coherent_components_identity_unmatched_and_read_only_input(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,path=self.fixture(temp);before=hashlib.sha256(path.read_bytes()).hexdigest()
            report=build(cfg)
            self.assertEqual(report['source_projection_rows'],5)
            self.assertEqual(report['unmatched_source_rows'],3)
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
            hitters=json.loads((Path(temp)/'results/hitter_consensus.json').read_text())
            h=next(r for r in hitters if r['player_id']=='1');m=h['metrics']
            self.assertAlmostEqual(m['AVG'],20/75)
            self.assertNotAlmostEqual(m['AVG'],.25)
            self.assertAlmostEqual(m['OPS'],m['OBP']+m['SLG'])
            self.assertEqual(h['fangraphs_ids'],['100']);self.assertEqual(h['mlbam_ids'],['200'])
            prospect=next(r for r in hitters if r['player_id']=='2')
            self.assertIsNone(prospect['metrics']['AVG']);self.assertIsNone(prospect['metrics']['HR'])
            pitcher=json.loads((Path(temp)/'results/pitcher_consensus.json').read_text())[0]['metrics']
            self.assertAlmostEqual(pitcher['ERA'],9*25/75)
            self.assertAlmostEqual(pitcher['WHIP'],77.5/75)
            self.assertEqual(pitcher['SV'],1);self.assertEqual(pitcher['SV_plus_HLD'],5)
            self.assertGreater(report['mixed_component_rate_values'],0)
            self.assertGreater(report['large_derived_rate_differences'],0)
            with self.assertRaises(ValueError):build(cfg)

    def test_metric_overrides_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,path=self.fixture(temp);values=json.loads(cfg.read_text())
            values['player_types']['hitter']['metric_weight_overrides']={'HR':{'A':3,'B':1}};cfg.write_text(json.dumps(values))
            build(cfg)
            h=json.loads((Path(temp)/'results/hitter_consensus.json').read_text())[0]
            self.assertEqual(h['metrics']['HR'],4)
            values['player_types']['hitter']['metric_weight_overrides']={'AVG':{'A':3}}
            cfg.write_text(json.dumps(values))
            with self.assertRaises(ValueError):build(cfg,Path(temp)/'bad')
            self.assertFalse((Path(temp)/'bad').exists())

    def test_missing_components_and_zero_denominators_are_not_zero_rates(self):
        formula={'numerator':{'ER':1},'denominator':{'IP':1},'scale':9}
        self.assertEqual(derive(formula,{'ER':0,'IP':0}),(None,[],'nonpositive_denominator'))
        self.assertEqual(derive(formula,{'IP':10}),(None,['ER'],'missing_components'))
        self.assertEqual(derive(formula,{'ER':0,'IP':10}),(0,[],'derived'))


if __name__=='__main__':unittest.main()
