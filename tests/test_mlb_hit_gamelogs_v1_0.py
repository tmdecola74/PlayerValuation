import copy
import json
import tempfile
import unittest
from pathlib import Path
from audit_mlb_hit_gamelogs_v1_0 import build,normalize,write_csv,read_csv,sha


def payload(kind='gameLog',hits=1,games=1):
    stat=dict(hits=hits,doubles=0,triples=0,homeRuns=0,gamesPlayed=games)
    s=dict(season='2016',gameType='R',player=dict(id=10),sport=dict(id=1),team=dict(id=100),stat=stat)
    if kind=='gameLog':s.update(date='2016-04-01',game=dict(gamePk=1))
    return dict(stats=[dict(type=dict(displayName=kind),group=dict(displayName='hitting'),splits=[s])])


class GameLogTests(unittest.TestCase):
    def fixture(self,root):
        d=root/'discrepancies.csv';g=root/'games.csv'
        c=dict(season=2016,player_type='hitter',mlbam_id=10,name='Test',metric='H',fangraphs_actual=2,
               terminal_count=1,rule_count=1,evidence_count=1,final_difference=-1)
        r=dict(season=2016,player_type='hitter',mlbam_id=10,name='Test',metric='H',game_pk=1,
               terminal_count=1,rule_count=1,cached_mlb=False,metric_admitted=False,mlb_count='')
        write_csv(d,[c],list(c));write_csv(g,[r],list(r));return d,g

    def fetcher(self,hits=1):
        def f(url):return json.dumps(payload('gameLog' if 'stats=gameLog' in url else 'season',hits)).encode()
        return f

    def test_matching_logs_are_explicit_source_disagreement_and_full_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d,g=self.fixture(root);before=[sha(d),sha(g)]
            r=build(d,g,root/'out',root/'cache',root/'backup',True,self.fetcher(),0)
            self.assertEqual(r['specific_games_to_inspect'],0)
            self.assertIn('GAME_LOGS_AND_RECONSTRUCTION_AGREE_SOURCE_SEASON_TOTAL_DISAGREEMENT',r['season_statuses'])
            self.assertFalse(r['counts_modified']);self.assertEqual(before,[sha(d),sha(g)])
            tree=lambda p:{str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}
            self.assertEqual(tree(root/'out'),tree(Path(r['backup'])))
            # Offline resumability must never call the fetcher.
            fail=lambda u:(_ for _ in ()).throw(AssertionError('Network called'))
            build(d,g,root/'out2',root/'cache',root/'backup',False,fail,0)
            with self.assertRaises(FileExistsError):build(d,g,root/'out',root/'cache',root/'backup')

    def test_exact_game_mismatch_plan(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d,g=self.fixture(root)
            r=build(d,g,root/'out',root/'cache',root/'backup',True,self.fetcher(0),0)
            self.assertEqual(r['specific_games_to_inspect'],1)
            row=read_csv(root/'out/mismatched_games.csv')[0]
            self.assertEqual(row['date'],'2016-04-01');self.assertEqual(row['mlb_minus_reconstructed'],'-1')

    def test_missing_game_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d,g=self.fixture(root)
            def f(url):
                x=payload('gameLog' if 'stats=gameLog' in url else 'season')
                if 'stats=gameLog' in url:x['stats'][0]['splits'][0]['game']['gamePk']=2
                return json.dumps(x).encode()
            build(d,g,root/'out',root/'cache',root/'backup',True,f,0)
            rows=read_csv(root/'out/mismatched_games.csv')
            self.assertEqual(len(rows),2);self.assertTrue(all(x['mlb_minus_reconstructed']=='' for x in rows))

    def test_bad_ids_types_duplicates_and_pagination_rejected(self):
        variations=[]
        x=payload();x['stats'][0]['splits'][0]['player']['id']=11;variations.append(x)
        x=payload();x['stats'][0]['splits'][0]['gameType']='S';variations.append(x)
        x=payload();x['stats'][0]['splits']*=2;variations.append(x)
        x=payload();x['stats'][0]['totalSplits']=2;variations.append(x)
        for x in variations:
            with self.assertRaises(ValueError):normalize(x,2016,'hitter',10,'gameLog',{'H'})

    def test_missing_component_not_zero(self):
        x=payload();del x['stats'][0]['splits'][0]['stat']['doubles']
        with self.assertRaises(KeyError):normalize(x,2016,'hitter',10,'gameLog',{'1B'})
        x=payload();x['stats'][0]['splits'][0]['stat']['doubles']=2
        with self.assertRaises(ValueError):normalize(x,2016,'hitter',10,'gameLog',{'1B'})

    def test_season_sum_and_game_count_gates(self):
        for mode in ['hits','games']:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);d,g=self.fixture(root)
                def f(url):
                    x=payload('gameLog' if 'stats=gameLog' in url else 'season')
                    if 'stats=season' in url:x['stats'][0]['splits'][0]['stat'][mode if mode=='hits' else 'gamesPlayed']=2
                    return json.dumps(x).encode()
                if mode=='hits':
                    with self.assertRaises(ValueError):build(d,g,root/'out',root/'cache',root/'backup',True,f,0)
                    self.assertFalse((root/'out').exists())
                else:
                    r=build(d,g,root/'out',root/'cache',root/'backup',True,f,0)
                    self.assertEqual(r['game_count_warning_rows'],1)
                self.assertFalse((root/'cache/download.lock').exists())

    def test_tampered_cache_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d,g=self.fixture(root)
            build(d,g,root/'out',root/'cache',root/'backup',True,self.fetcher(),0)
            next((root/'cache').rglob('response.json')).write_text('{}')
            with self.assertRaises(ValueError):build(d,g,root/'out2',root/'cache',root/'backup')
            self.assertFalse((root/'out2').exists())

    def test_baseline_bridge_and_holdout_rejected(self):
        for mode in ['bridge','holdout']:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);d,g=self.fixture(root)
                if mode=='bridge':
                    rows=read_csv(g);rows[0]['rule_count']='2';write_csv(g,rows,list(rows[0]))
                else:
                    rows=read_csv(d);rows[0]['season']='2026';write_csv(d,rows,list(rows[0]))
                with self.assertRaises(ValueError):build(d,g,root/'out',root/'cache',root/'backup')
                self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
