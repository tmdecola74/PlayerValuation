import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from audit_actuals_final_differences_v1_0 import audit, summarize_pa, candidate_play, classify, sha, write_csv, csv_rows
from actuals_final_audit_support_v1_0 import BOX_FIELDS


def pitch(event='single', batter=10,pitcher=20):
    return dict(game_pk=1,at_bat_number=1,pitch_number=1,batter=batter,pitcher=pitcher,
                balls=0,strikes=0,events=event,game_date='2016-04-01',game_type='R')


def feed(event='field_error'):
    teams={}
    for side,pid in [('home',10),('away',20)]:
        b={v:0 for v in BOX_FIELDS['hitter'].values()}
        b.update(plateAppearances=1,atBats=1)
        p={v:0 for v in BOX_FIELDS['pitcher'].values()}
        p.update(battersFaced=1,inningsPitched='0.0')
        teams[side]=dict(teamStats=dict(batting=b,pitching=p),players={str(pid):dict(person=dict(id=pid),stats=dict(batting=b,pitching=p))})
    play=dict(about=dict(atBatIndex=0,isComplete=True,inning=1,halfInning='top'),
              matchup=dict(batter=dict(id=10),pitcher=dict(id=20)),
              result=dict(eventType=event,description='fixture only'),
              playEvents=[dict(isPitch=True,pitchNumber=1,count=dict(balls=0,strikes=0))])
    return dict(gamePk=1,gameData=dict(game=dict(type='R',season='2016'),status=dict(abstractGameState='Final',detailedState='Final')),
                liveData=dict(boxscore=dict(teams=teams),plays=dict(allPlays=[play])))


