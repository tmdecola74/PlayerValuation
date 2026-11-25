import csv,json,hashlib
from pathlib import Path
from collections import Counter
O=Path('outputs/minor_history_2027_research')
def read(p):
 with Path(p).open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def save(name,rr):
 with (O/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
raw=read('outputs/international_intake_2019_2026_v2/international_stints_prepared.csv')
api_records=json.loads(Path('work/public_player_identity_lookup.json').read_text())
api={str(p['id']):p for r in api_records if r['query'].isdigit() for p in r.get('people',[])}
P1=[
 dict(name='Teruaki Sato',PlayerId='sa3063811',role='hitter',league='NPB',home_registry_id='41045153',mlbam_id='831664',DOB='1999-03-13',identity_status='CORROBORATED_MLBAM_TIE',source_year=2021,fingerprint={'G':126,'PA':455,'AB':425,'H':101,'HR':24,'SO':173},home_source='https://npb.jp/bis/eng/players/41045153.html',independent_source='https://www.thebaseballcube.com/content/player/239483/',MLB_source='https://www.mlb.com/player/teruaki-sato-831664',market_status='REPORTED_CUBS_AGREEMENT_PENDING_FORMAL_TRANSACTION',status_source='https://www.mlb.com/news/teruaki-sato-cubs-contract',status_evidence_date='2026-11-24'),
 dict(name='Hiromi Itoh',PlayerId='sa3063835',role='pitcher',league='NPB',home_registry_id='51355153',mlbam_id='808955',DOB='1997-08-31',identity_status='CORROBORATED_MLBAM_TIE',source_year=2021,fingerprint={'G':23,'IP':146,'H':125,'HR':8,'BB':53,'SO':141},home_source='https://npb.jp/bis/eng/players/51355153.html',independent_source='https://www.thebaseballcube.com/content/player/239449/',MLB_source='https://www.mlb.com/player/hiromi-itoh-808955',market_status='POSTED_FREE_AGENT_NO_LATER_AGREEMENT_VERIFIED',status_source='https://www.mlb.com/news/mlb-rumors-and-2026-27-free-agent-news-november-21',status_evidence_date='2026-11-21'),
 dict(name='Si-hwan Roh',PlayerId='sa3012734',role='hitter',league='KBO',home_registry_id='69737',mlbam_id='823574',DOB='2000-12-03',identity_status='CORROBORATED_PROFILE_TIE_NOT_DIRECT_ID_COOCCURRENCE',source_year=2026,fingerprint={'G':127,'PA':571,'AB':505,'H':143,'HR':29,'SO':147},home_source='https://www.koreabaseball.com/Record/Player/HitterDetail/Basic.aspx?playerId=69737',independent_source='https://www.fangraphs.com/players/si-hwan-roh/sa3012734/stats/batting',MLB_source='https://www.mlb.com/player/si-hwan-roh-823574',market_status='POSTED_FREE_AGENT_NO_LATER_AGREEMENT_VERIFIED',status_source='https://www.mlb.com/news/mlb-free-agents-2026-2027',status_evidence_date='2026-11-22'),
 dict(name='Kaima Taira',PlayerId='sa3062990',role='pitcher',league='NPB',home_registry_id='31035136',mlbam_id='838343',DOB='1999-11-15',identity_status='CORROBORATED_MLBAM_TIE_BIOGRAPHIC_FIELD_CONFLICT_FLAGGED',source_year=2019,fingerprint={'G':26,'IP':24,'H':29,'HR':2,'BB':9,'SO':23},home_source='https://npb.jp/bis/eng/players/31035136.html',independent_source='https://pacificleague.com/en/player/518051',MLB_source='https://statsapi.mlb.com/api/v1/people/838343',market_status='REPORTED_BLUE_JAYS_AGREEMENT_PENDING_FORMAL_TRANSACTION',status_source='https://www.mlb.com/news/kaima-taira-profile-blue-jays',status_evidence_date='2026-11-24')]
identities=[]
for p in P1:
 rr=[r for r in raw if r['PlayerId']==p['PlayerId'] and r['player_type']==p['role'] and int(r['Season'])==p['source_year']]
 assert len(rr)==1 and all(float(rr[0][c])==v for c,v in p['fingerprint'].items())
 assert api[p['mlbam_id']]['birthDate']==p['DOB']
 assert api[p['mlbam_id']]['primaryPosition']['type']==('Pitcher' if p['role']=='pitcher' else 'Infielder')
 identities.append({**{k:v for k,v in p.items() if k!='fingerprint'},'identity_status':'CORROBORATED_OFFICIAL_MLB_API_DOB_ROLE_AND_HOME_RECORD','official_API_source':'https://statsapi.mlb.com/api/v1/people/'+p['mlbam_id'],'biographic_conflict':'BATS_MLB_R_VS_NPB_L_DO_NOT_USE_BATTING_HAND' if p['PlayerId']=='sa3062990' else '', 'fingerprint':json.dumps(p['fingerprint'],sort_keys=True),'fingerprint_matches_supplied_export':True,'canonical_key':'MLBAM:'+p['mlbam_id'],'translation_status':'UNVALIDATED_NO_FORECAST','as_of':'2026-11-24'})
save('P1_corroborated_identity_and_status.csv',identities)
(O/'official_MLB_identity_responses.json').write_text(json.dumps([r for r in api_records if r['query'].isdigit()],indent=2))
statuses=[
 dict(mlbam_id='650331',name='Lewin Diaz',verified_primary_role='hitter',latest_verified_record='Samsung Lions 2026 KBO player registration',record_date='2026 end-season snapshot',status='OVERSEAS_RECORD_VERIFIED_2027_CONTRACT_UNVERIFIED',source='https://eng.koreabaseball.com/Teams/PlayerInfoHitter/Summary.aspx?pcode=54400',note='No MLB arrival or future contract inferred.'),
 dict(mlbam_id='641541',name='Jon Duplantier',verified_primary_role='pitcher',latest_verified_record='Yokohama DeNA BayStars official 2026 roster',record_date='2026 end-season snapshot',status='OVERSEAS_PITCHER_ROLE_VERIFIED',source='https://npb.jp/bis/eng/players/13715150.html',note='Priority queue listed hitter history; official primary role pitcher. Source latest affiliate differs; retain role/team conflict flags.'),
 dict(mlbam_id='672773',name='Elvis Luciano',verified_primary_role='pitcher',latest_verified_record='Yomiuri Giants official 2026 roster',record_date='2026 end-season snapshot',status='OVERSEAS_RECORD_VERIFIED_2027_CONTRACT_UNVERIFIED',source='https://npb.jp/bis/eng/players/03005157.html',note='No posting or MLB return independently established.'),
 dict(mlbam_id='642451',name='Luis Liberato',verified_primary_role='hitter',latest_verified_record='Aguilas Cibaenas winter roster',record_date='2026-11-13',status='WINTER_ROSTER_VERIFIED_SUMMER_2027_UNVERIFIED',source='https://aguiluchos.com/wp-content/uploads/2026/11/Boletin-de-Prensa-No.25-Aguilas-Cibaenas-Serie-Regular-2026-27.pdf',note='Winter affiliation does not establish a summer MLB contract.'),
 dict(mlbam_id='664057',name='Andrew Stevenson',verified_primary_role='hitter',latest_verified_record='Campeche assignment',record_date='2026-04-16',status='LATEST_PRIMARY_TRANSACTION_NON_MLB_2027_UNVERIFIED',source='https://www.mlb.com/player/andrew-stevenson-664057',note='MLB profile also records Durham release in August 2025; no newer verified MLB contract.'),
 dict(mlbam_id='664314',name='Estevan Florial',verified_primary_role='hitter',latest_verified_record='Chihuahua announced for 2027',record_date='2026-09-23',status='ANNOUNCED_2027_MEXICAN_LEAGUE_ROSTER',source='https://lmb.com.mx/noticias/dorados-de-chihuahua-incorpora-al-canonero-estevan-florial',note='2027 non-MLB announcement; not an MLB return.'),
 dict(mlbam_id='596748',name='Maikel Franco',verified_primary_role='hitter',latest_verified_record='Licey winter assignment',record_date='2026-10-16',status='WINTER_ROSTER_VERIFIED_MLB_CLAIM_UNCONFIRMED',source='https://www.mlb.com/player/maikel-franco-596748',note='Newer secondary Royals claim not independently confirmed; do not infer a signed MLB contract.'),
 dict(mlbam_id='609274',name='Elier Hernandez',verified_primary_role='hitter',latest_verified_record='Licey winter assignment',record_date='2026-10-16',status='WINTER_ROSTER_VERIFIED_SUMMER_2027_UNVERIFIED',source='https://www.mlb.com/player/elier-hernandez-609274',note='Durango reserve-list entry August 2026; no summer MLB status inferred.'),
 dict(mlbam_id='672478',name='Jordan Diaz',verified_primary_role='hitter',latest_verified_record='Yucatan signed/released entries on same date',record_date='2026-05-09',status='PRIMARY_TRANSACTION_AMBIGUOUS_2027_UNVERIFIED',source='https://www.mlb.com/player/jordan-diaz-672478',note='Same-date conflict retained. Colombian winter move reported separately; no MLB contract established.'),
 dict(mlbam_id='658668',name='Edward Olivares',verified_primary_role='hitter',latest_verified_record='Margarita winter assignment',record_date='2026-10-13',status='WINTER_ROSTER_VERIFIED_SUMMER_2027_UNVERIFIED',source='https://www.mlb.com/player/edward-olivares-658668',note='A prior Rays minor deal does not establish current MLB status.'),
]
metadata=json.loads(Path('work/returner_official_metadata.json').read_text());metabank={r['mlbam_id']:r for r in metadata}
for r in statuses:
 a=metabank[r['mlbam_id']];profile=a.get('profile',{});transactions=a.get('latest_transactions',[])
 r.update(as_of='2026-11-24',posting_status='NO_CURRENT_MLB_POSTING_ESTABLISHED_IN_REVIEW',translation_status='UNVALIDATED_COVERAGE_ONLY',source_scope='Latest verified evidence, not certification of current summer 2027 roster',API_profile_team=profile.get('currentTeam',{}).get('name',''),API_profile_active=profile.get('active',''),API_latest_transaction=transactions[0]['description'] if transactions else '',API_latest_transaction_date=transactions[0]['date'] if transactions else '',API_source=a.get('transactions_url',''),API_warning='currentTeam can retain stale last-known affiliations; do not treat as current MLB roster membership')
save('priority_returner_status_review.csv',statuses)
(O/'official_returner_metadata_responses.json').write_text(json.dumps(metadata,indent=2))
lookup={r['mlbam_id']:r for r in statuses}
for role in ['hitter','pitcher']:
 rr=read(O/f'research_2027_{role}s.csv')
 for r in rr:
  s=lookup.get(r['mlbam_id']);r['priority_returner_review_status']=s['status'] if s else ''
  r['official_role_conflict']=bool(s and role!=s['verified_primary_role'])
  if r['official_role_conflict']:r['research_exceptions']+=';PRIMARY_ROLE_CONFLICT_REVIEW'
 save(f'research_2027_{role}s.csv',rr)
# All identities remain observational, outside the production crosswalk/config.
save('P1_international_coverage_only.csv',[dict(season=2027,player_type=r['role'],name=r['name'],PlayerId=r['PlayerId'],mlbam_id=r['mlbam_id'],canonical_key=r['canonical_key'],market_status=r['market_status'],forecast_status='UNVALIDATED_INTERNATIONAL_TRANSLATION_NO_PA_IP_OR_SKILL_FORECAST',PA='',IP='',source=r['status_source']) for r in identities])
summary=dict(P1_players=4,home_registry_identity_ties=4,corroborated_MLBAM_ties=4,MLBAM_unresolved=[],non_identifier_biographic_conflicts=['Kaima Taira batting hand: MLB R versus NPB L; not used'],priority_returners_reviewed=10,returner_current_2027_roster_certified=False,international_translation_adopted=False,production_identity_crosswalk_modified=False,as_of='2026-11-24')
(O/'identity_status_review.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
