"""Repair audit-only Bot/bottom PA link classifications without a raw archive rescan."""
import argparse
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from audit_actuals_final_differences_v1_0 import (
    csv_rows, write_csv, json_out, summarize_pa, candidate_play, classify, event_vector, PA_EVENTS, NON_PA_EVENTS,
)
from actuals_final_audit_support_v1_0 import sha, now, validate_feed


def repair(source='outputs/actuals_final_difference_audit_v1_0',
           output='outputs/actuals_final_difference_audit_v1_0_1',backup_root='backups'):
    source,output,backup_root=map(lambda x:Path(x).resolve(),(source,output,backup_root))
    if output.exists():raise FileExistsError('Choose a new output folder')
    for p in (source,backup_root):
        if p==output or p in output.parents or output in p.parents:raise ValueError('Overlapping folders')
    if source==backup_root or source in backup_root.parents or backup_root in source.parents:raise ValueError('Backup overlaps source')
    files=[p for p in source.iterdir() if p.is_file()]
    if any(p.is_symlink() or p.is_dir() for p in source.iterdir()):raise ValueError('Expected flat audit output')
    fingerprints={str(p):sha(p) for p in files}
    report=json.loads((source/'audit_report.json').read_text(encoding='utf-8'))
    if report['version']!='1.0.0':raise ValueError('Fast repair expects an original 1.0.0 audit')
    old_hashes=json.loads((source/'input_hashes.json').read_text(encoding='utf-8'))
    feed_paths={int(Path(p).parent.name):(Path(p),h) for p,h in old_hashes.items() if Path(p).name=='feed.json'}
    evidence=[json.loads(line) for line in (source/'candidate_pa_evidence.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    verified={};changes={};new_evidence={};class_counts=Counter(report['classification_pa_groups'])
    for ev in evidence:
        key=(ev['season'],ev['game_pk'],ev['at_bat_number'])
        if key in new_evidence:raise ValueError('Duplicate PA evidence')
        new_evidence[key]=ev
        if ev['mlb_play'] is None:continue
        game=ev['game_pk']
        if game not in feed_paths:raise ValueError('Evidence has no frozen feed fingerprint')
        path,digest=feed_paths[game]
        if game not in verified:
            if sha(path)!=digest:raise ValueError('Cached feed changed since original audit')
            fingerprints[str(path)]=digest
            payload=validate_feed(json.loads(path.read_text(encoding='utf-8')),game,ev['season'])
            meta_path=path.with_name('source.json')
            if str(meta_path) not in old_hashes or sha(meta_path)!=old_hashes[str(meta_path)]:raise ValueError('Cached metadata changed')
            fingerprints[str(meta_path)]=old_hashes[str(meta_path)]
            verified[game]=payload
        pa=summarize_pa(ev['statcast_sequence'])
        play,failures=candidate_play(verified[game],pa)
        if play!=ev['mlb_play']:raise ValueError('Saved PA evidence differs from verified cached play')
        # This repair may remove only the half-inning false negative.
        old=set(ev['link_failures']);new=set(failures)
        if new-old or old-new-{'HALF_INNING_MISMATCH'}:raise ValueError('Unexpected link-check change')
        classification=classify(pa,play,failures)
        if failures!=ev['link_failures'] or classification!=ev['classification']:
            class_counts[ev['classification']]-=1;class_counts[classification]+=1
            changes[key]=(pa,play,failures,classification)
        ev['link_failures']=failures;ev['classification']=classification
    inventory=list(csv_rows(source/'pa_inventory.csv'))
    updated=0
    for row in inventory:
        key=tuple(int(row[k]) for k in ('season','game_pk','at_bat_number'))
        if key not in changes:continue
        pa,play,failures,classification=changes[key]
        row['link_failures']=';'.join(failures);row['classification']=classification
        event=play.get('result',{}).get('eventType','')
        value=event_vector(event,row['player_type']).get(row['metric'],0) if not failures and event in PA_EVENTS|NON_PA_EVENTS else None
        row['mlb_pa_contribution']='' if value is None else str(value)
        row['mlb_minus_rule_pa']='' if value is None else str(value-int(row['statcast_rule_pa_contribution']))
        updated+=1
    unknown={(int(r['season']),int(r['game_pk']),int(r['at_bat_number'])) for r in csv_rows(source/'unknown_outcome_reviews.csv')}
    def is_lead(r):
        key=tuple(int(r[k]) for k in ('season','game_pk','at_bat_number'))
        return key in unknown or bool(r['paired_leads']) or r['mlb_minus_rule_pa'] not in ('','0') or (r['classification']!='CACHE_MISSING' and bool(r['link_failures']))
    leads=[r for r in inventory if is_lead(r)]
    lead_keys={tuple(int(r[k]) for k in ('season','game_pk','at_bat_number')) for r in leads}
    cases=list(csv_rows(source/'remaining_cases.csv'));counts=Counter((r['season'],r['player_type'],r['mlbam_id'],r['metric']) for r in leads)
    for row in cases:row['candidate_pa_rows']=counts[tuple(row[k] for k in ('season','player_type','mlbam_id','metric'))]
    if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Input changed during repair')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
    try:
        for p in files:shutil.copyfile(p,stage/p.name)
        shutil.copyfile(source/'audit_report.json',stage/'repair_prior_audit_report.json')
        for name,rows in [('pa_inventory.csv',inventory),('candidate_pa_reviews.csv',leads),('remaining_cases.csv',cases)]:
            write_csv(stage/name,rows,list(rows[0]) if rows else ['season','game_pk','at_bat_number'])
        kept=[ev for key,ev in new_evidence.items() if key in lead_keys]
        with (stage/'candidate_pa_evidence.jsonl').open('w',encoding='utf-8') as f:
            for ev in kept:f.write(json.dumps(ev)+'\n')
        backup=backup_root/(output.name+'_'+now().replace(':','').replace('-','').replace('.','_').replace('+','_'))
        report.update(version='1.0.1',built_at=now(),report_repair_only=True,
                      source_audit=str(source),source_audit_unchanged=True,raw_archive_rescanned=False,
                      half_inning_links_reclassified=len(changes),pa_metric_rows_reclassified=updated,
                      classification_pa_groups={k:v for k,v in class_counts.items() if v},
                      candidate_review_rows=len(leads),candidate_evidence_pa_groups=len(kept),
                      output=str(output),backup=str(backup),counts_modified=False)
        json_out(stage/'audit_report.json',report)
        json_out(stage/'repair_provenance.json',dict(input_sha256=fingerprints,
                 repair_code_sha256=sha(__file__),link_code_sha256=sha(Path(__file__).with_name('audit_actuals_final_differences_v1_0.py')),
                 raw_integrity_basis='Inherited from preserved original audit; raw files not rescanned during link-only repair'))
        (stage/'audit_report.md').write_text('# Audit link repair 1.0.1\n\nBot/bottom normalized; all other link checks retained.\n\n'
            f'{len(changes)} PA links reclassified; {len(leads)} candidate metric review rows remain.\n\n'
            'Baseline counts and game totals are unchanged. Original audit is preserved. Raw files were not rescanned.\n',encoding='utf-8')
        # Verify the full copy for every file not intentionally changed.
        changed={'audit_report.json','audit_report.md','pa_inventory.csv','candidate_pa_reviews.csv','remaining_cases.csv','candidate_pa_evidence.jsonl'}
        for p in files:
            if p.name not in changed and sha(stage/p.name)!=fingerprints[str(p)]:raise ValueError('Preserved output copy mismatch')
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
        if {p.name:sha(p) for p in stage.iterdir()}!={p.name:sha(p) for p in backup.iterdir()}:raise ValueError('Backup verification failed')
        if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Input changed during repair')
        if output.exists():raise FileExistsError('Output created during repair')
        stage.rename(output)
        return report
    finally:
        if stage.exists():shutil.rmtree(stage)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default='outputs/actuals_final_difference_audit_v1_0')
    p.add_argument('--output',default='outputs/actuals_final_difference_audit_v1_0_1')
    p.add_argument('--backup-root',default='backups')
    a=p.parse_args();print(json.dumps(repair(a.source,a.output,a.backup_root),indent=2))

if __name__=='__main__':main()
