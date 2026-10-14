import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_dc_values_v1_1 as reporting

class ReportingTests(unittest.TestCase):
    def test_reviewed_links_adp_watchlist_and_complete_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); inputs=base/'inputs'; inputs.mkdir()
            def write(name, rows):
                reporting.csv_out(inputs/name, rows)
            links=[('12299','de_vries','hitter','573.65'),('10253','miranda','hitter','745.5'),('12487','doyle','pitcher','740.55')]
            eligibility=[dict(nfbc_player_id=n,player_id=p,player_type=t,ADP=a,source_player_name=p,source_team='STL') for n,p,t,a in links]
            eligibility.append(dict(nfbc_player_id='low',player_id='low',player_type='hitter',ADP='749',source_player_name='Low',source_team='ATH'))
            write('nfbc15_dc_eligibility.csv',eligibility)
            # Original export lacks the newly reviewed canonical links.
            write('nfbc15_dc_adp.csv',[dict(nfbc_player_id=n,player_id='',player_type=t,ADP=a) for n,p,t,a in links if t=='hitter'][:1])
            review=[dict(nfbc_player_id=n,name=p,team='STL',player_type=t,ADP=a,reason='NO_PROJECTION_IDENTITY') for n,p,t,a in links]
            review.extend([dict(nfbc_player_id='missing',name='Missing',team='FA',player_type='pitcher',ADP='750',reason='NO_PROJECTION_IDENTITY'),dict(nfbc_player_id='low',name='Low',team='ATH',player_type='hitter',ADP='749',reason='OLD_IDENTITY_REASON')])
            write('nfbc15_dc_eligibility_review.csv',review)
            (inputs/'dc_input_audit.json').write_text('{}')
            before={p.name:p.read_bytes() for p in inputs.iterdir()}
            def engine(args):
                out=Path(args.output);out.mkdir()
                reporting.csv_out(out/'player_values.csv',[dict(player_id=p,player_type=t,draft_rank=i+1,name=p) for i,(n,p,t,a) in enumerate(links)])
                (out/'valuation_audit.json').write_text('{}')
            output=base/'result'
            with patch.object(reporting,'build_values',engine),patch.object(sys,'argv',['build','--inputs',str(inputs),'--output',str(output),'--backup-root',str(base/'backups')]),contextlib.redirect_stdout(io.StringIO()):
                reporting.main()
            with (output/'player_values_with_adp.csv').open(encoding='utf-8-sig',newline='') as f: values=list(csv.DictReader(f))
            for row,(nfbc,canonical,role,adp) in zip(values,links):
                self.assertEqual(row['nfbc_player_id'],nfbc)
                self.assertEqual(float(row['market_ADP']),float(adp))
                self.assertAlmostEqual(float(row['ADP_minus_value_rank']),float(adp)-int(row['draft_rank']))
            with (output/'unvalued_adp_watchlist.csv').open(encoding='utf-8-sig',newline='') as f:watch={r['nfbc_player_id']:r for r in csv.DictReader(f)}
            self.assertEqual(set(watch),{'low','missing'})
            self.assertEqual(watch['low']['reason'],'MAPPED_BUT_MISSING_OR_BELOW_FLOOR_PROJECTION_COMPONENTS')
            audit=json.loads((output/'valuation_audit.json').read_text())
            self.assertEqual(audit['unvalued_nfbc_assets'],2)
            self.assertEqual(audit['adp_matched_rows'],3)
            self.assertEqual(before,{p.name:p.read_bytes() for p in inputs.iterdir()})
            backup=Path(audit['backup'])
            for p in output.rglob('*'):
                if p.is_file():self.assertEqual(p.read_bytes(),(backup/p.relative_to(output)).read_bytes())

if __name__=='__main__':unittest.main()
