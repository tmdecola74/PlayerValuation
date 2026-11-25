import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import pitcher_workload_v1_27 as m
import participation_label_overlay_v1_27 as overlay
from standalone_io_v1_0 import dump, sha, tree

K=(2026,'pitcher','1')
V=dict(OUTS=450.,IP=150.,H=130.,ER=50.,BB=40.,SO=140.,HR=15.,W=10.,
       SV=5.,HLD=2.,QS=15.,ERA=3.,WHIP=170/150,SV_plus_HLD=7.)


class WorkloadTests(unittest.TestCase):
    def test_known_zero_is_not_assumed_no_appearance(self):
        self.assertEqual(m.observed({},K)[:2],(None,None))
        self.assertEqual(m.observed({K+('OUTS',):0},K)[:2],(0,None))
        self.assertEqual(m.observed({K+('OUTS',):0,K+('G',):1},K)[:2],(0,1))
        self.assertEqual(m.observed({K+('G',):0},K)[:2],(0,0))
        with self.assertRaises(ValueError):
            m.observed({K+('G',):0,K+('OUTS',):1},K)

    def test_appearance_model_and_conditional_model_are_independent(self):
        train=[([float(i%2)],100. if i%2 else 0.,i%2) for i in range(100)]
        model=m.fit(train)
        high=m.forecast(K,V,[1.],'STARTER','AVAILABLE',model)
        low=m.forecast(K,V,[0.],'STARTER','UNKNOWN',model)
        self.assertGreater(high['probability'],low['probability'])
        self.assertAlmostEqual(high['conditional_ip'],100.)
        self.assertAlmostEqual(low['two_part_ip'],low['probability']*low['conditional_ip'])
        self.assertEqual([high[k] for k in m.ANCHORS],[3.,5.,2.])
        only=m.fit([r for r in train if r[2]])
        self.assertIsNone(only['logistic'])
        self.assertIsNotNone(only['conditional'])
        self.assertIsNotNone(only['direct'])

    def test_availability_dates_and_no_current_actual_in_features(self):
        a={K+('OUTS',):600.,K+('G',):30.,K+('GS',):30.}
        self.assertEqual(m.features(K,V,a,{}),m.features(K,V,{},{}))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a.csv'
            header='season,mlbam_id,published_on,preseason_cutoff,availability,source\n'
            p.write_text(header+'2026,1,2026-02-20,2026-03-01,LIMITED,source\n')
            self.assertEqual(m.availability(p,{})[K],'LIMITED')
            p.write_text(header+'2026,1,2026-03-01,2026-03-01,LIMITED,source\n')
            with self.assertRaises(ValueError):
                m.availability(p,{})

    def test_diagnostic_bands_do_not_select_and_current_labels_are_excluded(self):
        rows=[]
        for y in (2022,2023,2024,2025,2026):
            for d,c in [('ALL','ALL'),('PRIOR_ROLE','STARTER'),('ACTUAL_EXPOSURE','GE100_IP')]:
                for arm,loss in [('accepted_ip',5),('direct_ip',4 if y<2026 else 100),('two_part_ip',6)]:
                    rows.append(dict(season=y,task='EXPECTED_IP',dimension=d,cohort=c,
                        method=arm,n=100,mse=loss,membership_sha256='same'))
        choice=m.select(rows,2026)
        self.assertEqual(choice['method'],'direct_ip')
        self.assertEqual(choice,m.select([r for r in rows if r['season']<2026 and r['dimension']!='ACTUAL_EXPOSURE'],2026))

    def test_pipeline_freezes_before_opening_evaluation_labels(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); ref,lab,parent=[root/n for n in ('v124','lab','v123')]
            for p in (ref,lab,parent):
                p.mkdir()
            lp=lab/'training_labels.parquet'; hp=lab/'holdout_labels.parquet'
            def labels_for(path,years):
                data=[]
                for y in years:
                    for n in range(16,61):
                        for k,v in [('OUTS',300 if n>15 else 0),('G',30 if n>15 else 0),('GS',30 if n>15 else 0)]:
                            data.append(dict(season=y,player_type='pitcher',mlbam_id=str(n),
                                             metric=k,eligible=True,label_value=v))
                if path==lp:
                    data.append(dict(season=2023,player_type='pitcher',mlbam_id='677020',metric='G',eligible=True,label_value=13))
                j=path.with_suffix('.json');dump(j,data)
                with duckdb.connect() as db:
                    db.read_json(str(j)).write_parquet(str(path))
                j.unlink()
            labels_for(lp,range(2016,2026));labels_for(hp,[2026])
            dump(lab/'label_build_report.json',{})
            def forecast_file(path,years):
                m.emit(path,[dict(season=y,player_type='pitcher',mlbam_id=str(n),
                                 method=m.BASE,metric=k,prediction=v)
                              for y in years for n in range(1,61) for k,v in V.items()])
                dump(path.parent/'forecast_freeze.json',{path.name:sha(path),**(
                    {'build_report.json':sha(ref/'build_report.json')} if path.parent==ref else {})})
            h=parent/'historical_forecasts.csv'
            forecast_file(h,m.YEARS)
            dump(ref/'build_report.json',dict(version='1.24.0',evaluation_outcomes_read=False,
                       label_report_sha256=sha(lab/'label_build_report.json')))
            forecast_file(ref/'frozen_2026_forecasts.csv',[2026])
            dump(ref/'input_hashes.json',{str(lp):sha(lp),str(h):sha(h)})
            dump(parent/'input_hashes.json',{str(lp):sha(lp)})
            for p in (ref,lab,parent):
                dump(p/'output_sha256.json',tree(p))
            a=argparse.Namespace(reference=ref,parent=parent,labels=lab,availability=None,
                      output=root/'run',backup_root=root/'backups',run=root/'run')
            a.overlay=root/'overlay'
            frozen_hash=sha(lp)
            for y in m.YEARS:
                d=root/(f'pitcher_label_coverage_{y}_'+('corrected' if y==2023 else 'v1_26_1'))
                d.mkdir()
                team_counts={str(i):162 for i in range(1,31)}
                season=dict(season=y,season_certified=True,source_complete=True,conflicting_pitchers=0,pool=60,
                            schedule_final_games=2430,boxscores_verified=2430,standings_team_counts=team_counts,
                            schedule_team_counts=team_counts,statuses={'VERIFIED_NO_APPEARANCE':15,'VERIFIED_APPEARED':45})
                report=dict(version='1.26.1',labels_modified=False,models_refitted=False,seasons=[season])
                if y==2023:
                    report['applied_label_corrections']=[dict(season=2023,player_type='pitcher',mlbam_id='677020',
                        metric='G',old_value=13,new_value=14,source=overlay.SOURCE,reason='Walk-off balk')]
                dump(d/'report.json',report)
                dump(d/'input_hashes.json',{str(lp):sha(lp),str(h):sha(h)})
                m.emit(d/'pitcher_label_coverage.csv',[dict(season=y,mlbam_id=str(n),
                    season_certified=True,appearance_identity_verified=True,observed_boxscore_G=0 if n<=15 else 30,
                    status='VERIFIED_NO_APPEARANCE' if n<=15 else 'VERIFIED_APPEARED',
                    proposed_G=0 if n<=15 else 30,proposed_OUTS=0 if n<=15 else None,
                    existing_G=None if n<=15 else 30,existing_OUTS=None if n<=15 else 300) for n in range(1,61)])
                dump(d/'output_sha256.json',tree(d))
            with patch.dict(overlay.COUNTS,{y:15 for y in m.YEARS}):
                p=argparse.Namespace(parent=parent,labels=lab,audits_root=root,output=a.overlay,backup_root=a.backup_root)
                result=overlay.build(p)
                self.assertEqual(result['certified_zero_players'],105)
                self.assertEqual(result['metric_rows'],211)
                self.assertEqual(sha(lp),frozen_hash)
                self.assertEqual([r['new_value'] for r in m.rows(a.overlay/'participation_label_overlay.csv')
                                  if r['mlbam_id']=='677020'],['14'])
                label_reader=m.labels
                with patch.object(m,'labels',side_effect=lambda p,*args: self.assertEqual(p,lp) or label_reader(p,*args)):
                    report=m.build(a)
            self.assertEqual(sha(lp),frozen_hash)
            self.assertIn(2026,report['participation_fit_origins'])
            frozen=tree(a.run)
            a.output=root/'eval'
            with patch.object(m,'fit',side_effect=AssertionError('evaluation fit')):
                report=m.evaluate(a)
            self.assertFalse(report['selection_uses_2026'])
            self.assertEqual(report['holdout_participation_interpretation'],'POSITIVE_ONLY_DIAGNOSTIC')
            self.assertEqual(report['holdout_unlabelled_participation'],15)
            self.assertEqual(tree(a.run),frozen)
            self.assertEqual(tree(a.output),tree(Path(report['backup'])))
            (a.run/'frozen_2026_workload.csv').write_text('tampered')
            a.output=root/'bad'
            with self.assertRaises(ValueError):
                m.evaluate(a)


if __name__=='__main__':
    unittest.main()
