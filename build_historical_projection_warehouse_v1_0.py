"""Stage 1B: lossless ingestion, conservative identities, and auditable matching."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def normalize_name(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]", "", value.encode("ascii", "ignore").decode().lower())


def clean_id(value):
    s = str(value or "").strip()
    if s.lower() in {"", "nan", "none", "null", "n/a", "0", "-1"}:
        return ""
    return re.sub(r"\.0+$", "", s)


def numbered_headers(headers):
    counts = Counter()
    result = []
    for column, value in enumerate(headers, 1):
        name = str(value or f"unnamed_{column}").strip()
        counts[name] += 1
        result.append(name if counts[name] == 1 else f"{name}__{counts[name]}")
    if len(set(result)) != len(result):
        raise ValueError("Header suffix collision; configure an explicit unique header list")
    return result


def read_rows(path, spec):
    if path.suffix.lower() == ".xlsx":
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = book[spec["sheet"]] if spec.get("sheet") else book.active
            iterator = iter(sheet.values)
            headers = numbered_headers(next(iterator))
            rows = []
            for line, cells in enumerate(iterator, 2):
                if len(cells) != len(headers):
                    raise ValueError(f"{path}:{line}: row width differs from header")
                rows.append((line, {k: "" if v is None else str(v) for k, v in zip(headers, cells)}))
            return headers, rows
        finally:
            book.close()
    with path.open(encoding=spec.get("encoding", "utf-8-sig"), newline="") as stream:
        reader = csv.reader(stream)
        headers = numbered_headers(next(reader))
        rows = []
        for line, cells in enumerate(reader, 2):
            if len(cells) != len(headers):
                raise ValueError(f"{path}:{line}: {len(cells)} cells for {len(headers)} headers")
            rows.append((line, dict(zip(headers, cells))))
        return headers, rows


def export_csv(path, rows, fields=None):
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or ["status"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


class Identities:
    """Only unambiguous ID edges are merged; conflicting components are isolated."""
    def __init__(self, rows, overrides, alias_policy=None, reviewed_aliases=None):
        self.parent = {}
        self.conflicts = []
        self.aliases = []
        key_names = defaultdict(set)
        edges = []
        for row in rows:
            keys = row["id_keys"]
            for key in keys:
                self.parent.setdefault(key, key)
                if row['name']:
                    key_names[key].add(normalize_name(row['name']))
            edges.extend((keys[0], k) for k in keys[1:])
        for edge in overrides:
            a = (edge["from_namespace"], clean_id(edge["from_id"]))
            b = (edge["to_namespace"], clean_id(edge["to_id"]))
            if not a[1] or not b[1]:
                raise ValueError("Override IDs must be populated")
            self.parent.setdefault(a, a)
            self.parent.setdefault(b, b)
            edges.append((a, b))
        for a, b in edges:
            ra, rb = self.find(a), self.find(b)
            if ra != rb:
                self.parent[max(ra, rb)] = min(ra, rb)
        groups = defaultdict(list)
        for key in self.parent:
            groups[self.find(key)].append(key)
        self.key_player = {}
        self.bad_keys = set()
        for keys in groups.values():
            reviewed = next((entry for entry in (reviewed_aliases or [])
                             if entry.get('verified_by') and entry.get('reason')
                             and set(map(tuple, entry['ids'])) == set(keys)), None)
            ns = defaultdict(set)
            for namespace, identifier in keys:
                ns[namespace].add(identifier)
            bad = False
            for namespace, ids in ns.items():
                if len(ids) <= 1:
                    continue
                policy = (alias_policy or {}).get(namespace)
                names = {name for key in keys if key[0] == namespace for name in key_names[key]}
                alias_ok = bool(policy and len(ns.get(policy['anchor_namespace'], set())) == 1
                                and (len(names) == 1 or reviewed is not None)
                                and all(key_names[key] for key in keys if key[0] == namespace)
                                and sum(bool(re.fullmatch(policy['primary_pattern'], ident)) for ident in ids) == 1
                                and all(re.fullmatch(policy['primary_pattern'], ident) or re.fullmatch(policy['alias_pattern'], ident) for ident in ids))
                if not alias_ok:
                    bad = True
            if not bad and any(len(ids) > 1 for ids in ns.values()):
                self.aliases.append({'ids': keys, 'reason': 'user-reviewed identity alias' if reviewed else 'configured prospect-to-numeric alias; single anchor ID and exact normalized name', 'review': reviewed})
            if bad:
                self.bad_keys.update(keys)
                self.conflicts.append({"ids": keys, "reason": "multiple identifiers within a namespace"})
            for key in keys:
                anchor = key if bad else sorted(keys, key=lambda x: (x[0] != "mlbam", x[0] != "fangraphs", x))[0]
                self.key_player[key] = "p_" + digest("|".join(anchor))

    def find(self, key):
        if self.parent[key] != key:
            self.parent[key] = self.find(self.parent[key])
        return self.parent[key]


def build(config_path, output_root=None):
    config_path = Path(config_path).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    project = config_path.parent.parent
    registry = json.loads((config_path.parent / cfg["metric_registry"]).read_text(encoding="utf-8"))
    overrides = json.loads((config_path.parent / cfg["identity_overrides"]).read_text(encoding="utf-8"))
    reviewed_aliases = json.loads((config_path.parent / cfg['reviewed_aliases']).read_text(encoding='utf-8')) if cfg.get('reviewed_aliases') else []
    resolutions = json.loads((config_path.parent / cfg['duplicate_resolutions']).read_text(encoding='utf-8')) if cfg.get('duplicate_resolutions') else []
    out = Path(output_root or project / "data" / "warehouse").resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Output must be empty; use a new --output directory: {out}")
    # Validate the full manifest before writing outputs.
    inputs = []
    for spec in cfg["files"]:
        base = Path(cfg["input_roots"][spec["root"]])
        if not base.is_absolute():
            base = project / base
        path = (base / spec["file"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path == out or out in path.parents:
            raise ValueError("Output directory must not contain input files")
        inputs.append((spec, path))
    if len({p for _, p in inputs}) != len(inputs):
        raise ValueError("Manifest repeats an input file")
    row_data, runs, field_map, issues = [], [], [], []
    for spec, path in inputs:
        profile = cfg["profiles"][spec["profile"]]
        headers, records = read_rows(path, spec)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        run_id = "r_" + digest(json.dumps(spec, sort_keys=True) + checksum)
        mapping = dict(cfg["metric_aliases"])
        mapping.update(profile.get("metric_aliases", {}))
        for header in headers:
            target = mapping.get(header, header)
            field_map.append({"run_id": run_id, "raw_field": header, "canonical_metric": target if target in registry else "", "preservation": "raw_json"})
        for line, raw in records:
            if not any(v.strip() for v in raw.values()):
                issues.append({"run_id": run_id, "row": line, "issue": "blank_row_preserved"})
            def value(field):
                return next((raw[k].strip() for k in profile.get(field, []) if raw.get(k, "").strip()), "")
            season_text = str(spec.get("season") or value("season"))
            try:
                season = int(season_text)
                if not 1900 <= season <= 2200:
                    raise ValueError()
            except ValueError:
                season = None
                issues.append({"run_id": run_id, "row": line, "issue": "invalid_season", "value": season_text})
            keys = []
            for namespace, columns in profile["ids"].items():
                identifier = next((clean_id(raw.get(k)) for k in columns if clean_id(raw.get(k))), "")
                if identifier:
                    keys.append((namespace, identifier))
            stats = {}
            for header, raw_value in raw.items():
                metric = mapping.get(header, header)
                if metric not in registry or spec["player_type"] not in registry[metric]["player_types"]:
                    continue
                if not raw_value.strip() or raw_value.strip().lower() in {"nan", "n/a", "null", "--", "-"}:
                    continue
                try:
                    number = float(raw_value.strip().rstrip("%"))
                    if raw_value.strip().endswith("%"):
                        number /= 100
                    if not math.isfinite(number):
                        raise ValueError()
                    if metric == "IP" and spec.get("ip_notation", "decimal") == "baseball":
                        whole, fraction = raw_value.split(".") if "." in raw_value else (raw_value, "0")
                        if fraction not in {"0", "1", "2"}:
                            raise ValueError()
                        number = int(whole) + int(fraction) / 3
                    stats[metric] = number
                except ValueError:
                    issues.append({"run_id": run_id, "row": line, "issue": "invalid_numeric", "field": header, "value": raw_value})
            for metric, meta in registry.items():
                formula = meta.get("derive")
                if formula and spec["player_type"] in meta["player_types"]:
                    if 'sum' in formula:
                        operands = [stats.get(key) for key in formula['sum']]
                        if all(number is not None for number in operands):
                            stats[metric] = sum(operands)
                        continue
                    numerator, denominator = stats.get(formula["numerator"]), stats.get(formula["denominator"])
                    if numerator is not None and denominator is not None and denominator > 0:
                        stats[metric] = numerator / denominator * formula.get("scale", 1)
            row_data.append({"record_id": "s_" + digest(f"{run_id}:{line}"), "run_id": run_id, "row_number": line, "season": season, "source": spec["source"], "kind": spec["kind"], "player_type": spec["player_type"], "name": value("name"), "team": value("team"), "id_keys": keys, "metrics": stats, "raw": raw})
        runs.append({"run_id": run_id, "season": spec.get("season"), "source": spec["source"], "kind": spec["kind"], "player_type": spec["player_type"], "original_file": str(path), "sha256": checksum, "rows": len(records), "headers": headers, "ip_notation": spec.get("ip_notation", "decimal")})
    identities = Identities(row_data, overrides, cfg.get('id_alias_policy'), reviewed_aliases)
    for row in row_data:
        keys = row["id_keys"]
        row["identity_conflict"] = any(key in identities.bad_keys for key in keys)
        row["player_id"] = identities.key_player[keys[0]] if keys else "unresolved_" + digest(row["record_id"])
    # Conservative names bridge different namespaces only when the entire corpus
    # has exactly one candidate in the configured target namespace. Collisions
    # are never resolved by team alone (trades and multi-team totals are common).
    candidates = defaultdict(set)
    source_name_ids = defaultdict(set)
    for row in row_data:
        for namespace, identifier in row['id_keys']:
            source_name_ids[(namespace, normalize_name(row['name']))].add(row['player_id'])
        if not row["identity_conflict"] and any(ns == cfg["name_bridge_namespace"] for ns, _ in row["id_keys"]):
            candidates[normalize_name(row["name"])].add(row["player_id"])
    bridges = defaultdict(set)
    for row in row_data:
        if any(ns == cfg["name_bridge_namespace"] for ns, _ in row["id_keys"]) or row["identity_conflict"]:
            continue
        choices = candidates.get(normalize_name(row["name"]), set())
        source_unique = all(len(source_name_ids[(ns, normalize_name(row['name']))]) == 1 for ns, _ in row['id_keys'])
        if row["name"] and len(choices) == 1 and source_unique:
            bridges[row["player_id"]].update(choices)
    accepted = {pid: next(iter(ids)) for pid, ids in bridges.items() if len(ids) == 1}
    for row in row_data:
        row["identity_method"] = "conflicting_ids" if row["identity_conflict"] else "identifier" if row["id_keys"] else "unresolved"
        if row["player_id"] in accepted:
            row["player_id"] = accepted[row["player_id"]]
            row["identity_method"] = "unique_name_bridge"
    actual_index = defaultdict(list)
    for row in row_data:
        if row["kind"] == "actual":
            actual_index[(row["season"], row["player_type"], row["player_id"])].append(row)
    unmatched, summaries, duplicates = [], [], []
    groups = defaultdict(list)
    for row in row_data:
        key = (row["kind"], row["season"], row["source"], row["player_type"])
        groups[key].append(row)
        row["actual_record_id"] = None
        row["match_status"] = "actual" if row["kind"] == "actual" else "unmatched"
        row["match_reason"] = ""
        if row["kind"] == "projection":
            hits = actual_index.get((row["season"], row["player_type"], row["player_id"]), [])
            reason = ""
            if row["identity_conflict"]:
                reason = "identity_conflict"
            elif row["season"] is None:
                reason = "missing_season"
            elif len(hits) > 1:
                reason = "duplicate_actual_key"
            elif len(hits) == 1 and not hits[0]["identity_conflict"]:
                row["match_status"] = "matched"
                row["actual_record_id"] = hits[0]["record_id"]
            else:
                ambiguous = len(candidates.get(normalize_name(row["name"]), set())) > 1 or any(len(source_name_ids[(ns, normalize_name(row['name']))]) > 1 for ns, _ in row['id_keys'])
                needs_name_bridge = row['identity_method'] != 'unique_name_bridge' and not any(ns == cfg['name_bridge_namespace'] for ns, _ in row['id_keys'])
                reason = "ambiguous_name" if ambiguous and needs_name_bridge else "no_actual_in_season" if row["id_keys"] else "missing_identifier"
            if reason:
                row["match_reason"] = reason
                unmatched.append({k: row[k] for k in ["record_id", "run_id", "row_number", "season", "source", "player_type", "player_id", "name", "team", "id_keys", "match_reason"]})
    for (kind, season, source, player_type), rows in sorted(groups.items(), key=lambda x: str(x[0])):
        ids = Counter(row["player_id"] for row in rows)
        names = Counter(normalize_name(row["name"]) for row in rows if row["name"])
        raw_ids = Counter(key for row in rows for key in row["id_keys"])
        for row in rows:
            if ids[row["player_id"]] > 1 or any(raw_ids[k] > 1 for k in row["id_keys"]) or names[normalize_name(row["name"])] > 1:
                duplicates.append({"kind": kind, "season": season, "source": source, "player_type": player_type, "record_id": row["record_id"], "name": row["name"], "player_id": row["player_id"], "id_keys": row["id_keys"], "duplicate_player_key": ids[row["player_id"]] > 1, "duplicate_name": names[normalize_name(row["name"])] > 1})
        matched = sum(row["match_status"] == "matched" for row in rows)
        summaries.append({"kind": kind, "season": season, "source": source, "player_type": player_type, "records": len(rows), "projected": len(rows) if kind == "projection" else 0, "matched": matched, "unmatched": len(rows) - matched if kind == "projection" else 0, "duplicate_id_rows": sum(any(raw_ids[k] > 1 for k in row["id_keys"]) for row in rows), "duplicate_name_rows": sum(names[normalize_name(row["name"])] > 1 for row in rows), "duplicate_player_key_rows": sum(ids[row["player_id"]] > 1 for row in rows), "missing_id_rows": sum(not row["id_keys"] for row in rows), "missing_name_rows": sum(not row["name"] for row in rows), "missing_season_rows": sum(row["season"] is None for row in rows), "missing_key_rows": sum(not row["id_keys"] or row["season"] is None for row in rows), "identity_conflict_rows": sum(row["identity_conflict"] for row in rows), "name_bridge_rows": sum(row["identity_method"] == "unique_name_bridge" for row in rows)})
    # Analytical selections are a separate layer. Original source rows and
    # canonical statistics remain intact, even when excluded from analysis.
    selections, unresolved_duplicates = select_records(row_data, resolutions)
    selection_by_id = {s['record_id']:s for s in selections}
    for summary in summaries:
        group_rows = groups[(summary['kind'],summary['season'],summary['source'],summary['player_type'])]
        selected_rows = [r for r in group_rows if selection_by_id[r['record_id']]['selected']]
        summary['analytical_selected_rows'] = len(selected_rows)
        summary['analytical_matched_rows'] = sum(r['match_status']=='matched' for r in selected_rows)
        summary['analytical_unmatched_rows'] = sum(r['match_status']=='unmatched' for r in selected_rows)
        summary['analytical_excluded_rows'] = len(group_rows)-len(selected_rows)
    out.mkdir(parents=True, exist_ok=True)
    audit = out / "audit"
    audit.mkdir()
    database = out / "historical_projection_warehouse.sqlite"
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript('''
        CREATE TABLE players(player_id TEXT PRIMARY KEY, preferred_name TEXT);
        CREATE TABLE player_id_crosswalk(namespace TEXT, external_id TEXT, player_id TEXT REFERENCES players, evidence TEXT, PRIMARY KEY(namespace, external_id));
        CREATE TABLE ingestion_runs(run_id TEXT PRIMARY KEY, kind TEXT, season INTEGER, source TEXT, player_type TEXT, original_file TEXT, sha256 TEXT, rows INTEGER, headers_json TEXT, ip_notation TEXT);
        CREATE VIEW projection_runs AS SELECT * FROM ingestion_runs WHERE kind='projection';
        CREATE TABLE metric_registry(metric TEXT PRIMARY KEY, metadata_json TEXT);
        CREATE TABLE source_field_map(run_id TEXT REFERENCES ingestion_runs, raw_field TEXT, canonical_metric TEXT, preservation TEXT);
        CREATE TABLE player_aliases(player_id TEXT REFERENCES players, name TEXT, team TEXT, run_id TEXT REFERENCES ingestion_runs, record_id TEXT);
    ''')
    player_names = {}
    for row in sorted(row_data, key=lambda row: row["kind"] != "actual"):
        player_names.setdefault(row["player_id"], row["name"])
    for pid in identities.key_player.values():
        player_names.setdefault(accepted.get(pid, pid), "")
    conn.executemany("INSERT INTO players VALUES (?,?)", player_names.items())
    crosswalk = []
    for (ns, external), pid in sorted(identities.key_player.items()):
        crosswalk.append({"namespace": ns, "external_id": external, "player_id": accepted.get(pid, pid), "evidence": "unique_name_bridge" if pid in accepted else "conflict_isolated" if (ns, external) in identities.bad_keys else "identifier_cooccurrence_or_override"})
    conn.executemany("INSERT INTO player_id_crosswalk VALUES (:namespace,:external_id,:player_id,:evidence)", crosswalk)
    for run in runs:
        conn.execute("INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?,?,?,?,?)", (run["run_id"], run["kind"], run["season"], run["source"], run["player_type"], run["original_file"], run["sha256"], run["rows"], json.dumps(run["headers"]), run["ip_notation"]))
    conn.executemany("INSERT INTO metric_registry VALUES (?,?)", [(k, json.dumps(v)) for k, v in registry.items()])
    conn.executemany("INSERT INTO source_field_map VALUES (:run_id,:raw_field,:canonical_metric,:preservation)", field_map)
    for player_type in ("hitter", "pitcher"):
        for kind in ("projection", "actual"):
            table = f"{player_type}_{'projections' if kind == 'projection' else 'actuals'}"
            conn.execute(f'''CREATE TABLE {table}(record_id TEXT PRIMARY KEY, run_id TEXT REFERENCES ingestion_runs, row_number INTEGER, season INTEGER, source TEXT, player_id TEXT REFERENCES players, name TEXT, team TEXT, identity_method TEXT, identity_conflict INTEGER, match_status TEXT, match_reason TEXT, actual_record_id TEXT, metrics_json TEXT, raw_json TEXT)''')
            subset = [row for row in row_data if row["kind"] == kind and row["player_type"] == player_type]
            conn.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(r["record_id"], r["run_id"], r["row_number"], r["season"], r["source"], r["player_id"], r["name"], r["team"], r["identity_method"], int(r["identity_conflict"]), r["match_status"], r["match_reason"], r["actual_record_id"], json.dumps(r["metrics"], ensure_ascii=False), json.dumps(r["raw"], ensure_ascii=False)) for r in subset])
            conn.execute(f"CREATE INDEX idx_{table}_key ON {table}(season,source,player_id)")
            flat = [{**{k: r[k] for k in ("record_id", "run_id", "row_number", "season", "source", "player_id", "name", "team", "identity_method", "match_status", "match_reason", "actual_record_id")}, **r["metrics"]} for r in subset]
            export_csv(out / f"{table}.csv", flat)
    conn.executemany("INSERT INTO player_aliases VALUES (?,?,?,?,?)", [(r["player_id"], r["name"], r["team"], r["run_id"], r["record_id"]) for r in row_data])
    conn.execute('''CREATE TABLE record_selection(record_id TEXT PRIMARY KEY,
        player_type TEXT, kind TEXT, selected INTEGER, selection_reason TEXT,
        excluded_metrics_json TEXT, analytical_metrics_json TEXT, review_json TEXT)''')
    conn.executemany('INSERT INTO record_selection VALUES (?,?,?,?,?,?,?,?)',
        [(s['record_id'], s['player_type'], s['kind'], int(s['selected']), s['selection_reason'],
          json.dumps(s['excluded_metrics']), json.dumps(s['analytical_metrics']), json.dumps(s['review'])) for s in selections])
    for player_type in ('hitter','pitcher'):
        table = f'{player_type}_projections'
        conn.execute(f'''CREATE VIEW analytical_{table} AS SELECT p.record_id,p.run_id,
            p.row_number,p.season,p.source,p.player_id,p.name,p.team,p.identity_method,
            p.match_status,p.match_reason,p.actual_record_id,
            s.analytical_metrics_json AS metrics_json,s.excluded_metrics_json,
            s.selection_reason FROM {table} p JOIN record_selection s USING(record_id)
            WHERE s.selected=1''')
        by_id = {s['record_id']: s for s in selections}
        analytical = [{**{k:r[k] for k in ('record_id','run_id','row_number','season','source','player_id','name','team','identity_method','match_status','match_reason','actual_record_id')},
            'excluded_metrics':by_id[r['record_id']]['excluded_metrics'],
            **by_id[r['record_id']]['analytical_metrics']} for r in row_data
            if r['kind']=='projection' and r['player_type']==player_type and by_id[r['record_id']]['selected']]
        export_csv(out / f'analytical_{table}.csv', analytical)
    conn.commit()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    stored = sum(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("hitter_actuals", "pitcher_actuals", "hitter_projections", "pitcher_projections"))
    conn.close()
    assert stored == len(row_data), "Input/output row conservation failed"
    assert integrity == "ok" and not fk_errors, "Database integrity failed"
    export_csv(out / "players.csv", [{"player_id": k, "preferred_name": v} for k, v in player_names.items()])
    export_csv(out / "player_id_crosswalk.csv", crosswalk)
    export_csv(out / "projection_runs.csv", [r for r in runs if r["kind"] == "projection"])
    export_csv(out / "source_field_map.csv", field_map)
    export_csv(out / "metric_registry.csv", [{"metric": k, **v} for k, v in registry.items()])
    export_csv(audit / "validation_summary.csv", summaries)
    export_csv(audit / "unmatched_players.csv", unmatched)
    export_csv(audit / "duplicate_records.csv", duplicates)
    export_csv(audit / "parsing_issues.csv", issues)
    export_csv(audit / 'record_selection.csv', [{k:v for k,v in s.items() if k!='analytical_metrics'} for s in selections])
    export_csv(audit / 'duplicate_resolutions.csv', [{k:v for k,v in s.items() if k!='analytical_metrics'} for s in selections if s['review']])
    export_csv(audit / 'unresolved_metric_exclusions.csv', [{'record_id':s['record_id'], 'name':s['name'], 'season':s['season'], 'source':s['source'], 'player_type':s['player_type'], 'metric':metric, 'reason':'Owner-approved unresolved duplicate metric; excluded from analytical statistics'} for s in selections if s['selected'] for metric in s['excluded_metrics']])
    export_csv(audit / 'name_bridge_matches.csv', [{k: r[k] for k in ('record_id','run_id','season','source','player_type','name','team','id_keys','player_id','match_status','actual_record_id')} for r in row_data if r['identity_method'] == 'unique_name_bridge'])
    (audit / "identity_conflicts.json").write_text(json.dumps(identities.conflicts, indent=2), encoding="utf-8")
    (audit / 'verified_id_aliases.json').write_text(json.dumps(identities.aliases, indent=2), encoding='utf-8')
    critical = bool(identities.conflicts or unresolved_duplicates or any(s["missing_season_rows"] for s in summaries) or any(i["issue"] == "invalid_numeric" for i in issues))
    report = {"builder_version": VERSION, "built_at_utc": datetime.now(timezone.utc).isoformat(), "status": "review_required" if critical else "passed", "input_files": len(runs), "projection_files": sum(r["kind"] == "projection" for r in runs), "input_rows": len(row_data), "stored_rows": stored, "canonical_players": len(player_names), "matched_projection_rows": sum(s["matched"] for s in summaries), "unmatched_projection_rows": len(unmatched), "unmatched_reasons": dict(Counter(r["match_reason"] for r in unmatched)), "identity_conflict_components": len(identities.conflicts), "accepted_id_alias_components": len(identities.aliases), "parsing_issues": len(issues), "sqlite_integrity": integrity, "foreign_key_errors": fk_errors, "groups": summaries, "inputs": runs, "notes": ["Unmatched does not imply zero MLB performance.", "Duplicate keys are retained at record grain and require review before backtesting.", "Name bridges are conservative candidates, not externally verified IDs."]}
    report.update({'reviewed_duplicate_groups':len(resolutions), 'unresolved_duplicate_groups':len(unresolved_duplicates),
                   'analytical_projection_rows':sum(s['kind']=='projection' and s['selected'] for s in selections),
                   'excluded_duplicate_projection_rows':sum(s['kind']=='projection' and not s['selected'] and bool(s['review']) for s in selections),
                   'unresolved_metric_exclusions':sum(len(s['excluded_metrics']) for s in selections if s['selected'])})
    if not critical and report['unresolved_metric_exclusions']:
        report['status']='passed_with_metric_exclusions'
    (audit / "validation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "effective_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (out / "effective_metric_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (out / "effective_identity_overrides.json").write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    (out / 'effective_reviewed_aliases.json').write_text(json.dumps(reviewed_aliases, indent=2), encoding='utf-8')
    (out / 'effective_duplicate_resolutions.json').write_text(json.dumps(resolutions, indent=2), encoding='utf-8')
    lines = ["# Stage 1B validation", "", f"Status: **{report['status']}**", "", f"{len(runs)} inputs; {len(row_data):,} input rows; {stored:,} stored rows.", f"{report['matched_projection_rows']:,} matched projections; {len(unmatched):,} unmatched projections.", "", "|Season|Source|Type|Projected|Matched|Unmatched|Duplicate IDs|Duplicate names|Missing keys|", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in summaries:
        if s["kind"] == "projection":
            lines.append("|" + "|".join(str(s[k]) for k in ("season", "source", "player_type", "projected", "matched", "unmatched", "duplicate_id_rows", "duplicate_name_rows", "missing_key_rows")) + "|")
    lines.extend(["", "Every source record is retained. See unmatched_players.csv, duplicate_records.csv, parsing_issues.csv and identity_conflicts.json for row-level review.", "", "Name bridge matches require review before Stage 2. Missing actuals are not converted to zero. Source columns (including repeated headers) are retained in SQLite raw_json; input SHA-256 hashes are recorded."])
    lines.extend(['',f"Analytical projection rows: {report['analytical_projection_rows']:,}. Reviewed duplicate groups: {len(resolutions)}; unresolved duplicate groups: {len(unresolved_duplicates)}.", f"Unresolved metric exclusions: {report['unresolved_metric_exclusions']}. Use analytical_hitter_projections and analytical_pitcher_projections for Stage 2; original tables retain both rows and all metrics."])
    (audit / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def select_records(rows, resolutions):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['kind'],row['player_type'],row['season'],row['source'],row['player_id'])].append(row)
    reviews = {}
    for entry in resolutions:
        record_set = frozenset(entry['candidate_record_ids'])
        if len(record_set)<2 or entry['selected_record_id'] not in record_set or not entry.get('verified_by') or not entry.get('reason'):
            raise ValueError('Invalid reviewed duplicate resolution')
        if record_set in reviews:
            raise ValueError('Duplicate resolution entries')
        reviews[record_set]=entry
    used, selections, unresolved = set(), [], []
    for key, candidates in groups.items():
        record_set=frozenset(r['record_id'] for r in candidates)
        entry=reviews.get(record_set)
        if entry:
            used.add(record_set)
        if len(candidates)>1 and not entry:
            unresolved.append(key)
        for row in candidates:
            selected = (len(candidates)==1 or bool(entry and row['record_id']==entry['selected_record_id'])) and not row['identity_conflict'] and row['season'] is not None
            excluded = entry.get('exclude_metrics',[]) if entry and selected else []
            reason='reviewed_duplicate_selected' if entry and selected else 'reviewed_duplicate_not_selected' if entry else 'unresolved_duplicate' if len(candidates)>1 else 'unique_record'
            if row['identity_conflict'] or row['season'] is None:
                reason='invalid_identity_or_season'
            selections.append({'record_id':row['record_id'],'player_type':row['player_type'],'kind':row['kind'],'season':row['season'],'source':row['source'],'name':row['name'],
                               'selected':selected,'selection_reason':reason,'excluded_metrics':excluded,
                               'analytical_metrics':{m:v for m,v in row['metrics'].items() if m not in excluded},'review':entry})
    if set(reviews)!=used:
        raise ValueError('Reviewed duplicate resolution does not match the exact current duplicate records; review input changes')
    return selections, unresolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "config" / "warehouse.json")
    parser.add_argument("--output", type=Path, help="New or empty destination directory")
    args = parser.parse_args()
    report = build(args.config, args.output)
    print(json.dumps({k: report[k] for k in ("status", "input_files", "stored_rows", "matched_projection_rows", "unmatched_projection_rows")}, indent=2))
    return 2 if report["status"] == "review_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
