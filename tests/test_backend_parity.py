import unittest,tempfile,json,csv,shutil
from pathlib import Path
from build_historical_projection_warehouse_v1_0 import build
from migrate_sqlite_warehouse_to_duckdb_v1_0 import migrate
from compare_warehouse_backends_v1_0 import run,compare_outputs
class Parity(unittest.TestCase):
 def test_four_stages(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);config=root/'config';config.mkdir()
   shipped=Path(__file__).resolve().parents[1]/'config'
   cfg=json.loads((shipped/'warehouse.json').read_text())
   for name in ['metric_registry.json','identity_overrides.json']:
    shutil.copy2(shipped/name,config/name)
   for name in ['reviewed_aliases.json','duplicate_resolutions.json']:(config/name).write_text('[]')
   cfg['input_roots']={'actuals':str(root),'projections':str(root)};cfg['files']=[]
   headers=['Season','Name','PlayerId','PA','HR']
   actual=[headers]+[[year,'P'+str(i),i,500,10+i] for year in [2024,2025,2026] for i in [1,2,3]]
   with (root/'actual.csv').open('w',newline='') as f:csv.writer(f).writerows(actual)
   cfg['files'].append(dict(file='actual.csv',root='actuals',kind='actual',source='Actual',player_type='hitter',profile='fangraphs',ip_notation='decimal'))
   for year in [2024,2025,2026]:
    for source,delta in [('A',1),('B',-1)]:
     name=f'{source}{year}.csv'
     with (root/name).open('w',newline='') as f:csv.writer(f).writerows([headers]+[[year,'P'+str(i),i,500,10+i+delta] for i in [1,2,3]])
     cfg['files'].append(dict(file=name,root='projections',kind='projection',source=source,season=year,player_type='hitter',profile='fangraphs',ip_notation='decimal'))
   (config/'warehouse.json').write_text(json.dumps(cfg));build(config/'warehouse.json')
   cohort=dict(name='all',minimum_actual=0,minimum_projected=0)
   accuracy={'warehouse':'unused','output':'unused','correlation_min_n':2,'ranking_min_n':2,'player_types':{'hitter':{'exposure':'PA','headline_cohort':'all','cohorts':[cohort],'metric_groups':{'fantasy_outcome':['HR'],'opportunity':['PA'],'skill':[]}}}}
   consensus={'season':2026,'warehouse':'unused','output':'unused','source_weights':{'A':1,'B':1},'minimum_sources_for_agreement':2,'high_disagreement_cv':.25,'rate_difference_thresholds':{},'player_types':{'hitter':{'exposure':'PA','rate_interpretation_exposure_floor':100,'base_metrics':['PA','HR'],'nonnegative_metrics':['PA','HR'],'metric_weight_overrides':{},'derived_metrics':{}}}}
   bt={'warehouse':'unused','output':'unused','consensus_config':'config/consensus_projections.json','seasons':[2024,2025,2026],'correlation_min_n':2,'player_types':{'hitter':{'exposure':'PA','projected_exposure_floor':100,'headline_cohort':'all','metrics':['HR','PA'],'cohorts':[cohort]}}}
   blend=json.loads(Path(__file__).resolve().parent.joinpath('backend_parity_blend_fixture.json').read_text())
   for name,value in [('accuracy_evaluation.json',accuracy),('consensus_projections.json',consensus),('consensus_backtesting.json',bt),('blend_backtesting.json',blend)]:
    (config/name).write_text(json.dumps(value))
   sqlite=root/'data/warehouse/historical_projection_warehouse.sqlite';out=root/'migrated';migrate(sqlite,out)
   result=run(root,sqlite,out/'player_valuation.duckdb',root/'comparison')
   failures=[r for r in result['checks'] if not r['pass']]
   self.assertTrue(result['pass'],json.dumps(failures,indent=2))
   self.assertTrue(Path(result['backup']).is_dir())
 def test_comparison_detects_membership_weight_and_duplicate_changes(self):
  with tempfile.TemporaryDirectory() as t:
   a=Path(t)/'a';b=Path(t)/'b';a.mkdir();b.mkdir()
   (a/'weights.csv').write_text('player_id,weight\n1,0.5\n2,0.5\n')
   (b/'weights.csv').write_text('player_id,weight\n2,0.5\n1,0.5\n')
   self.assertTrue(all(r['pass'] for r in compare_outputs(a,b)))
   (b/'weights.csv').write_text('player_id,weight\n1,0.4\n3,0.6\n')
   self.assertFalse(all(r['pass'] for r in compare_outputs(a,b)))
   (b/'weights.csv').write_text('player_id,weight\n1,0.5\n2,0.5\n2,0.5\n')
   self.assertFalse(all(r['pass'] for r in compare_outputs(a,b)))
if __name__=='__main__':unittest.main()
