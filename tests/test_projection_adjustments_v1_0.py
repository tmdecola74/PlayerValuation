import unittest,json,tempfile,copy,csv,sqlite3
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from argparse import Namespace
from backtest_projection_adjustments_v1_0 import solve,fit,candidate,select,build_models,forecast,evaluate_holdout,load_inputs,run

class AdjustmentTests(unittest.TestCase):
 def config(self):
  return dict(fit_season=2024,validation_season=2025,holdout_season=2026,ridge_strength=10,minimum_fit_players=10,minimum_validation_players=10,minimum_usable_player_features=1,minimum_mae_gain_pct=2,maximum_rmse_decline_pct=0,player_types={'hitter':dict(exposure='PA',headline_actual_exposure=100,features=['whiff_pct'],team_features=[],metrics={'HR':dict(kind='count',maximum_relative_change=.2)}),'pitcher':dict(exposure='IP',headline_actual_exposure=40,features=['velocity'],team_features=[],metrics={'SV':dict(kind='count',maximum_relative_change=.2,minimum_projected_value_for_adjustment=5)})})
 def data(self):
  rows=[];labels={}
  for year in [2024,2025,2026]:
   for i in range(30):
    rows.append(dict(player_type='hitter',season=year,source='Source',player_id=str(i),name='Player '+str(i),record_id=str(year)+'_'+str(i),metrics={'PA':500,'HR':20},excluded_metrics=[],features={'whiff_pct':(.1+i/100,.8)},team_features={}))
    if year<2026:labels[('hitter',year,str(i))]=dict(PA=500,HR=20+(i-15)/5)
  return rows,labels
 def test_known_linear_solver(self):
  self.assertEqual(solve([[2,0],[0,4]],[6,8]),[3,2])
 def test_validation_labels_cannot_change_fit_scaling_or_coefficients(self):
  rows,labels=self.data();cfg=self.config();m=fit(rows[:30],labels,'hitter','Source','HR',cfg)
  changed=copy.deepcopy(labels)
  for k,v in changed.items():
   if k[1]==2025:v['HR']=9999
  m2=fit(rows[:30],changed,'hitter','Source','HR',cfg)
  self.assertEqual(m,m2)
  self.assertEqual(m['fit_players'],30)
 def test_capped_changes_and_exclusions_missing_zero_fallback(self):
  rows,labels=self.data();cfg=self.config();m=fit(rows[:30],labels,'hitter','Source','HR',cfg)
  m['coefficients']=[1000]+[0]*(len(m['coefficients'])-1)
  pred,_=candidate(rows[0],m,'HR',cfg);self.assertEqual(pred,24)
  row=copy.deepcopy(rows[0]);row['features']={};self.assertEqual(candidate(row,m,'HR',cfg)[0],20)
  row['excluded_metrics']=['HR'];self.assertIsNone(candidate(row,m,'HR',cfg)[0])
  row['excluded_metrics']=[];row['metrics']['HR']=0;self.assertEqual(candidate(row,m,'HR',cfg)[0],0)
 def test_validation_gates_require_both_cohorts_and_rmse(self):
  cfg=self.config();m={'status':'FITTED'}
  good=dict(baseline={'n':30},mae_gain_pct=3,rmse_gain_pct=1)
  self.assertTrue(select(m,{'all_matched':good,'headline':good},cfg)[0])
  self.assertFalse(select(m,{'all_matched':good,'headline':dict(good,rmse_gain_pct=-.1)},cfg)[0])
  self.assertFalse(select(m,{'all_matched':dict(good,mae_gain_pct=1.9),'headline':good},cfg)[0])
 def test_missing_actuals_and_zero_saves_kept_in_identical_paired_pool(self):
  cfg=self.config();pred=[dict(player_type='pitcher',season=2026,source='Source',player_id='a',metric='SV',baseline=10,prediction=9),dict(player_type='pitcher',season=2026,source='Source',player_id='missing',metric='SV',baseline=10,prediction=9)]
  scored,pairs,omitted=evaluate_holdout(pred,{('pitcher',2026,'a'):{'IP':60,'SV':0}},cfg)
  self.assertEqual(scored[0]['n'],1);self.assertEqual(pairs[0]['actual'],0)
  self.assertEqual(omitted[0]['reason'],'NO_ACTUAL_RECORD')
 def test_rejected_model_forecasts_exact_baseline(self):
  rows,labels=self.data();cfg=self.config();models,*_=build_models(rows,labels,cfg)
  for m in models:m['selected']=False
  preds=forecast(rows,models,cfg)
  self.assertTrue(all(r['baseline']==r['prediction'] for r in preds))
 def test_loader_rejects_future_player_features_and_target_labels(self):
  cfg=self.config()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   (root/'model_input_audit.json').write_text(json.dumps(dict(target_season=2026,feature_event_end='2025-11-01',holdout_labels_loaded=False,trace={'status':'COMPLETE'})))
   (root/'model_features.csv').write_text('player_type,projection_season,player_id,metric,value,reliability,feature_season,sample_size,minimum_sample\nhitter,2026,p1,whiff_pct,.2,.5,2026,100,50\n')
   with self.assertRaisesRegex(ValueError,'feature leakage'):load_inputs(root,cfg)
   (root/'model_features.csv').write_text('player_type,projection_season,player_id,metric,value,reliability,feature_season,sample_size,minimum_sample\nhitter,2026,p1,whiff_pct,.2,.5,2025,100,50\n')
   (root/'model_team_context.csv').write_text('player_type,projection_season,source,player_id,context_season\n')
   (root/'projection_baselines.jsonl').write_text('')
   (root/'training_labels.jsonl').write_text(json.dumps(dict(player_type='hitter',season=2026,player_id='p1',metrics={'HR':1}))+'\n')
   with self.assertRaisesRegex(ValueError,'future labels'):load_inputs(root,cfg)
 def test_full_pipeline_freezes_before_holdout_and_target_outcomes_cannot_change_forecasts(self):
  cfg=self.config();rows,labels=self.data()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);inp=root/'inputs';inp.mkdir();conf=root/'config.json';conf.write_text(json.dumps(cfg));sql=root/'reference.sqlite'
   for name in ['projection_baselines.jsonl','model_features.csv','model_team_context.csv','training_labels.jsonl','model_input_audit.json']:(inp/name).write_text('placeholder')
   with closing(sqlite3.connect(sql)) as c:c.execute('create table placeholder(x INTEGER)');c.commit()
   args=Namespace(config=conf,inputs=inp,output=root/'out1',backup_root=root/'backups',evaluate_holdout=True,sqlite=sql)
   def holdout(path,year):
    stages=list(root.glob('out1.staging-*'))
    self.assertEqual(len(stages),1)
    self.assertTrue((stages[0]/'frozen_models.json').is_file());self.assertTrue((stages[0]/'forecasts_2026.jsonl').is_file())
    return {('hitter',2026,str(i)):{'PA':500,'HR':25} for i in range(30)}
   with patch('backtest_projection_adjustments_v1_0.load_inputs',return_value=(rows,labels,{'trace':{'status':'COMPLETE'}})),patch('backtest_projection_adjustments_v1_0.load_holdout',side_effect=holdout):r1=run(args)
   args.output=root/'out2'
   with patch('backtest_projection_adjustments_v1_0.load_inputs',return_value=(rows,labels,{'trace':{'status':'COMPLETE'}})),patch('backtest_projection_adjustments_v1_0.load_holdout',return_value={('hitter',2026,str(i)):{'PA':500,'HR':9999} for i in range(30)}):r2=run(args)
   self.assertEqual(r1['frozen_model_sha256'],r2['frozen_model_sha256']);self.assertEqual(r1['forecasts_sha256'],r2['forecasts_sha256'])
   self.assertNotEqual((root/'out1/holdout_scores.csv').read_bytes(),(root/'out2/holdout_scores.csv').read_bytes())
   self.assertEqual((Path(r1['backup'])/'forecasts_2026.jsonl').read_bytes(),(root/'out1/forecasts_2026.jsonl').read_bytes())

if __name__=='__main__':unittest.main()
