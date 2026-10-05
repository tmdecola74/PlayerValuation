# Stage 2 — historical projection accuracy

Matched analytical projections: **13,497**. Unmatched analytical projections excluded: **39,794**.

Errors use projection minus actual: positive bias means overprojection. MAE and RMSE are in each metric's original units. Percentage metrics are fractions; multiply errors by 100 for percentage points.

The tables below compare every metric-capable source available that season on exactly the same players. Sources can differ across metrics. No seasons are pooled. These are descriptive lowest-MAE results, not statistically established winners.

Correlations and rank errors require at least 30 observations; rankings require 30. Constant-series correlations remain blank. Rate errors are equally weighted by player, with PA/IP thresholds controlling small samples.

All original rows remain in Stage 1B. Only reviewed analytical selections enter Stage 2. Greg Jones's WAR, wRC+, Off and Def remain excluded; they are outside this configured metric set.

## Common-player comparisons

### Hitters — regular_playing_time

Actual PA ≥ 300; projected floor 0. Every evaluated player has positive actual PA.

#### Fantasy Outcome

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|AVG|2|279|THE BAT X|0.018706|0.023738|0.0024592|0.54548|
|2024|HR|2|279|THE BAT X|5.227|6.8253|-0.40397|0.69473|
|2024|OPS|2|279|THE BAT X|0.056783|0.071725|0.014545|0.51766|
|2024|R|2|279|THE BAT X|15.873|20.248|-2.827|0.62061|
|2024|RBI|2|279|THE BAT X|15.78|19.972|-2.882|0.64369|
|2024|SB|2|279|Steamer|5.2114|8.2933|-2.0944|0.66195|
|2025|AVG|3|275|Steamer|0.01848|0.023127|0.00099629|0.48146|
|2025|HR|3|275|Steamer|5.9534|7.8144|-1.6207|0.64672|
|2025|OPS|3|275|Steamer|0.054331|0.069591|0.008537|0.49971|
|2025|R|3|275|Steamer|15.565|20.055|-7.2775|0.61568|
|2025|RBI|3|275|Steamer|16.783|21.826|-7.3713|0.55161|
|2025|SB|3|275|THE BAT X|4.5008|6.9155|-0.72128|0.76028|
|2026|AVG|4|263|Depth Charts|0.017915|0.022455|0.0020893|0.52272|
|2026|HR|4|263|Steamer|6.2109|7.842|-1.8322|0.61507|
|2026|OPS|4|263|Depth Charts|0.054697|0.067888|0.0055075|0.4661|
|2026|R|4|263|THE BAT X|17.726|21.813|-5.5293|0.56244|
|2026|RBI|4|263|THE BAT X|18.531|23.155|-5.735|0.49237|
|2026|SB|4|263|Steamer|4.3148|6.1821|-0.91204|0.73692|

#### Opportunity

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|G|2|279|THE BAT X|29.42|39.018|-18.174|0.42715|
|2024|PA|2|279|THE BAT X|105.82|139.37|-43.168|0.63336|
|2025|G|3|275|THE BAT X|28.877|38.238|-18.168|0.42209|
|2025|PA|3|275|OOPSY|105.81|144.08|-20.542|0.60032|
|2026|G|4|263|THE BAT X|30.11|40.115|-18.205|0.36592|
|2026|PA|4|263|THE BAT X|113.95|146.57|-46.788|0.5752|

