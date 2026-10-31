import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from actuals_scoring_v1_0 import *
from repair_actuals_reports_v1_0_1 import partition_report_rows,repair
from reconcile_statcast_actuals_v1_0 import build
import test_actuals_scoring_v1_0 as fixture_helpers
feed=fixture_helpers.feed
pitch=fixture_helpers.pitch


def example():
 rows=[pitch(1),pitch(2,strikes=1),pitch(3,batter=11,strikes=2),pitch(4,balls=1,strikes=2,event='strikeout')]
 trace={'game_pk':1,'at_bat_number':1,'event':'strikeout','sequence':rows,**credit_pa(rows)}
 play={'atBatIndex':0,'about':{'isComplete':True},'result':{'eventType':'strikeout'},'matchup':{'batter':{'id':11},'pitcher':{'id':20}},'playEvents':[{'isPitch':True,'pitchNumber':1,'count':{'balls':0,'strikes':1}},{'isPitch':True,'pitchNumber':2,'count':{'balls':0,'strikes':2}},{'details':{'eventType':'offensive_substitution'},'player':{'id':11},'replacedPlayer':{'id':10},'count':{'balls':0,'strikes':2}},{'isPitch':True,'pitchNumber':3,'count':{'balls':1,'strikes':2}},{'isPitch':True,'pitchNumber':4,'count':{'balls':1,'strikes':3}}]}
 return trace,play


class FixTests(unittest.TestCase):
 def test_partial_rows_are_preserved_outside_season_domain(self):
  rows=[{'fangraphs_actual':'','terminal_count':'0','status':'NO_FANGRAPHS_REFERENCE'},{'fangraphs_actual':'','terminal_count':'','partial_boxscore_count':'0'},{'fangraphs_actual':'','terminal_count':'','partial_boxscore_count':'4'}]
  primary,other=partition_report_rows(rows);self.assertEqual(len(primary),1);self.assertEqual([r['partial_boxscore_count'] for r in other],['0','4'])
  self.assertEqual(season_comparison_domain({1},{2}),{1,2})
 def test_credit_label_confirmation_no_count_or_pitch_changes(self):
  trace,play=example();original=copy.deepcopy(trace['sequence']);proof=confirm_terminal_scored_label(trace,play)
  self.assertEqual(proof['credited_batter'],10);self.assertEqual(proof['physical_finishing_batter'],11);self.assertFalse(proof['count_changes']);self.assertEqual(trace['sequence'],original)
  payload={'gamePk':1,'liveData':{'plays':{'allPlays':[play]}}};self.assertTrue(confirm_trace_from_feed(trace,payload));self.assertEqual(trace['unresolved_roles'],[])
 def test_index_alone_wrong_ids_counts_or_pitch_sequence_cannot_confirm(self):
  t,p=example()
  for field in ['batter','pitcher']:
   wrong=copy.deepcopy(p);wrong['matchup'][field]['id']=999;self.assertIsNone(confirm_terminal_scored_label(t,wrong))
  wrong=copy.deepcopy(p);wrong['playEvents'][2]['count']['strikes']=1;self.assertIsNone(confirm_terminal_scored_label(t,wrong))
  wrong=copy.deepcopy(p);wrong['playEvents'][-1]['pitchNumber']=9;self.assertIsNone(confirm_terminal_scored_label(t,wrong))
  self.assertFalse(confirm_trace_from_feed(t,{'gamePk':2,'liveData':{'plays':{'allPlays':[p]}}}))
 def test_fast_repair_preserves_primary_values_and_backs_up_evidence(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg,statcast=fixture_helpers.PipelineTests().fixture(root);cache=root/'cache';(cache/'1').mkdir(parents=True)
   raw=cache/'1'/'feed.json';raw.write_text(json.dumps(feed()));dump(cache/'1'/'source.json',{'game_pk':1,'sha256':sha(raw)})
   build(root/'reference',cfg,root/'original',start='2015-04-05',end='2015-04-05',backup_root=root/'backups',feed_cache=cache)
   p=root/'original'/'player_metric_reconciliation.csv'
   with p.open() as f:r=csv.DictReader(f);headers=r.fieldnames;rows=list(r)
   before=copy.deepcopy(rows)
   for role,mid,metric,value in [('hitter',999,'PA','0'),('pitcher',888,'ER','4')]:
    extra={k:'' for k in headers};extra.update(season='2015',player_type=role,mlbam_id=str(mid),metric=metric,partial_boxscore_count=value,status='NO_FANGRAPHS_REFERENCE',sequence_review='False');rows.append(extra)
   csv_out(p,rows,headers);source_sha=sha(p)
   result=repair(root/'original',cache,root/'fixed',root/'backups')
   self.assertEqual(result['mlb_evidence_only_rows'],2);self.assertEqual(sha(p),source_sha)
   with (root/'fixed'/'player_metric_reconciliation.csv').open() as f:after=list(csv.DictReader(f))
   self.assertEqual(after,before)
   self.assertTrue((Path(result['backup'])/'mlb_evidence_only.csv').is_file())
   with (root/'fixed'/'mlb_evidence_only.csv').open() as f:other=list(csv.DictReader(f))
   self.assertEqual([r['partial_boxscore_count'] for r in other],['0','4'])
if __name__=='__main__':unittest.main()