class FinalAuditTests(unittest.TestCase):
    def fixture(self,t,cached=False,extra_pitch=False):
        root=Path(t);folder=root/'baseline';folder.mkdir();raw=root/'raw.csv'
        rows=[pitch()]
        if extra_pitch:rows.append(pitch())
        write_csv(raw,rows,list(rows[0]))
        (folder/'source_windows.json').write_text(json.dumps([dict(day='2016-04-01',status='COMPLETE',raw_path=str(raw),raw_hash=sha(raw),rows=len(rows),source_rows=len(rows))]))
        (folder/'reconciliation_report.json').write_text(json.dumps(dict(seasons=[2016])))
        case=dict(season=2016,player_type='hitter',mlbam_id=10,name='Test',metric='H',fangraphs_actual=0,
                  terminal_count=1,rule_count=1,evidence_count=0 if cached else 1,final_difference=0 if cached else 1,status='UNRESOLVED_DIFFERENCE')
        # Use a nonzero final discrepancy even when MLB hit/error evidence replaces the raw hit.
        if cached:case.update(fangraphs_actual=1,final_difference=-1)
        write_csv(folder/'discrepancies.csv',[case],list(case))
        cache=root/'cache';cache.mkdir()
        if cached:self.save_feed(cache,feed())
        return root,folder,raw,cache

    def save_feed(self,cache,payload):
        d=cache/'1';d.mkdir(exist_ok=True);(d/'feed.json').write_text(json.dumps(payload))
        (d/'source.json').write_text(json.dumps(dict(game_pk=1,season=2016,sha256=sha(d/'feed.json'))))

    def test_read_only_bridge_and_complete_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t,True);before=sha(raw)
            r=audit(folder,cache,root/'out',root/'backups')
            self.assertTrue(r['baseline_reproduced']);self.assertFalse(r['counts_modified'])
            self.assertEqual(sha(raw),before)
            self.assertEqual(r['classification_pa_groups']['ALIGNED_HIT_OR_ERROR_CLASSIFICATION_DIFFERENCE'],1)
            self.assertEqual({p.name:sha(p) for p in (root/'out').iterdir()},{p.name:sha(p) for p in Path(r['backup']).iterdir()})
            with self.assertRaises(FileExistsError):audit(folder,cache,root/'out',root/'backups')

    def test_hash_tamper_fails_without_output(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t);raw.write_text('tamper')
            with self.assertRaises(ValueError):audit(folder,cache,root/'out',root/'backups')
            self.assertFalse((root/'out').exists())

    def test_bad_cache_hash_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t,True);(cache/'1/feed.json').write_text('{}')
            with self.assertRaises(ValueError):audit(folder,cache,root/'out',root/'backups')
            self.assertFalse((root/'out').exists())

    def test_index_alone_or_player_or_count_cannot_prove_link(self):
        pa=summarize_pa([pitch()]);f=feed()
        self.assertFalse(candidate_play(f,pa)[1])
        f['liveData']['plays']['allPlays'][0]['matchup']['pitcher']['id']=999
        p,fail=candidate_play(f,pa);self.assertIn('PITCHER_IDENTITY_NOT_PROVEN',fail)
        self.assertEqual(classify(pa,p,fail),'PLAY_LINK_REVIEW_REQUIRED')
        changed=pitch();changed['balls']=1
        self.assertIn('PRE_PITCH_COUNT_MISMATCH',candidate_play(feed(),summarize_pa([changed]))[1])

    def test_unknown_not_zero_and_runner_only_not_pa(self):
        pa=summarize_pa([pitch()]);p,fail=candidate_play(feed('game_advisory'),pa)
        self.assertEqual(classify(pa,p,fail),'UNKNOWN_MLB_OUTCOME_REVIEW')
        p,fail=candidate_play(feed('pickoff_1b'),pa)
        self.assertEqual(classify(pa,p,fail),'ALIGNED_EXTRA_RECONSTRUCTED_OUTCOME')
        pa=summarize_pa([pitch('')]);p,fail=candidate_play(feed('catcher_interf'),pa)
        self.assertEqual(classify(pa,p,fail),'ALIGNED_MISSING_TERMINAL_OUTCOME')

    def test_cache_change_baseline_bridge_is_explicit(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t)
            self.save_feed(cache,feed())
            r=audit(folder,cache,root/'out',root/'backups')
            self.assertFalse(r['baseline_reproduced']);self.assertEqual(len(r['baseline_bridge_issues']),1)

    def test_paired_residual_is_lead_not_confirmation(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t)
            cases=list(csv_rows(folder/'discrepancies.csv'))
            other=dict(cases[0],player_type='pitcher',mlbam_id='20')
            cases.append(other);write_csv(folder/'discrepancies.csv',cases,list(cases[0]))
            r=audit(folder,cache,root/'out',root/'backups')
            self.assertEqual(r['primary_uncached_games'],1)
            leads=list(csv_rows(root/'out/candidate_pa_reviews.csv'))
            self.assertTrue(all(x['classification']=='CACHE_MISSING' for x in leads))

    def test_holdout_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t)
            cases=list(csv_rows(folder/'discrepancies.csv'));cases[0]['season']='2026'
            write_csv(folder/'discrepancies.csv',cases,list(cases[0]))
            with self.assertRaises(ValueError):audit(folder,cache,root/'out',root/'backups')

    def test_exact_duplicate_pitch_collapses_but_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t,extra_pitch=True)
            self.assertTrue(audit(folder,cache,root/'out',root/'backups')['baseline_reproduced'])
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t)
            write_csv(raw,[pitch(),pitch('double')],list(pitch()))
            w=json.loads((folder/'source_windows.json').read_text());w[0].update(raw_hash=sha(raw),rows=2,source_rows=2)
            (folder/'source_windows.json').write_text(json.dumps(w))
            with self.assertRaises(ValueError):audit(folder,cache,root/'out',root/'backups')

    def test_rejected_boxscore_block_never_replaces(self):
        with tempfile.TemporaryDirectory() as t:
            root,folder,raw,cache=self.fixture(t)
            f=feed();f['liveData']['boxscore']['teams']['home']['teamStats']['batting']=copy.deepcopy(f['liveData']['boxscore']['teams']['home']['teamStats']['batting'])
            f['liveData']['boxscore']['teams']['home']['teamStats']['batting']['hits']=1
            self.save_feed(cache,f)
            self.assertTrue(audit(folder,cache,root/'out',root/'backups')['baseline_reproduced'])

if __name__=='__main__':unittest.main()