#### Skill

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|BABIP|2|279|THE BAT X|0.02184|0.028498|0.0018516|0.49979|
|2024|BB%|2|279|THE BAT X|0.014833|0.018955|0.0029545|0.70727|
|2024|HR_per_PA|2|279|THE BAT X|0.0079957|0.010001|0.0014606|0.67488|
|2024|ISO|2|279|THE BAT X|0.029344|0.036764|0.0074718|0.66745|
|2024|K%|2|279|Steamer|0.024543|0.031723|0.0014925|0.84808|
|2024|RBI_per_PA|2|279|THE BAT X|0.016668|0.021434|0.0032478|0.56124|
|2024|R_per_PA|2|279|THE BAT X|0.015183|0.018712|0.0042179|0.4487|
|2024|SB_per_PA|2|279|THE BAT X|0.0089788|0.013162|-0.0012375|0.80524|
|2024|wOBA|2|279|THE BAT X|0.022093|0.027974|0.0045791|0.526|
|2025|BABIP|3|275|OOPSY|0.022352|0.029099|8.2793e-05|0.44194|
|2025|BB%|3|275|THE BAT X|0.014924|0.019203|-0.0030517|0.76334|
|2025|HR_per_PA|3|275|OOPSY|0.0085436|0.010539|-0.00030914|0.69576|
|2025|ISO|3|275|Steamer|0.030218|0.037725|0.0048856|0.66714|
|2025|K%|3|275|OOPSY|0.027492|0.034861|0.004255|0.78902|
|2025|RBI_per_PA|3|275|Steamer|0.018874|0.023478|0.000971|0.47682|
|2025|R_per_PA|3|275|THE BAT X|0.014142|0.017656|-0.00029895|0.5209|
|2025|SB_per_PA|3|275|THE BAT X|0.0080133|0.011699|0.00064046|0.7967|
|2025|wOBA|3|275|Steamer|0.021559|0.027293|0.0039972|0.49617|
|2026|BABIP|4|263|Depth Charts|0.021591|0.027523|0.0017018|0.48025|
|2026|BB%|4|263|Depth Charts|0.015707|0.020122|-0.0027912|0.69567|
|2026|HR_per_PA|4|263|Steamer|0.0079097|0.010018|0.00099768|0.6882|
|2026|ISO|4|263|OOPSY|0.02813|0.035792|-0.00012195|0.66519|
|2026|K%|4|263|Depth Charts|0.024725|0.031627|-0.00080335|0.83839|
|2026|RBI_per_PA|4|263|Steamer|0.017889|0.02295|8.0496e-05|0.41091|
|2026|R_per_PA|4|263|THE BAT X|0.015491|0.019249|-0.00079718|0.38026|
|2026|SB_per_PA|4|263|THE BAT X|0.0074445|0.009787|0.0017192|0.80202|
|2026|wOBA|4|263|Depth Charts|0.021473|0.026506|-0.00074883|0.45753|

### Pitchers — substantial_innings

Actual IP ≥ 40; projected floor 0. Every evaluated player has positive actual IP.

#### Fantasy Outcome

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|ERA|2|361|Steamer|0.87949|1.1245|0.19632|0.31561|
|2024|QS|2|361|ATC|2.0762|3.5097|-0.43201|0.88246|
|2024|SO|2|361|ATC|26.008|33.935|-4.7333|0.64982|
|2024|SV|2|361|Steamer|1.6884|4.0756|-0.57365|0.60904|
|2024|SV_plus_HLD|2|361|ATC|4.1593|6.9262|-1.9084|0.85035|
|2024|W|2|361|Steamer|2.5091|3.1976|-0.18716|0.50428|
|2024|WHIP|2|361|ATC|0.15554|0.20109|0.050788|0.35629|
|2025|ERA|4|331|OOPSY|0.87882|1.1261|-0.019422|0.3767|
|2025|QS|4|331|ATC|2.1653|3.6729|-0.048801|0.86025|
|2025|SO|4|331|ATC|26.866|36.628|-2.7118|0.61296|
|2025|SV|4|331|Steamer|1.743|4.1793|-0.52875|0.58624|
|2025|SV_plus_HLD|4|331|ATC|3.7708|6.6905|-1.7577|0.86818|
|2025|W|4|331|ATC|2.5089|3.2959|-0.39695|0.4849|
|2025|WHIP|4|331|OOPSY|0.13904|0.18017|0.01705|0.40325|
|2026|ERA|5|337|Steamer|0.84324|1.065|0.046484|0.41429|
|2026|QS|5|337|ATC|2.2709|3.7567|0.11099|0.85232|
|2026|SO|5|337|OOPSY|28.193|37.542|-1.1128|0.64399|
|2026|SV|5|337|ATC|2.0909|5.2008|-0.67148|0.62116|
|2026|SV_plus_HLD|5|337|ATC|4.0823|7.3288|-1.5709|0.82161|
|2026|W|5|337|OOPSY|2.546|3.3269|-0.011869|0.50789|
|2026|WHIP|5|337|ATC|0.1438|0.18301|0.015513|0.36364|

#### Opportunity

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|G|2|361|Steamer|9.7639|13.33|2.2935|0.70128|
|2024|GS|2|361|ATC|3.7298|6.1623|-0.59332|0.8807|
|2024|IP|2|361|ATC|24.669|33.445|-5.8828|0.66699|
|2025|G|4|331|ATC|10.225|13.608|-4.0047|0.71628|
|2025|GS|4|331|OOPSY|4.0272|6.7046|-0.35952|0.86172|
|2025|IP|4|331|OOPSY|26.296|38.088|2.7197|0.5985|
|2026|G|5|337|ATC|9.6565|13.409|-3.8305|0.69959|
|2026|GS|5|337|ATC|4.5627|7.0681|-1.4746|0.8543|
|2026|IP|5|337|OOPSY|25.944|36.042|-1.835|0.64301|

