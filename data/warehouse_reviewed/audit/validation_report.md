# Stage 1B validation

Status: **review_required**

22 inputs; 57,855 input rows; 57,855 stored rows.
13,509 matched projections; 39,798 unmatched projections.

|Season|Source|Type|Projected|Matched|Unmatched|Duplicate IDs|Duplicate names|Missing keys|
|---|---|---|---:|---:|---:|---:|---:|---:|
|2024|ATC|pitcher|917|622|295|0|4|0|
|2024|Steamer|hitter|3711|649|3062|0|76|1|
|2024|Steamer|pitcher|5168|783|4385|0|121|0|
|2024|THE BAT X|hitter|729|530|199|0|0|0|
|2025|ATC|pitcher|882|688|194|0|2|0|
|2025|OOPSY|hitter|3826|671|3155|16|91|0|
|2025|OOPSY|pitcher|5003|824|4179|16|119|0|
|2025|RotoWire|pitcher|1207|598|609|0|8|0|
|2025|Steamer|hitter|4140|666|3474|0|90|1|
|2025|Steamer|pitcher|5215|791|4424|0|126|1|
|2025|THE BAT X|hitter|696|586|110|0|2|0|
|2026|ATC|pitcher|855|681|174|0|2|0|
|2026|Depth Charts|hitter|638|555|83|0|2|0|
|2026|Depth Charts|pitcher|802|666|136|0|0|0|
|2026|OOPSY|hitter|2802|649|2153|0|24|0|
|2026|OOPSY|pitcher|4232|796|3436|0|75|0|
|2026|RotoWire|pitcher|2439|713|1726|0|18|0|
|2026|Steamer|hitter|4186|659|3527|0|78|0|
|2026|Steamer|pitcher|5162|799|4363|0|123|0|
|2026|THE BAT X|hitter|697|583|114|0|2|0|

Every source record is retained. See unmatched_players.csv, duplicate_records.csv, parsing_issues.csv and identity_conflicts.json for row-level review.

Name bridge matches require review before Stage 2. Missing actuals are not converted to zero. Source columns (including repeated headers) are retained in SQLite raw_json; input SHA-256 hashes are recorded.
