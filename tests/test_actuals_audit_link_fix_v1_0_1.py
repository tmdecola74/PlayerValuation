import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import audit_actuals_final_differences_v1_0 as auditmod
from repair_actuals_audit_links_v1_0_1 import repair
from actuals_final_audit_support_v1_0 import BOX_FIELDS,sha

class LinkFixTests(unittest.TestCase):
    def test_bot_bottom_and_top_bottom(self):
        for a,b in [('Bot','bottom'),('bottom','Bot'),('Top','top')]:
            self.assertEqual(auditmod.normalize_half(a),auditmod.normalize_half(b))
        self.assertNotEqual(auditmod.normalize_half('Top'),auditmod.normalize_half('bottom'))

    def make_audit(self,root):
        folder=root/'baseline';folder.mkdir();cache=root/'cache';(cache/'1').mkdir(parents=True)
        raw=root/'raw.csv'
        row=dict(game_pk=1,at_bat_number=1,pitch_number=1,batter=10,pitcher=20,balls=0,strikes=0,
                 events='single',game_date='2016-04-01',game_type='R',inning=1,inning_topbot='Bot')
        auditmod.write_csv(raw,[row],list(row))
        auditmod.json_out(folder/'source_windows.json',[dict(day='2016-04-01',status='COMPLETE',raw_path=str(raw),raw_hash=sha(raw),rows=1,source_rows=1)])
        auditmod.json_out(folder/'reconciliation_report.json',dict(seasons=[2016]))
        case=dict(season=2016,player_type='hitter',mlbam_id=10,name='Test',metric='H',fangraphs_actual=1,
                  terminal_count=1,rule_count=1,evidence_count=0,final_difference=-1,status='UNRESOLVED_DIFFERENCE')
        auditmod.write_csv(folder/'discrepancies.csv',[case],list(case))
        teams={}
        for side,pid in [('home',10),('away',20)]:
            b={v:0 for v in BOX_FIELDS['hitter'].values()};b.update(plateAppearances=1,atBats=1)
            p={v:0 for v in BOX_FIELDS['pitcher'].values()};p.update(battersFaced=1,inningsPitched='0.0')
            teams[side]=dict(teamStats=dict(batting=b,pitching=p),players={str(pid):dict(person=dict(id=pid),stats=dict(batting=b,pitching=p))})
        play=dict(about=dict(atBatIndex=0,isComplete=True,inning=1,halfInning='bottom'),
                  matchup=dict(batter=dict(id=10),pitcher=dict(id=20)),result=dict(eventType='field_error'),
                  playEvents=[dict(isPitch=True,pitchNumber=1,count=dict(balls=0,strikes=0))])
        payload=dict(gamePk=1,gameData=dict(game=dict(type='R',season='2016'),status=dict(abstractGameState='Final',detailedState='Final')),
                     liveData=dict(boxscore=dict(teams=teams),plays=dict(allPlays=[play])))
        auditmod.json_out(cache/'1/feed.json',payload)
        auditmod.json_out(cache/'1/source.json',dict(game_pk=1,season=2016,sha256=sha(cache/'1/feed.json')))
        out=root/'audit_old'
        with patch.object(auditmod,'normalize_half',lambda s:str(s).lower()):
            auditmod.audit(folder,cache,out,root/'backups')
        report=json.loads((out/'audit_report.json').read_text());report['version']='1.0.0';auditmod.json_out(out/'audit_report.json',report)
        return out,raw,cache

    def test_fast_repair_no_raw_rescan_and_verified_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);old,raw,cache=self.make_audit(root)
            before={p.name:sha(p) for p in old.iterdir()}
            raw.unlink()  # proves fast repair does not reopen raw source paths
            out=root/'repaired';report=repair(old,out,root/'backups')
            self.assertEqual(report['half_inning_links_reclassified'],1)
            self.assertEqual(report['classification_pa_groups']['ALIGNED_HIT_OR_ERROR_CLASSIFICATION_DIFFERENCE'],1)
            self.assertTrue(report['baseline_reproduced']);self.assertFalse(report['counts_modified'])
            self.assertEqual(before,{p.name:sha(p) for p in old.iterdir()})
            self.assertEqual(sha(old/'game_metric_comparisons.csv'),sha(out/'game_metric_comparisons.csv'))
            self.assertEqual({p.name:sha(p) for p in out.iterdir()},{p.name:sha(p) for p in Path(report['backup']).iterdir()})
            with self.assertRaises(FileExistsError):repair(old,out,root/'backups')

    def test_tampered_feed_rejected_before_publish(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);old,raw,cache=self.make_audit(root);(cache/'1/feed.json').write_text('{}')
            with self.assertRaises(ValueError):repair(old,root/'out',root/'backups')
            self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
