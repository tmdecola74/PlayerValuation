# Feature definitions and provenance

All percentages are fractions 0–1. Output tables retain season, MLBAM ID, counts and measurement coverage. Nullable metrics remain null if no denominator. Samples reflect observed, validated pitch records, not a guarantee of official PA completeness.

| Output | Grain | Main contents |
|---|---|---|
| hitter_statcast_season | season × batter MLBAM | contact, swings, whiffs, chase, observed PA/K/BB, tracked BBE counts |
| pitcher_statcast_season | season × pitcher MLBAM | same allowed/induced metrics plus aggregate pitch properties |
| pitcher_arsenal_season | season × pitcher × pitch type | properties, classified-pitch usage, whiffs, observed putaway/RV |
| pitcher_arsenal_changes | same | prior contiguous-season velocity/usage/whiff deltas |
| pitcher_platoon_season | season × pitcher × batter stance | performance/skill samples against each stance |
| hitter/pitcher_skill_changes | season × MLBAM | prior contiguous-season changes, never arbitrary lag across gaps |
| team_context_season | season × MLB team ID | completed-game W/RS/RA, Pythagorean proxy, close final margins |
| team_pitcher_usage_season | season × team × pitcher | appearance inning shares, first/later entry proxies |
| team_running_opportunities_season | season × batting team | distinct PA sequences containing runner on first/second open |
| team_late_lead_states_season | season × fielding team | games with observed ninth-inning defensive lead 1–3 |
| team_context_enriched | season × team | optional full-season official SB/CS/SV/HLD supplements |

Whiff numerator: descriptions swinging_strike, swinging_strike_blocked, missed_bunt, swinging_pitchout. Swing denominator also includes foul/foul_tip/foul_bunt, hit-into-play variants and pitchout/bunt-foul-tip contacts. Foul tips count as contact in this explicit local definition; this may differ from published Savant leaderboards. Do not claim exact official leaderboard equivalence.

SwStr% uses misses among thrown pitch-result rows (type B/S/X), excluding automatic_ball/automatic_strike. CSW uses those misses plus called strikes over the same denominator. Zone rate uses numbered zones 1–9 divided by known numbered zones 1–14; chase uses swings in zones 11–14 divided by pitches there. Zone denominators are exported. Unknown zone is excluded, never guessed.

Observed K% and BB% use terminal events in the configured PA event whitelist; BB includes intentional walks. Non-PA events are listed in feature_audit.json. No at-bat-sequence ID alone implies a completed PA. Putaway is observed terminal strikeouts on two-strike rows divided by all two-strike rows. RV100 is mean delta_run_exp × 100, OFFENSE perspective; it is not asserted to be the published pitcher leaderboard RV/100.

BBE means type X. EV uses non-null launch_speed on those rows; hard-hit uses EV >=95 with known-EV denominator. Barrel% uses launch_speed_angle=6 among BBE with known launch_speed_angle. xwobacon is the mean estimated_woba_using_speedangle on measured contact only; xba_contact is its BA counterpart. These are not whole-PA xwOBA or xERA. EV data may contain provider estimates.

pfx_x/pfx_z are supplied feet converted to inches, preserving catcher's perspective sign. They are not automatically arm-side or total gravity-included movement. Location/zone measurement era is explicit: through 2025 front-of-plate/operator zone; 2026 onward ABS middle-of-plate definitions. Velocity/spin/extension average non-null samples; aggregate pitcher velocity can change through pitch-mix changes. Prefer pitch-type velocity deltas. Hitter opposing pitch properties are labeled faced/opposing, not hitter ability.

Pitch usage denominator is classified pitches only (pitch_type non-null). Missing types are excluded, and overall pitch counts can differ. No missing pitch type is imputed. Year-over-year changes require adjacent season years and may still compare partial versus full histories; users must control selected dates/sample sizes.

Team wins/runs come from archived final MLB schedule scores. Pythagorean proxy exponent=1.83; it is a descriptive feature, not a future-team win forecast. Inning appearance shares include any pitcher observed in that inning; later-entry is not a reliable starter/reliever classification. Ninth-lead states are not official save opportunities. Runner-first/second-open PA sequences are a denominator proxy, not actual steal opportunities or team aggressiveness; an event adapter is still needed for conditional attempts. Official SB attempts per PA is labeled per PA and must not be substituted for attempts per eligible runner opportunity.

Team supplements join MLB numeric team ID, avoiding abbreviation alias guesses. Source group fields are retained in raw_stats_json. Original team actuals are full-season statistics; they are blocked from a partial-season feature snapshot. Historical past-team attributes must be transferred to the upcoming projected team using forecast-date roster context in the model layer.

Definitions referenced during development:
- https://baseballsavant.mlb.com/csv-docs
- https://github.com/jldbc/pybaseball/blob/master/pybaseball/statcast.py
- https://statsapi.mlb.com/api/v1/schedule
- https://statsapi.mlb.com/api/v1/teams/stats
