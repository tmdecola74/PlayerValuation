"""Offline, read-only game/PA audit of remaining supported actuals differences.
Uses frozen raw versions and a separate validated MLB evidence layer. Never repairs counts.
"""
from __future__ import annotations
import argparse
import hashlib
import csv
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from actuals_final_audit_support_v1_0 import (
    sha, now, integer, credit_pa, event_vector, PA_EVENTS, NON_PA_EVENTS,
    SUPPORTED, validate_feed, boxscore_counts,
)

VERSION = '1.0.1'
DEFAULT_RECONCILIATION = 'outputs/actuals_statcast_reconciliation_v1_0_remaining_pa_evidence'
KEY = ('season', 'player_type', 'mlbam_id', 'metric')


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f'Empty or duplicate CSV headings: {path}')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'Malformed CSV row: {path}')
            yield row


def write_csv(path, rows, fields):
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def json_out(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def case_key(row):
    return (int(row['season']), row['player_type'], integer(row['mlbam_id'], 'mlbam_id'), row['metric'])


def parse_pitch(row, year):
    p = {k: row.get(k, "") for k in ("game_pk", "at_bat_number", "pitch_number", "batter", "pitcher", "balls", "strikes", "events", "game_date", "game_type", "inning", "inning_topbot", "description")}
    for col in ('game_pk', 'at_bat_number', 'pitch_number', 'batter', 'pitcher'):
        p[col] = integer(row[col], col)
        if p[col] <= 0:
            raise ValueError('Nonpositive pitch identifier')
    if row.get('game_type') != 'R' or not row.get('game_date', '').startswith(str(year) + '-'):
        raise ValueError('Wrong pitch season or game type')
    for col in ('balls', 'strikes'):
        try:
            p[col] = integer(row[col], col)
        except (ValueError, KeyError):
            p[col] = None
    p['events'] = row.get('events', '').strip()
    return p


def summarize_pa(rows):
    rows = sorted(rows, key=lambda r: r['pitch_number'])
    terminals = [r for r in rows if r['events'] in PA_EVENTS]
    valid = len(terminals) == 1 and terminals[0] is rows[-1]
    decision = credit_pa(rows) if valid else {'status': 'NO_VALID_TERMINAL', 'owners': {}, 'unresolved_roles': []}
    terminal = terminals[0] if valid else None
    return {'rows': rows, 'terminal': terminal, 'decision': decision,
            'event': terminal['events'] if terminal else '',
            'labels': sorted({r['events'] for r in rows} - {''}),
            'unknown': sorted({r['events'] for r in rows} - PA_EVENTS - NON_PA_EVENTS - {''})}


def normalize_half(value):
    value = str(value).strip().lower()
    return {'bot': 'bottom', 'bottom': 'bottom', 'top': 'top'}.get(value, value)


def candidate_play(payload, pa):
    """Index nominates only. Both IDs and every pre-pitch count must also agree."""
    rows = pa['rows']
    candidates = [p for p in payload.get('liveData', {}).get('plays', {}).get('allPlays', [])
                  if p.get('about', {}).get('atBatIndex', p.get('atBatIndex', -2)) + 1 == rows[0]['at_bat_number']]
    if len(candidates) != 1:
        return None, ['NO_UNIQUE_INDEX_CANDIDATE']
    play = candidates[0]
    failures = []
    matchup = play.get('matchup', {})
    for col in ('batter', 'pitcher'):
        # Strict single-owner proof; changed PAs remain review cases here.
        ids = {r[col] for r in rows}
        if len(ids) != 1 or matchup.get(col, {}).get('id') not in ids:
            failures.append(col.upper() + '_IDENTITY_NOT_PROVEN')
    pitches = [e for e in play.get('playEvents', []) if e.get('isPitch')]
    if len(pitches) != len(rows):
        failures.append('PITCH_COUNT_MISMATCH')
    else:
        previous = (0, 0)
        for row, pitch in zip(rows, pitches):
            if row['pitch_number'] != pitch.get('pitchNumber'):
                failures.append('PITCH_NUMBER_MISMATCH')
            if (row.get('balls'), row.get('strikes')) != previous:
                failures.append('PRE_PITCH_COUNT_MISMATCH')
            c = pitch.get('count', {})
            previous = (c.get('balls'), c.get('strikes'))
    raw_inning = rows[0].get('inning')
    if raw_inning not in (None, '') and int(float(raw_inning)) != play.get('about', {}).get('inning'):
        failures.append('INNING_MISMATCH')
    half = normalize_half(rows[0].get('inning_topbot', ''))
    if half and half != normalize_half(play.get('about', {}).get('halfInning', '')):
        failures.append('HALF_INNING_MISMATCH')
    if not play.get('about', {}).get('isComplete'):
        failures.append('MLB_PLAY_INCOMPLETE')
    return play, sorted(set(failures))


def classify(pa, play, failures):
    if play is None:
        return 'NO_UNIQUE_PLAY_LINK'
    if failures:
        return 'PLAY_LINK_REVIEW_REQUIRED'
    if not pa['terminal'] and any(r['events'] in PA_EVENTS for r in pa['rows']):
        return 'INVALID_STATCAST_TERMINAL_SEQUENCE_REVIEW'
    event = play.get('result', {}).get('eventType', '')
    if event not in PA_EVENTS | NON_PA_EVENTS:
        return 'UNKNOWN_MLB_OUTCOME_REVIEW'
    old = pa['event']
    if old and event in NON_PA_EVENTS:
        return 'ALIGNED_EXTRA_RECONSTRUCTED_OUTCOME'
    if not old and event in PA_EVENTS:
        return 'ALIGNED_MISSING_TERMINAL_OUTCOME'
    if old and old != event:
        if (old in {'single','double','triple','home_run','field_error'} or
                event in {'single','double','triple','home_run','field_error'}):
            return 'ALIGNED_HIT_OR_ERROR_CLASSIFICATION_DIFFERENCE'
        return 'ALIGNED_OUTCOME_LABEL_DIFFERENCE'
    if pa['unknown']:
        return 'UNKNOWN_STATCAST_OUTCOME_REVIEW'
    return 'ALIGNED_OUTCOME_AGREES' if old else 'ALIGNED_NON_PA_NO_COMPLETED_COUNT'


def game_plan(keys):
    return [dict(season=y, game_pk=g, priority='PLAYER_SEASON_DIFFERENCE',
                 url=f'https://statsapi.mlb.com/api/v1.1/game/{g}/feed/live') for y,g in sorted(keys)]


def audit(reconciliation=DEFAULT_RECONCILIATION, cache='data/mlb_scoring_evidence_v1_0',
          output='outputs/actuals_final_difference_audit_v1_0', backup_root='backups'):
    folder, cache, output, backup_root = map(lambda p: Path(p).resolve(), (reconciliation, cache, output, backup_root))
    if output.exists():
        raise FileExistsError('Choose a new output folder: ' + str(output))
    if output == backup_root or output in backup_root.parents or backup_root in output.parents:
        raise ValueError('Output and backup folders overlap')
    for protected in (folder, cache):
        if output == protected or output in protected.parents or protected in output.parents:
            raise ValueError('Output overlaps an input folder')
        if backup_root == protected or backup_root in protected.parents or protected in backup_root.parents:
            raise ValueError('Backup root overlaps an input folder')
    fingerprints = {}
    def remember(path):
        path = Path(path)
        digest = sha(path)
        previous = fingerprints.setdefault(str(path), digest)
        if digest != previous:
            raise ValueError('Input changed during audit: ' + str(path))
        return digest
    for name in ('source_windows.json', 'discrepancies.csv', 'reconciliation_report.json'):
        remember(folder/name)
    remember(Path(__file__))
    remember(Path(__file__).with_name('actuals_final_audit_support_v1_0.py'))
    baseline_report = json.loads((folder/'reconciliation_report.json').read_text(encoding='utf-8-sig'))
    windows = json.loads((folder/'source_windows.json').read_text(encoding='utf-8-sig'))
    cases = list(csv_rows(folder/'discrepancies.csv'))
    if not cases:
        raise ValueError('No discrepancy rows to audit')
    targets = {}
    case_map = {}
    for row in cases:
        key = case_key(row)
        if key in case_map or key[1] not in SUPPORTED or key[3] not in SUPPORTED[key[1]]:
            raise ValueError('Duplicate or unsupported discrepancy key: ' + str(key))
        if key[0] >= 2026 or key[0] not in baseline_report['seasons']:
            raise ValueError('Target holdout/future season or season outside baseline')
        if row['status'] != 'UNRESOLVED_DIFFERENCE':
            raise ValueError('Only numerical unresolved differences are supported')
        if int(row['evidence_count']) - int(row['fangraphs_actual']) != int(row['final_difference']):
            raise ValueError('Inconsistent baseline discrepancy arithmetic')
        case_map[key] = row
        targets.setdefault(key[:3], set()).add(key[3])
    years = sorted({k[0] for k in targets})
    selected = [w for w in windows if int(w['day'][:4]) in years]
    if len({w['day'] for w in selected}) != len(selected):
        raise ValueError('Duplicate source window day')
    if any(not any(int(w['day'][:4]) == y for w in selected) for y in years):
        raise ValueError('Target season missing from source manifest')
    # Retain complete PA sequences only when a target player appears in that role.
    groups = defaultdict(dict)
    observed_games = defaultdict(set)
    physical = defaultdict(set)
    source_counts = Counter()
    print(f'Scanning {len(selected)} frozen daily CSVs for {len(targets)} target player-season roles...', flush=True)
    for n, w in enumerate(selected, 1):
        if w['status'] != 'COMPLETE':
            raise ValueError('Incomplete frozen window')
        raw = Path(w['raw_path'])
        if remember(raw) != w['raw_hash']:
            raise ValueError('Frozen raw SHA256 mismatch: ' + str(raw))
        year = int(w['day'][:4])
        daily = defaultdict(list)
        count = 0
        for row in csv_rows(raw):
            p = parse_pitch(row, year)
            count += 1
            observed_games[year].add(p['game_pk'])
            daily[p['game_pk'], p['at_bat_number']].append((p, row))
        source_counts[year] += count
        if count != int(w.get('source_rows', w['rows'])):
            raise ValueError('Frozen raw row count mismatch: ' + str(raw))
        for (game, number), rows in daily.items():
            if not any((year, role, p[col]) in targets for p,_ in rows
                       for role,col in [('hitter','batter'),('pitcher','pitcher')]):
                continue
            group = groups[year, game, number]
            for p, raw_row in rows:
                signature = hashlib.sha256(json.dumps(raw_row, sort_keys=True).encode()).hexdigest()
                pitch = p['pitch_number']
                if pitch in group and group[pitch][1] != signature:
                    raise ValueError('Conflicting duplicate targeted pitch key')
                group[pitch] = (p, signature)  # only byte-equivalent field duplicates collapse
        if n % 100 == 0:
            print(f'{n}/{len(selected)} frozen daily files verified', flush=True)
    raw_counts, rule_counts = Counter(), Counter()
    pas = {}
    affected_by_pa = {}
    for (year, game, number), pitched in sorted(groups.items()):
        pa = summarize_pa([p for p,_ in pitched.values()])
        pas[year,game,number] = pa
        affected = set()
        for role,col in [('hitter','batter'),('pitcher','pitcher')]:
            for p in pa['rows']:
                key = (year,role,p[col])
                if key in targets:
                    physical[key].add(game)
                    affected.add(key)
            if pa['terminal']:
                terminal = pa['terminal'][col]
                owner = pa['decision'].get('owners', {}).get(role, terminal)
                if role in pa['decision'].get('unresolved_roles', []):
                    owner = terminal  # exactly the existing reconciliation's withheld-move behavior
                for metric,value in event_vector(pa['event'],role).items():
                    if (year,role,terminal) in targets:
                        raw_counts[year,game,role,terminal,metric] += value
                    if (year,role,owner) in targets:
                        rule_counts[year,game,role,owner,metric] += value
        affected_by_pa[year,game,number] = affected
    # Cache inventory is fixed for the run. Reading evidence never refreshes it.
    if (cache/'download.lock').exists():
        raise ValueError('Evidence downloader is running; finish it before this audit')
    cache_inventory = sorted(str(p.relative_to(cache)) for p in cache.glob('*/source.json')) if cache.exists() else []
    feeds = {}
    feed_boxes = {}
    feed_notes = []
    for relative in cache_inventory:
        meta_path = cache/relative
        remember(meta_path)
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        game, year = integer(meta['game_pk'],'game_pk'), integer(meta['season'],'season')
        if year not in years or game not in observed_games[year]:
            continue
        if meta_path.parent.name != str(game):
            raise ValueError('Cache folder/game identity mismatch')
        path = meta_path.with_name('feed.json')
        if remember(path) != meta['sha256']:
            raise ValueError('MLB cached feed SHA256 mismatch')
        payload = validate_feed(json.loads(path.read_text(encoding='utf-8')),game,year)
        if (year,game) in feeds:
            raise ValueError('Duplicate cache game')
        feeds[year,game] = payload
        box, blocks, notes = boxscore_counts(payload)
        feed_boxes[year,game] = (box,blocks)
        feed_notes.extend(dict(season=year,game_pk=game,**note) for note in notes)
    evidence_counts = rule_counts.copy()
    game_rows = []
    for target, metrics in sorted(targets.items()):
        year,role,pid = target
        games = set(physical[target])
        for (y,g),(box,blocks) in feed_boxes.items():
            if y == year and any((role,pid,m) in box for m in metrics):
                games.add(g)
        for game in sorted(games):
            cached = (year,game) in feeds
            box,blocks = feed_boxes.get((year,game), ({},set()))
            for metric in sorted(metrics):
                key = (year,game,role,pid,metric)
                admitted = (role,metric) in blocks
                mlb = box.get((role,pid,metric),0) if admitted else None
                if admitted:
                    evidence_counts[key] = mlb
                game_rows.append(dict(season=year,player_type=role,mlbam_id=pid,
                                      name=case_map[year,role,pid,metric]['name'],metric=metric,game_pk=game,
                                      terminal_count=raw_counts[key],rule_count=rule_counts[key],
                                      cached_mlb=cached,metric_admitted=admitted,mlb_count=mlb,
                                      mlb_minus_rule=mlb-rule_counts[key] if admitted else None))
    pa_rows, leads, unknowns, candidate_evidence, unmatched_plays = [], [], [], [], []
    primary = set()
    suspect_counts = Counter()
    for (year,game,number),pa in sorted(pas.items()):
        affected = affected_by_pa[year,game,number]
        payload = feeds.get((year,game))
        play, failures = candidate_play(payload,pa) if payload else (None,['CACHE_MISSING'])
        classification = classify(pa,play,failures) if payload else 'CACHE_MISSING'
        mlb_event = play.get('result',{}).get('eventType','') if play else ''
        before_leads = len(leads)
        old_event = pa['event']
        # Complementary season residuals nominate PAs; they never establish a scoring change.
        pairs = []
        if pa['terminal']:
            p = pa['terminal']
            for hm,pm in [('H','H'),('PA','TBF')]:
                hk,pk = (year,'hitter',p['batter'],hm),(year,'pitcher',p['pitcher'],pm)
                if hk in case_map and pk in case_map and int(case_map[hk]['final_difference']) == int(case_map[pk]['final_difference']):
                    if hm == 'H' and (old_event in {'single','double','triple','home_run','field_error'}):
                        pairs.append('COMPLEMENTARY_HIT_RESIDUALS_SAME_SIGN')
                    elif hm == 'PA':
                        pairs.append('COMPLEMENTARY_PA_TBF_RESIDUALS_SAME_SIGN')
        unknown = bool(pa['unknown']) or (play and mlb_event not in PA_EVENTS|NON_PA_EVENTS)
        if pairs and not payload:
            primary.add((year,game))
        if unknown:
            unknowns.append(dict(season=year,game_pk=game,at_bat_number=number,
                                 statcast_labels=json.dumps(pa['labels']),mlb_event=mlb_event,
                                 status='UNRESOLVED_UNKNOWN_OUTCOME_NO_COUNT_OVERRIDE'))
            if not payload:
                primary.add((year,game))
        # Write all target PA associations, including quiet matches, for reproducible review.
        for target in sorted(affected):
            _,role,pid = target
            col = 'batter' if role=='hitter' else 'pitcher'
            for metric in sorted(targets[target]):
                row_case = case_map[year,role,pid,metric]
                old_vector = event_vector(old_event,role)
                local = old_vector.get(metric,0) if pa['terminal'] and pa['decision'].get('owners',{}).get(role,pa['terminal'][col]) == pid else 0
                matched = play is not None and not failures
                recognized = matched and mlb_event in PA_EVENTS|NON_PA_EVENTS
                mv = event_vector(mlb_event,role).get(metric,0) if recognized else None
                delta = mv-local if mv is not None else None
                admitted = (role,metric) in feed_boxes.get((year,game),({},set()))[1]
                rec = dict(season=year,player_type=role,mlbam_id=pid,name=row_case['name'],metric=metric,
                           game_pk=game,at_bat_number=number,statcast_event=old_event,
                           statcast_labels=json.dumps(pa['labels']),mlb_event=mlb_event,
                           classification=classification,link_failures=';'.join(failures),
                           statcast_batter_ids=json.dumps(sorted({r['batter'] for r in pa['rows']})),
                           statcast_pitcher_ids=json.dumps(sorted({r['pitcher'] for r in pa['rows']})),
                           mlb_batter_id=play.get('matchup',{}).get('batter',{}).get('id') if play else None,
                           mlb_pitcher_id=play.get('matchup',{}).get('pitcher',{}).get('id') if play else None,
                           metric_admitted=admitted,statcast_rule_pa_contribution=local,
                           mlb_pa_contribution=mv,mlb_minus_rule_pa=delta,
                           season_final_difference=row_case['final_difference'],
                           paired_leads=';'.join(pairs),
                           description=play.get('result',{}).get('description','') if play else '')
                pa_rows.append(rec)
                if unknown or pairs or (delta is not None and delta != 0) or (payload and failures):
                    leads.append(rec)
                    suspect_counts[year,role,pid,metric] += 1
        if len(leads) > before_leads:
            candidate_evidence.append(dict(season=year,game_pk=game,at_bat_number=number,
                                           classification=classification,link_failures=failures,
                                           statcast_sequence=pa['rows'],mlb_play=play))
    # Retain MLB plays involving targets that have no nominated raw PA group.
    # These cannot be linked or counted from an index alone.
    for (year,game),payload in sorted(feeds.items()):
        for play in payload.get('liveData',{}).get('plays',{}).get('allPlays',[]):
            about=play.get('about',{});index=about.get('atBatIndex',play.get('atBatIndex'))
            if not isinstance(index,int) or (year,game,index+1) in pas:
                continue
            involved=[]
            for role,col in [('hitter','batter'),('pitcher','pitcher')]:
                pid=play.get('matchup',{}).get(col,{}).get('id')
                if (year,role,pid) in targets:
                    involved.append(dict(player_type=role,mlbam_id=pid))
            if involved:
                unmatched_plays.append(dict(season=year,game_pk=game,candidate_at_bat_number=index+1,
                                            status='MLB_ONLY_INDEX_CANDIDATE_NO_RAW_LINK',targets=involved,mlb_play=play))
    # Bridge precisely to baseline terminal/rule/final totals. Never silently replace baseline.
    season_rows = []
    alignment_issues = []
    for key,row in sorted(case_map.items()):
        year,role,pid,metric = key
        def total(counter):
            return sum(v for (y,g,r,p,m),v in counter.items() if (y,r,p,m)==key)
        raw, rule, evidence = total(raw_counts),total(rule_counts),total(evidence_counts)
        expected = tuple(int(row[c]) for c in ('terminal_count','rule_count','evidence_count'))
        agrees = (raw,rule,evidence) == expected
        if not agrees:
            alignment_issues.append(dict(key=list(key),baseline=expected,audit=(raw,rule,evidence)))
        missing_games = [g for g in physical[year,role,pid] if (year,g) not in feeds]
        season_rows.append(dict(**{c:row[c] for c in KEY},name=row['name'],fangraphs_actual=row['fangraphs_actual'],
                                baseline_terminal=expected[0],baseline_rule=expected[1],baseline_evidence=expected[2],
                                audit_terminal=raw,audit_rule=rule,audit_current_cache_evidence=evidence,
                                baseline_final_difference=row['final_difference'],
                                audit_current_cache_difference=evidence-int(row['fangraphs_actual']),
                                baseline_reproduced=agrees,uncached_observed_games=len(missing_games),
                                candidate_pa_rows=suspect_counts[key],
                                status='BASELINE_REPRODUCED_REVIEW_ONLY' if agrees else 'BASELINE_BRIDGE_MISMATCH_REVIEW_REQUIRED'))
    all_missing = {(y,g) for (y,role,pid) in targets for g in physical[y,role,pid] if (y,g) not in feeds}
    # Check all files actually read, plus detect a cache download occurring mid-run.
    if any(sha(p)!=digest for p,digest in fingerprints.items()):
        raise ValueError('A source changed during audit; no output published')
    if (cache/'download.lock').exists() or cache_inventory != sorted(str(p.relative_to(cache)) for p in cache.glob('*/source.json')):
        raise ValueError('Cache inventory changed during audit')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
    backup = None
    try:
        def emit(name,rows,empty_fields):
            write_csv(stage/name,rows,list(rows[0]) if rows else empty_fields)
        emit('remaining_cases.csv',season_rows,list(KEY))
        emit('game_metric_comparisons.csv',game_rows,list(KEY)+['game_pk'])
        emit('pa_inventory.csv',pa_rows,list(KEY)+['game_pk','at_bat_number'])
        emit('candidate_pa_reviews.csv',leads,list(KEY)+['game_pk','at_bat_number'])
        emit('unknown_outcome_reviews.csv',unknowns,['season','game_pk','at_bat_number','status'])
        emit('mlb_rejected_metric_blocks.csv',feed_notes,['season','game_pk','player_type','metric','status'])
        for name,items in [('candidate_pa_evidence.jsonl',candidate_evidence),('unmatched_mlb_plays.jsonl',unmatched_plays)]:
            with (stage/name).open('w',encoding='utf-8') as f:
                for item in items:
                    f.write(json.dumps(item,allow_nan=False)+'\n')
        plan_fields = ['season','game_pk','priority','url']
        write_csv(stage/'primary_game_fetch_plan.csv',game_plan(primary),plan_fields)
        write_csv(stage/'fallback_observed_games_fetch_plan.csv',game_plan(all_missing-primary),plan_fields)
        shutil.copyfile(folder/'discrepancies.csv',stage/'baseline_discrepancies.csv')
        shutil.copyfile(folder/'source_windows.json',stage/'source_windows.json')
        json_out(stage/'input_hashes.json',fingerprints)
        backup = backup_root/(output.name+'_'+now().replace(':','').replace('-','').replace('.','_').replace('+','_'))
        report = dict(version=VERSION,built_at=now(),status='AUDIT_REVIEW_REQUIRED',model_ready=False,
                      discrepancy_metric_rows=len(cases),target_player_season_roles=len(targets),
                      frozen_windows_checked=len(selected),target_pa_groups=len(pas),
                      cached_games_used=len(feeds),baseline_reproduced=not alignment_issues,
                      baseline_bridge_issues=alignment_issues,classification_pa_groups=dict(Counter(
                          (classify(pa,*candidate_play(feeds[y,g],pa)) if (y,g) in feeds else 'CACHE_MISSING')
                          for (y,g,n),pa in pas.items())),
                      candidate_review_rows=len(leads),candidate_evidence_pa_groups=len(candidate_evidence),
                      unmatched_mlb_target_plays=len(unmatched_plays),unknown_outcome_pa_groups=len(unknowns),
                      primary_uncached_games=len(primary),fallback_uncached_observed_games=len(all_missing-primary),
                      inputs_unchanged=True,counts_modified=False,output=str(output),backup=str(backup),
                      limitations=[
                          'Source outcome disagreement is not proof of a historical scoring revision; dated archived scoring evidence is required.',
                          'PA index alone never proves alignment; both players and the entire pitch/count sequence are checked.',
                          'Changed players, pitch gaps, unknown outcomes and failed links remain review cases.',
                          'Season residual pairings are leads only, never used to select a corrected outcome.',
                          'Cached boxscore replacements require both team/player metric sums to agree.',
                          'No new event classification or source count is published; baseline reports are preserved.',
                          'Observed-game plans can miss a game/appearance wholly absent from Statcast.',
                          'No IP/ER season certification, historical measurement approval or model approval is issued.',
                          'If cache contents differ from baseline, bridge mismatch remains explicit; no claim of reproducing old totals.'])
        json_out(stage/'audit_report.json',report)
        (stage/'audit_report.md').write_text(
            '# Final actuals difference audit\n\n'
            f"{len(cases)} baseline metric differences; {len(targets)} player-season roles.\n\n"
            f"Baseline reproduced: {not alignment_issues}. Counts modified: False.\n\n"
            f"Primary uncached game leads: {len(primary)}. Fallback observed games: {len(all_missing-primary)}.\n\n"
            'Read remaining_cases.csv first, then game_metric_comparisons.csv and candidate_pa_reviews.csv. '
            'PA index matching alone is insufficient. Aligned source disagreements do not certify when a scoring revision happened. '
            'Do not automatically download the fallback plan or edit actuals to force agreement.\n',encoding='utf-8')
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(stage,backup)
        if {p.name:sha(p) for p in stage.iterdir()} != {p.name:sha(p) for p in backup.iterdir()}:
            raise ValueError('Complete backup hash verification failed')
        if output.exists():
            raise FileExistsError('Output created by another process')
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reconciliation',default=DEFAULT_RECONCILIATION)
    p.add_argument('--mlb-feed-cache',default='data/mlb_scoring_evidence_v1_0')
    p.add_argument('--output',default='outputs/actuals_final_difference_audit_v1_0')
    p.add_argument('--backup-root',default='backups')
    a = p.parse_args()
    print(json.dumps(audit(a.reconciliation,a.mlb_feed_cache,a.output,a.backup_root),indent=2))

if __name__ == '__main__':
    main()
