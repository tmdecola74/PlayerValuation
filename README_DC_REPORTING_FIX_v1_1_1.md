DC reporting fix 1.1.1

Extract into D:\JonAPythonClass\pycharm\PlayerValuation and replace build_dc_values_v1_1.py. The tests folder merges into your existing tests folder. Your reviewed eligibility CSV is not replaced.

Run:
python -m unittest discover -s tests -p "test_dc_reporting_v1_1_1.py" -v
python build_dc_values_v1_1.py --output "outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix"

Expected for your reviewed inputs: 961 ranked players, 17 unvalued assets, 961 ADP matched rows. De Vries (12299), Miranda (10253), Doyle (12487) should have NFBC IDs and ADP and should not appear in the unvalued watchlist.

The reviewed eligibility table supplies current NFBC/canonical links and ADP. Original ADP is a fallback where eligibility ADP is blank. Resolved review entries are excluded from the watchlist; mapped but unvalued entries keep the component/floor reason. The original review CSV remains archived unchanged. Projection calculations and original reference data are unchanged. Complete final output backup still includes corrected reporting.

Manual eligibility mappings must still be preserved if inputs are regenerated; this patch does not add persistent alias override support.
