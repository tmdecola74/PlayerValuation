import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from build_lagged_features_v1_0 import build
from lagged_io_v1_0 import sha,tree
ROOT=Path(__file__).resolve().parents[1]
def dump(p,v):p.write_text(json.dumps(v),encoding='utf-8')
def parquet(p,rows,types):
 f=p.with_suffix('.csv')
 with f.open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=list(types));w.writeheader();w.writerows(rows)
 with duckdb.connect() as db:db.read_csv(str(f),header=True,columns=types).write_parquet(str(p))
 f.unlink()
def fixture(p,holdout=30,target_age=99):
 (p/'ref').mkdir();(p/'labels/register_snapshot').mkdir(parents=True);(p/'raw').mkdir()
 c=json.loads((ROOT/'config/lagged_features_v1_0.json').read_text());c.update(source_seasons=[2024,2025],training_target_seasons=[2025],window_start_mmdd='03-01',window_end_mmdd='03-01',first_rolling_evaluation_year=2025);c['minimum_observations']={m:1 for m in c['minimum_observations']};dump(p/'config.json',c)
 players=[dict(season=y,player_type=r,mlbam_id=pid,age=28+y-2024 if y<2026 else target_age) for y in [2024,2025,2026] for r,pid in [('hitter','1'),('pitcher','2')]]
 parquet(p/'ref/player_seasons.parquet',players,dict(season='INTEGER',player_type='VARCHAR',mlbam_id='BIGINT',age='INTEGER'));parquet(p/'ref/actual_counts.parquet',[{'value':1}],{'value':'INTEGER'})
 hashes={n:sha(p/'ref'/n) for n in ['actual_counts.parquet','player_seasons.parquet']};metrics={'hitter':['G','PA','H','HR'],'pitcher':['G','OUTS','SO','SV']};rows=[]
 for y in [2024,2025,2026]:
  for role,pid in [('hitter','1'),('pitcher','2')]:
   for m in metrics[role]:rows.append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,label_value=holdout if y==2026 else y-2020,eligible=True,purpose='holdout_evaluation' if y==2026 else 'training',label_source='FROZEN_FANGRAPHS_ACTUALS'))
 types=dict(season='INTEGER',player_type='VARCHAR',mlbam_id='VARCHAR',metric='VARCHAR',label_value='DOUBLE',eligible='BOOLEAN',purpose='VARCHAR',label_source='VARCHAR')
 for split,ys in [('training',[2024,2025]),('holdout',[2026])]:parquet(p/f'labels/{split}_labels.parquet',[r for r in rows if r['season'] in ys],types)
 dump(p/'labels/training_labels_config.json',{'metrics':metrics});dump(p/'labels/register_snapshot/modeling_label_policy.json',{'expected_reference_hashes':hashes});dump(p/'labels/label_build_report.json',dict(holdout_season=2026,training_seasons=[2024,2025],primary_source='FROZEN_FANGRAPHS_ACTUALS',rows={'training_eligible':16,'holdout_eligible':8},reference_sha256=hashes));dump(p/'labels/output_sha256.json',tree(p/'labels'))
 manifest=[]
 for y in [2024,2025]:
  rows=[dict(game_pk=y,at_bat_number=1,pitch_number=n,game_date=f'{y}-03-01',game_type='R',batter=1,pitcher=2,description=d,type='X' if n>2 else 'S',zone=12 if n==1 else 5,launch_speed=100 if n==3 else None,launch_speed_angle=6 if n==3 else None,estimated_woba_using_speedangle=.4 if n==3 else None,release_speed=95,release_extension=6) for n,d in enumerate(['swinging_strike','foul','hit_into_play','hit_into_play'],1)]
  types=dict(game_pk='BIGINT',at_bat_number='INTEGER',pitch_number='INTEGER',game_date='VARCHAR',game_type='VARCHAR',batter='BIGINT',pitcher='BIGINT',description='VARCHAR',type='VARCHAR',zone='INTEGER',launch_speed='DOUBLE',launch_speed_angle='DOUBLE',estimated_woba_using_speedangle='DOUBLE',release_speed='DOUBLE',release_extension='DOUBLE')
  f=p/f'raw/{y}.parquet';parquet(f,rows,types);raw=p/f'raw/{y}.txt';raw.write_text('frozen',encoding='utf-8');schedule=p/f'raw/{y}.json';dump(schedule,{})
  manifest.append(dict(day=f'{y}-03-01',status='COMPLETE',rows=4,raw_path=str(raw),raw_hash=sha(raw),parquet_path=str(f),parquet_hash=sha(f),schedule_path=str(schedule),schedule_hash=sha(schedule)))
 dump(p/'windows.json',manifest);return manifest
