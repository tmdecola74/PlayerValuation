# FanGraphs play-log review — historical years need confirmation

The uploaded workbook has one sheet. The five relevant rows are 2, 8, 10, 12 and 17. Adjacent rows contain the copied pitch descriptions. No workbook values or source counts were changed.

| Expected historical date | Player | FanGraphs play text | MLB feed outcome | Finding, conditional on historical year |
|---|---|---|---|---|
| 2016-09-27 | Chase Headley | Single to shortstop | Single | Play text agrees; FanGraphs game total reported zero hits |
| 2016-09-30 | Charlie Culberson | Single to shortstop; Hernández out at third | Single; runner out at third | Play text agrees; FanGraphs game total reported zero hits |
| 2016-10-02 | Aaron Altherr | Reached on pitcher error | Field error | Play text agrees; FanGraphs game total reported one hit |
| 2016-10-02 | Adam Wainwright | Reached on third-base error; advanced to second | Field error | Play text agrees; FanGraphs game total reported a double |
| 2022-08-13 | Luis González | Single to third | Field error | Cross-provider play-label difference remains |

The paired pitcher game totals differ in the same direction. Conditional on verifying the historical source years, four pairs (12 metric rows) show FanGraphs play text agreeing with MLB while FanGraphs game/season hit totals disagree. González/Underwood accounts for the remaining three metric rows and has a single-versus-error play-text disagreement.

## Provenance and matching limits

Every populated Date cell in the workbook stores a date in 2026. The intended dates are in 2016 and 2022. Several Score cells also store Excel dates rather than score strings. This is consistent with Excel interpreting pasted month/day and score text, but that cause has not been established. The workbook contains no source URLs. No stored year or score was silently rewritten or used as historical confirmation.

Month/day, inning and half-inning match the prior MLB candidates. Opposing pitcher abbreviations, batter names in the descriptions and copied pitch descriptions also support those contextual candidates. This is not certification of exact cross-provider pitch/count alignment. The extra González stolen-base row is a runner event and is not an additional plate appearance or hit.

Please confirm that the first four players were viewed with 2016 selected and González with 2022 selected, and whether Excel assigned 2026 during pasting. Source page URLs with season selection, or screenshots including the selected year and relevant rows, would resolve the provenance issue. No new broad download is needed.

No historical scoring-revision date is established. The original reconciliation and actuals reference remain unchanged. These findings do not select a modeling label source or approve modeling readiness.
