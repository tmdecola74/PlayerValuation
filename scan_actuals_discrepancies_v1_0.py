"""Read-only targeted PA inventory from a reconciliation's frozen raw CSV versions."""
import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def flags(rows):
    events = {r.get('events', '').strip() for r in rows} - {''}
    reasons = []
    if not events:
        reasons.append('NO_RECORDED_TERMINAL_EVENT')
    if len(events) > 1:
        reasons.append('MULTIPLE_EVENT_LABELS')
    if any(any(k in e.lower() for k in ('interf', 'advisory', 'error', 'sac', 'intent', 'trunc')) for e in events):
        reasons.append('SPECIAL_EVENT_LABEL')
    if any(len({r.get(k, '') for r in rows}) > 1 for k in ('batter', 'pitcher')):
        reasons.append('PLAYER_CHANGE')
    try:
        numbers = sorted(int(r['pitch_number']) for r in rows)
        if numbers != list(range(1, max(numbers) + 1)):
            reasons.append('PITCH_SEQUENCE_GAP_OR_DUPLICATE')
    except (ValueError, KeyError):
        reasons.append('INVALID_PITCH_NUMBER')
    return reasons


def build(source, discrepancies, output, backup_root='backups', top=3):
    source, discrepancies, output = map(Path, (source, discrepancies, output))
    if output.exists():
        raise FileExistsError(f'Choose a new output folder: {output}')
    if top < 1:
        raise ValueError('top must be positive')
    input_hashes = {str(p.resolve()): sha(p) for p in (source, discrepancies)}
    targets = sorted((r for r in read_csv(discrepancies) if r['player_type'] == 'hitter' and r['metric'] == 'PA'),
                     key=lambda r: (-abs(int(r['final_difference'])), int(r['season']), r['mlbam_id']))[:top]
    if not targets:
        raise ValueError('No hitter PA discrepancies selected')
    lookup = {(int(r['season']), r['mlbam_id']): r for r in targets}
    windows = json.loads(source.read_text(encoding='utf-8-sig'))
    selected = [w for w in windows if int(w['day'][:4]) in {k[0] for k in lookup}]
    if len({w['day'] for w in selected}) != len(selected):
        raise ValueError('Duplicate frozen daily windows')
    appearances, candidates, games, hashes = [], [], {}, {}
    for n, w in enumerate(selected, 1):
        if w['status'] != 'COMPLETE':
            raise ValueError('Incomplete source window')
        p = Path(w['raw_path'])
        actual_hash = sha(p)
        if actual_hash != w['raw_hash']:
            raise ValueError(f'Frozen raw hash mismatch: {p}')
        hashes[str(p)] = actual_hash
        grouped = defaultdict(list)
        for row in read_csv(p):
            grouped[(row.get('game_pk'), row.get('at_bat_number'))].append(row)
        year = int(w['day'][:4])
        for (game, pa), rows in grouped.items():
            touched = {r.get('batter') for r in rows}
            for player in touched:
                target = lookup.get((year, player))
                if not target:
                    continue
                reasons = flags(rows)
                item = dict(season=year, mlbam_id=player, name=target['name'], game_pk=game,
                            at_bat_number=pa, source_day=w['day'], pitch_rows=len(rows),
                            events=json.dumps(sorted({r.get('events', '') for r in rows} - {''})),
                            flags=';'.join(reasons))
                appearances.append(item)
                key = (year, game)
                games.setdefault(key, set()).add(player)
                if reasons:
                    candidates.append(item)
        if n % 50 == 0:
            print(f'{n}/{len(selected)} frozen daily CSVs checked', flush=True)
    for p, digest in hashes.items():
        if sha(p) != digest:
            raise ValueError('Source changed during scan: ' + p)
    for p in (source, discrepancies):
        if sha(p) != input_hashes[str(p.resolve())]:
            raise ValueError('Report input changed during scan')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output.name + '.staging-', dir=output.parent))
    try:
        fields = ['season','mlbam_id','name','game_pk','at_bat_number','source_day','pitch_rows','events','flags']
        write_csv(stage/'target_appearances.csv', appearances, fields)
        write_csv(stage/'candidate_pas.csv', candidates, fields)
        candidate_games = {(r['season'], r['game_pk']) for r in candidates}
        plan_fields = ['season','game_pk','priority','url']
        def plan(keys):
            return [dict(season=y, game_pk=g, priority='PLAYER_SEASON_DIFFERENCE',
                         url=f'https://statsapi.mlb.com/api/v1.1/game/{g}/feed/live') for y,g in sorted(keys)]
        write_csv(stage/'candidate_game_fetch_plan.csv', plan(candidate_games), plan_fields)
        write_csv(stage/'all_target_games_fetch_plan.csv', plan(games), plan_fields)
        report = dict(version='1.0.0', targets=targets, frozen_windows_checked=len(selected),
                      recorded_pa_groups=len(appearances), candidate_pas=len(candidates),
                      candidate_games=len(candidate_games), all_target_games=len(games),
                      inputs_unchanged=True, source_manifest_sha256=input_hashes[str(source.resolve())],
                      verified_raw_sha256=hashes,
                      limitations=['Candidates are investigation leads, not explanations or count corrections.',
                                   'A PA absent from Statcast cannot be located by this scan alone; inspect game evidence.',
                                   'Player-change ownership is not re-scored here. Existing reconciliation is preserved.',
                                   'Full target-game inventory includes only games with a recorded pitch to the target.'])
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        backup = Path(backup_root).resolve()/(output.name+'_'+stamp)
        report['backup'] = str(backup)
        (stage/'scan_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        shutil.copyfile(source, stage/'source_windows.json')
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, backup)
        if {p.name:sha(p) for p in stage.iterdir()} != {p.name:sha(p) for p in backup.iterdir()}:
            raise ValueError('Backup verification failed')
        stage.rename(output)
        return {k:v for k,v in report.items() if k != 'verified_raw_sha256'}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reconciliation', default='outputs/actuals_statcast_reconciliation_v1_0_min0ip')
    p.add_argument('--output', default='outputs/actuals_targeted_scan_v1_0')
    p.add_argument('--backup-root', default='backups')
    p.add_argument('--top', type=int, default=3)
    a = p.parse_args()
    folder = Path(a.reconciliation)
    print(json.dumps(build(folder/'source_windows.json', folder/'discrepancies.csv', a.output, a.backup_root, a.top), indent=2))

if __name__ == '__main__':
    main()