#### Skill

|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|
|---|---|---:|---:|---|---:|---:|---:|---:|
|2024|BABIP|2|361|Steamer|0.028481|0.036645|0.0087561|0.314|
|2024|BB%|2|361|ATC|0.016005|0.02082|0.0036211|0.56896|
|2024|BB/9|2|361|ATC|0.68509|0.88791|0.15312|0.54667|
|2024|FIP|2|361|Steamer|0.652|0.83229|0.29696|0.45966|
|2024|HR/9|2|361|Steamer|0.30788|0.39744|0.11393|0.45634|
|2024|K%|2|361|Steamer|0.028471|0.036897|-0.0040059|0.68392|
|2024|K-BB%|2|361|ATC|0.034966|0.046245|-0.0036403|0.55689|
|2024|K/9|2|361|Steamer|0.99544|1.2735|-0.0013288|0.69447|
|2025|BABIP|3|385|OOPSY|0.027041|0.033838|0.0024264|0.25626|
|2025|BB%|3|385|ATC|0.014811|0.019699|-8.1524e-05|0.56869|
|2025|BB/9|4|331|Steamer|0.61492|0.80628|-0.036237|0.55297|
|2025|FIP|3|385|Steamer|0.61607|0.78164|0.046766|0.49063|
|2025|HR/9|4|331|Steamer|0.32328|0.41053|0.012164|0.48805|
|2025|K%|3|385|ATC|0.02948|0.037336|-0.00031874|0.66345|
|2025|K-BB%|3|385|ATC|0.034433|0.043538|-0.00023723|0.57618|
|2025|K/9|4|331|ATC|1.0184|1.3011|0.13304|0.66615|
|2026|BABIP|4|378|OOPSY|0.026873|0.034181|0.0048531|0.21141|
|2026|BB%|4|378|Depth Charts|0.01575|0.020226|-0.0045423|0.59114|
|2026|BB/9|5|337|Depth Charts|0.66363|0.85755|-0.17238|0.57193|
|2026|FIP|4|378|ATC|0.62317|0.79938|0.066977|0.42777|
|2026|HR/9|5|337|ATC|0.31908|0.40924|0.044743|0.45235|
|2026|K%|4|378|OOPSY|0.030808|0.037936|-0.0028902|0.655|
|2026|K-BB%|4|378|OOPSY|0.035437|0.044669|-0.0017949|0.52712|
|2026|K/9|5|337|OOPSY|1.0517|1.2945|0.010915|0.67088|

## Reading the detailed outputs

* `accuracy_summary.csv`: every source/season/metric/cohort, including source-specific, common-all and pairwise samples.
* `common_player_accuracy.csv`: all-source common-player comparisons only; compare sources within the same sample_id.
* `source_specific_accuracy.csv`: individual-source diagnostics; player populations differ across sources.
* `pairwise_comparisons.csv`: two-source comparisons on identical players. Positive MAE delta means source B has lower error.
* `cohort_memberships.jsonl`: exact player IDs and source sets for each sample_id. Match sample_id across outputs.
* `evaluation_pairs.csv`: linked projected/actual values and errors before cohort filtering.
* `input_coverage.csv`: selected, matched and unmatched counts. Unmatched never means assumed zero.
* `metric_availability.csv`, `missing_metric_pairs.csv`: unavailable fields and explicit missing-value reasons.
* `excluded_projection_records.csv`: source rows excluded by the reviewed analytical selection policy.
* `metric_derivations.csv`: missing OPS derived from OBP + SLG, with input side and formula recorded. Original values are never overwritten.

Only compare rows with the same sample_id when comparing sources. Pairwise and common-all estimates can differ because their player populations differ. Each metric has its own complete-value sample.

## Limits and next use

This report evaluates the supplied historical files as preseason snapshots. Their original timing is inherited from source provenance. Future optimized weights must be trained on earlier seasons and validated on a held-out season; this build fits no weights.

All thresholds are configurable. Source-specific summaries are useful diagnostics; common-player results support fair comparisons. Playing-time and skill are scored separately. Counting-stat errors still combine opportunity and skill, while rates such as HR/PA remove much of the exposure effect.
