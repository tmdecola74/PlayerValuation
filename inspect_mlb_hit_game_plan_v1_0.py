"""Inspect only games selected by the hit game-log audit; retain hashed MLB evidence."""
import argparse,json,shutil,tempfile
from pathlib import Path
from audit_mlb_hit_gamelogs_v1_0 import fetch,sha,dump,now,read_csv

def inspect(audit,output):
    audit=Path(audit).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    rows=read_csv(audit/'mismatched_games.csv');plan=read_csv(audit/'game_fetch_plan.csv')
    stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
    try:
        findings=[]
        for game in plan:
            pk=int(game['game_pk']);raw=stage/f'{pk}.json';raw.write_bytes(fetch(game['url']));data=json.loads(raw.read_bytes())
            if data.get('gamePk')!=pk or data['gameData']['game']['type']!='R':raise ValueError('Wrong game/type')
            dump(stage/f'{pk}.source.json',dict(url=game['url'],retrieved_at=now(),sha256=sha(raw)))
            box=data['liveData']['boxscore'];plays=data['liveData']['plays']['allPlays']
            for pid in sorted({int(r['mlbam_id']) for r in rows if int(r['game_pk'])==pk}):
                teams=[(side,t) for side,t in box['teams'].items() if 'ID'+str(pid) in t['players']]
                if len(teams)!=1:raise ValueError('Ambiguous player boxscore')
                side,team=teams[0];player=team['players']['ID'+str(pid)];bat=player['stats'].get('batting',{})
                teamH=team['teamStats']['batting']['hits'];sumH=sum(p['stats'].get('batting',{}).get('hits',0) for p in team['players'].values())
                if teamH!=sumH:raise ValueError('Team/player hit sum mismatch')
                batterplays=[p for p in plays if p.get('matchup',{}).get('batter',{}).get('id')==pid]
                findings.append(dict(game_pk=pk,date=data['gameData']['datetime']['officialDate'],mlbam_id=pid,name=player['person']['fullName'],side=side,positions=player.get('allPositions',[]),game_status=player.get('gameStatus'),batting=bat,matched_batter_plays=[dict(atBatIndex=p['about']['atBatIndex'],result=p['result']) for p in batterplays],player_hit_sum_matches_team=True,interpretation='ZERO_HIT_NO_RECORDED_BATTER_PLAY' if bat.get('hits')==0 and not batterplays else 'REVIEW_REQUIRED'))
        dump(stage/'game_inspections.json',findings)
        dump(stage/'inspection_report.json',dict(built_at=now(),games=len(plan),player_games=len(findings),counts_modified=False,limitations=['Current MLB feed, not dated scoring revision evidence.','Absent reconstructed games remain absent; zero-hit MLB appearances are not inserted into physical Statcast.']))
        stage.rename(output)
        return findings
    finally:
        if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(inspect(a.audit,a.output),indent=2))