class LagTests(unittest.TestCase):
 def run_build(self,p):return build(p/'labels',p/'ref',p/'windows.json',p/'config.json',p/'out',p/'backups')
 def rows(self,p):
  with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
 def test_lags_and_labels_and_backup(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);before=tree(p/'ref');r=self.run_build(p);self.assertEqual(tree(p/'out'),tree(Path(r['backup'])));self.assertEqual(tree(p/'ref'),before)
   rows=self.rows(p/'out/training_matrix.csv');h=next(x for x in rows if x['player_type']=='hitter');self.assertEqual(float(h['x_actual_lag1_H']),4);self.assertEqual(float(h['y_H']),5);self.assertEqual(h['x_actual_lag2_H'],'');self.assertEqual(float(h['age_at_target_estimate']),29)
   q=next(x for x in rows if x['player_type']=='pitcher');self.assertEqual(q['x_statcast_lag1_spin_rpm_value'],'');self.assertEqual(q['x_statcast_lag1_spin_rpm_observations'],'0');self.assertEqual(r['pitch_rows'],8)
 def test_holdout_outcome_and_target_age_invariance(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=p/'a';b=p/'b';a.mkdir();b.mkdir();fixture(a,30,99);fixture(b,88,10);self.run_build(a);self.run_build(b)
   for name in ['training_features.csv','holdout_features.csv','training_matrix.csv']:self.assertEqual((a/'out'/name).read_bytes(),(b/'out'/name).read_bytes())
   self.assertNotEqual((a/'out/holdout_matrix.csv').read_bytes(),(b/'out/holdout_matrix.csv').read_bytes())
 def test_future_windows_never_opened(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);m=fixture(p);m.append(dict(day='2026-03-01',status='COMPLETE',rows=999,parquet_path='not-present'));dump(p/'windows.json',m);self.assertEqual(self.run_build(p)['selected_windows'],2)
 def test_missing_window_and_hash_tamper(self):
  for mode in ['missing','tamper']:
   with tempfile.TemporaryDirectory() as t:
    p=Path(t);m=fixture(p)
    if mode=='missing':dump(p/'windows.json',m[:-1])
    else:(p/'raw/2024.txt').write_text('changed')
    with self.assertRaises(ValueError):self.run_build(p)
    self.assertFalse((p/'out').exists())
 def test_label_manifest_tamper(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);(p/'labels/training_labels.parquet').write_bytes(b'changed')
   with self.assertRaises(ValueError):self.run_build(p)
 def test_sample_gate_and_no_zero_imputation(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);c=json.loads((p/'config.json').read_text());c['minimum_observations']['ev']=100;dump(p/'config.json',c);self.run_build(p);h=next(x for x in self.rows(p/'out/training_features.csv') if x['player_type']=='hitter');self.assertEqual(h['x_statcast_lag1_ev_value'],'');self.assertEqual(h['x_statcast_lag1_ev_observations'],'1');self.assertEqual(h['x_statcast_lag1_ev_eligible'],'0')
 def test_windows_encoding_and_output_guard(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);orig=Path.read_text
   def windows(path,encoding=None,errors=None,**kw):return orig(path,encoding=encoding or 'cp1252',errors=errors,**kw)
   with patch.object(Path,'read_text',windows):self.run_build(p)
   with self.assertRaises(FileExistsError):self.run_build(p)
 def test_masked_prior_actual_label_not_backfilled(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p)
   with duckdb.connect() as db:
    rows=db.read_parquet(str(p/'labels/training_labels.parquet')).fetchall()
    columns=db.read_parquet(str(p/'labels/training_labels.parquet')).columns
   rows=[dict(zip(columns,r)) for r in rows if not(r[columns.index('season')]==2024 and r[columns.index('player_type')]=='hitter' and r[columns.index('metric')]=='H')]
   types=dict(season='INTEGER',player_type='VARCHAR',mlbam_id='VARCHAR',metric='VARCHAR',label_value='DOUBLE',eligible='BOOLEAN',purpose='VARCHAR',label_source='VARCHAR')
   (p/'labels/training_labels.parquet').unlink();parquet(p/'labels/training_labels.parquet',rows,types)
   report=json.loads((p/'labels/label_build_report.json').read_text());report['rows']['training_eligible']-=1;dump(p/'labels/label_build_report.json',report)
   (p/'labels/output_sha256.json').unlink();dump(p/'labels/output_sha256.json',tree(p/'labels'));self.run_build(p)
   r=next(x for x in self.rows(p/'out/training_features.csv') if x['player_type']=='hitter');self.assertEqual(r['x_actual_lag1_H'],'')
 def test_holdout_cold_start_does_not_select_feature_population(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p)
   with duckdb.connect() as db:
    rel=db.read_parquet(str(p/'labels/holdout_labels.parquet'));cols=rel.columns;rows=[dict(zip(cols,r)) for r in rel.fetchall()]
   rows.append(dict(season=2026,player_type='hitter',mlbam_id='999',metric='HR',label_value=9,eligible=True,purpose='holdout_evaluation',label_source='FROZEN_FANGRAPHS_ACTUALS'))
   types=dict(season='INTEGER',player_type='VARCHAR',mlbam_id='VARCHAR',metric='VARCHAR',label_value='DOUBLE',eligible='BOOLEAN',purpose='VARCHAR',label_source='VARCHAR')
   (p/'labels/holdout_labels.parquet').unlink();parquet(p/'labels/holdout_labels.parquet',rows,types)
   report=json.loads((p/'labels/label_build_report.json').read_text());report['rows']['holdout_eligible']+=1;dump(p/'labels/label_build_report.json',report)
   (p/'labels/output_sha256.json').unlink();dump(p/'labels/output_sha256.json',tree(p/'labels'));self.run_build(p)
   self.assertFalse(any(r['mlbam_id']=='999' for r in self.rows(p/'out/holdout_features.csv')));self.assertTrue(any(r['mlbam_id']=='999' for r in self.rows(p/'out/cold_start_targets.csv')))
 def test_duplicate_physical_pitch_rejected_even_with_updated_file_hash(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);m=fixture(p);raw=p/'raw/2024.parquet';new=p/'raw/duplicate.parquet'
   with duckdb.connect() as db:
    rel=db.read_parquet(str(raw));rel.union(rel.limit(1)).write_parquet(str(new))
   raw.unlink();new.rename(raw);m[0]['rows']=5;m[0]['parquet_hash']=sha(raw);dump(p/'windows.json',m)
   with self.assertRaises(ValueError):self.run_build(p)
   self.assertFalse((p/'out').exists())
if __name__=='__main__':unittest.main()
