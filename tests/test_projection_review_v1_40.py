import unittest
from projection_review_v1_40 import review, identity
class ReviewTests(unittest.TestCase):
    def fixture(self):
        home={'hitter':[dict(season='2027',player_type='hitter',mlbam_id='1',
            weighted_actuals__PA='100',weighted_actuals__HR='10',weighted_actuals__AVG='.25')],
            'pitcher':[dict(season='2027',player_type='pitcher',mlbam_id='2',
            weighted_actuals__IP='100',weighted_actuals__SO='100',weighted_actuals__W='5')]}
        p=[dict(player_type='hitter',mlbam_id='1',eligible='True',source_season='2026',metric=m) for m in ('gb_rate','ld_rate','fb_rate','pull_air_rate')]
        p+=[dict(player_type='pitcher',mlbam_id='2',eligible='True',source_season='2025',metric='pull_air_rate')]
        src={('steamer','hitter'):{'1':dict(name='One',PA=200.,HR=30.,AVG=.3),'3':dict(name='Three',PA=10.)},
             ('depth_charts','hitter'):{'1':dict(name='One Variant',PA=150.,HR=20.)},
             ('steamer','pitcher'):{'2':dict(name='Two',IP=80.,SO=90.,W=4.)},
             ('depth_charts','pitcher'):{}}
        return home,p,src
    def test_names_no_name_matching_and_vintage(self):
        h,p,s=self.fixture();n,e,_,_,_,_=review(h,p,s)
        self.assertEqual(n['hitter'][0]['name'],'One')
        self.assertEqual(n['hitter'][0]['feature_vintage'],'CURRENT_2026_ALL_FOUR')
        self.assertEqual(n['pitcher'][0]['feature_vintage'],'OLDER_ONLY')
        self.assertEqual(identity(s,'pitcher','1')[1],'UNRESOLVED_NO_ID_NAME')
        self.assertTrue(e)
    def test_component_identity_and_common_metric_pools(self):
        h,p,s=self.fixture();_,_,pairs,cov,components,summary=review(h,p,s)
        self.assertTrue(all(abs(r['accounting_residual'])<1e-10 for r in components))
        common=[r for r in summary if r['pool']=='COMMON_BOTH']
        self.assertEqual({r['metric'] for r in common},{'PA','HR'})
        self.assertEqual(len({r['membership_sha256'] for r in common}),1)
        self.assertTrue(any(r['status']=='BENCHMARK_ONLY' for r in cov))
        self.assertFalse(next(r for r in pairs if r['metric']=='AVG')['common_both_benchmarks'])
    def test_future_and_duplicates_rejected(self):
        h,p,s=self.fixture();h['hitter'][0]['season']='2028'
        with self.assertRaises(ValueError):review(h,p,s)
        h,p,s=self.fixture();h['hitter']*=2
        with self.assertRaises(ValueError):review(h,p,s)
    def test_zero_preserved_and_missing_not_filled(self):
        h,p,s=self.fixture();s['steamer','pitcher']['2']['W']=0
        _,_,pairs,_,_,_=review(h,p,s)
        self.assertEqual(next(r for r in pairs if r['metric']=='W')['benchmark'],0)
        self.assertFalse(any(r['metric']=='QS' for r in pairs))

class PipelineTests(unittest.TestCase):
    def test_manifest_pipeline_backup_and_immutable_stats(self):
        import csv,json,tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from standalone_io_v1_0 import dump,sha,tree
        from projection_review_v1_40 import run
        from project_2027_v1_31 import FILES,FIELDS
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);export=root/'export';base=root/'base';bench=root/'bench'
            for d in (export,base,bench):d.mkdir()
            def write(p,rows):
                fields=list(dict.fromkeys(k for r in rows for k in r))
                with p.open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            for (s,role),name in FILES.items():
                write(bench/name,[dict(Name='Test',MLBAMID='1',IP=100,PA=100,SO=90,W=5)])
            dump(base/'report.json',dict(version='1.31.0',benchmark_vintage='2026-11-13'))
            dump(base/'input_hashes.json',{str(bench/n):sha(bench/n) for n in FILES.values()})
            dump(base/'output_sha256.json',tree(base))
            dump(export/'report.json',dict(version='1.39.0',valuation_enabled=False,models_refitted=False,
                forecast_counts=dict(hitter=1,pitcher=1)))
            for role in FIELDS:
                row=dict(season='2027',player_type=role,mlbam_id='1')
                row.update({'weighted_actuals__'+m:100 for m in FIELDS[role]})
                write(export/f'side_by_side_2027_{role}s.csv',[row])
            write(export/'player_feature_provenance.csv',[dict(player_type='hitter',mlbam_id='1',eligible='True',source_season='2026',metric='pull_air_rate')])
            for name in ('largest_changes.csv','player_adjustments.csv'):
                write(export/name,[dict(player_type='pitcher',mlbam_id='1',metric='SO',delta='0.5')])
            dump(export/'input_hashes.json',{str(base/'report.json'):sha(base/'report.json')})
            dump(export/'output_sha256.json',tree(export))
            before={str(p):tree(p) for p in (base,export,bench)}
            a=SimpleNamespace(export=export,baseline=base,benchmarks=bench,output=root/'out',backup_root=root/'backups')
            r=run(a)
            self.assertFalse(r['forecasts_modified'])
            self.assertEqual(tree(root/'out'),tree(Path(r['backup'])))
            self.assertEqual(before,{str(p):tree(p) for p in (base,export,bench)})
            with self.assertRaises(FileExistsError):run(a)
            # Snapshot tampering is rejected before creating a new report.
            (bench/next(iter(FILES.values()))).write_text('tampered')
            a.output=root/'bad'
            with self.assertRaises(ValueError):run(a)
            self.assertFalse(a.output.exists())
