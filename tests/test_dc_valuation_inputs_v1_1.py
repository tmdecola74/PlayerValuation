import unittest,json,tempfile,math
from pathlib import Path
from unittest.mock import patch
from prepare_dc_valuation_inputs_v1_1 import innings,dc_calibration,eligibility_mapping,normalized,read_standings

class Sheet:
 def __init__(self,title,rows):self.title=title;self.values=rows
class Book:
 def __init__(self,sheets):self.sheets=sheets;self.closed=False
 def __iter__(self):return iter(self.sheets)
 def close(self):self.closed=True

class DCInputTests(unittest.TestCase):
 def make_group(self,year,name,r_slope,low_ip=False):
  result=[]
  for i in range(15):
   points=15-i;ip=900 if low_ip and i==0 else 1200
   result.append(dict(season=year,league_id=name,team_name=str(i),AB=7000,H_hit=1750,IP=ip,ER=500,BB_allowed=400,H_allowed=1100,R=500+r_slope*points,HR=180+5*points,RBI=600+15*points,SB=80+4*points,AVG=.24+.001*points,W=50+2*points,SV=10+4*points,K=1000+30*points,ERA=4.5-.05*points,WHIP=1.4-.01*points))
  return result
 def test_baseball_innings_not_decimal_tenths(self):
  self.assertAlmostEqual(innings(1000.1),1000+1/3);self.assertAlmostEqual(innings(1000.2),1000+2/3)
  with self.assertRaises(ValueError):innings(1000.3)
 def test_within_league_slopes_and_equal_season_weights(self):
  a=self.make_group(2023,'A',10);b=self.make_group(2024,'B',20);c=self.make_group(2024,'C',20)
  for r in c:r['R']+=10000
  cal,_=dc_calibration(a+b+c,{(2023,'A'):a,(2024,'B'):b,(2024,'C'):c})
  self.assertAlmostEqual(cal['annual_slopes'][2023]['R'],10);self.assertAlmostEqual(cal['annual_slopes'][2024]['R'],20);self.assertAlmostEqual(cal['slopes']['R'],15)
 def test_low_innings_leagues_excluded_from_rates_only(self):
  a=self.make_group(2025,'A',10);b=self.make_group(2025,'B',20,True)
  cal,pen=dc_calibration(a+b,{(2025,'A'):a,(2025,'B'):b})
  self.assertEqual(len(pen),1);self.assertEqual(sum(r['category']=='R' for r in cal['league_fits']),2);self.assertEqual(sum(r['category']=='ERA' for r in cal['league_fits']),1)
 def test_two_way_asset_has_two_roles_one_canonical_identity(self):
  players=[dict(name='Shohei Ohtani',player_type=t,player_id='same',teams=['LAD'],mlbam_ids=['660271']) for t in ['hitter','pitcher']]
  b=Book([Sheet('ADP',[('Player ID','Player','Team','Position(s)','ADP','Min Pick','Max Pick','# Picks'),(9810,'Ohtani, Shohei','LAD','UT, P',1.3,1,3,20)])])
  with patch('prepare_dc_valuation_inputs_v1_1.openpyxl.load_workbook',return_value=b):mapped,review,_=eligibility_mapping('unused',players)
  self.assertTrue(b.closed);self.assertEqual(len(mapped),2);self.assertEqual({r['player_id'] for r in mapped},{'same'});self.assertEqual(review,[])
 def test_nfbc_same_name_assets_not_collapsed(self):
  players=[dict(name='Jacob Wilson',player_type='hitter',player_id='a',teams=['ATH'],mlbam_ids=['805779'])]
  header=('Player ID','Player','Team','Position(s)','ADP','Min Pick','Max Pick','# Picks');b=Book([Sheet('ADP',[header,(1,'Wilson, Jacob','ATH','SS',170,150,200,20),(2,'Wilson, Jacob','HOU','UT',745,631,631,1)])])
  with patch('prepare_dc_valuation_inputs_v1_1.openpyxl.load_workbook',return_value=b):mapped,review,_=eligibility_mapping('unused',players)
  self.assertEqual(len(mapped),1);self.assertEqual(len(review),1);self.assertEqual(mapped[0]['nfbc_player_id'],'1')
 def test_anchored_canonical_preferred_to_unanchored_duplicate_and_alias_team(self):
  players=[dict(name='Corbin Carroll',player_type='hitter',player_id='a',teams=['ARI'],mlbam_ids=['1']),dict(name='Corbin Carroll',player_type='hitter',player_id='orphan',teams=['ARZ'],mlbam_ids=[])]
  b=Book([Sheet('ADP',[('Player ID','Player','Team','Position(s)','ADP','Min Pick','Max Pick','# Picks'),(1,'Carroll, Corbin','ARZ','OF',10,7,15,20)])])
  with patch('prepare_dc_valuation_inputs_v1_1.openpyxl.load_workbook',return_value=b):mapped,review,_=eligibility_mapping('unused',players)
  self.assertEqual(mapped[0]['player_id'],'a');self.assertFalse(review)
 def test_unique_offseason_team_disagreement_is_flagged_not_a_merge(self):
  players=[dict(name='Player Name',player_type='hitter',player_id='a',teams=['SEA'],mlbam_ids=['1'])]
  b=Book([Sheet('ADP',[('Player ID','Player','Team','Position(s)','ADP','Min Pick','Max Pick','# Picks'),(1,'Name, Player','TOR','OF',10,7,15,20)])])
  with patch('prepare_dc_valuation_inputs_v1_1.openpyxl.load_workbook',return_value=b):mapped,review,_=eligibility_mapping('unused',players)
  self.assertEqual(mapped[0]['match_method'],'UNIQUE_ANCHORED_NAME_OFFSEASON_TEAM_DISAGREEMENT')
 def test_historical_duplicate_hit_columns_and_2025_rounding(self):
  rows=[['Rank','Owner','Team','League','Draft Pos','Hitting','Pitching','Overall Pts','Back','R','HR','RBI','SB','AB','H','AVG','K','W','SV','IP','ER','ERA','BB','H','WHIP']]
  for i in range(15):
   ab=7000;h=1837;ip=1200+2/3;er=430;bb=350;ha=1000
   avg=round(round(h/ab,4),3);era=round(round(9*er/ip,3),2);whip=round(round((bb+ha)/ip,3),2)
   rows.append([i+1,'Owner',str(i),'L',i+1,0,0,0,0,1000,250,950,150,ab,h,avg,1300,80,50,1200.2,er,era,bb,ha,whip])
  book=Book([Sheet('2025',rows)])
  with patch('prepare_dc_valuation_inputs_v1_1.openpyxl.load_workbook',return_value=book):records,groups=read_standings('unused')
  self.assertTrue(book.closed);self.assertEqual(records[0]['H_hit'],1837);self.assertEqual(records[0]['H_allowed'],1000);self.assertAlmostEqual(records[0]['AVG'],1837/7000)

if __name__=='__main__':unittest.main()
