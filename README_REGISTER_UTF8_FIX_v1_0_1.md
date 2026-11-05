# Windows UTF-8 fix v1.0.1

Extract into D:\JonAPythonClass\pycharm\PlayerValuation and replace the builder and its test file. Requires the original v1.0 package already installed. All JSON reads explicitly use UTF-8 with optional BOM. Text outputs remain UTF-8. Register and policy versions remain 1.0.0; the build report records implementation version 1.0.1.

All 11 tests pass, including a simulated CP1252-default build. A complete live evidence build and verified backup pass. The register CSV/JSON and exclusion plan are byte-identical to v1.0 outputs. No reference or evidence file changes.

Run:

```powershell
python -m unittest discover -s tests -p "test_discrepancy_register_v1_0.py" -v
python build_discrepancy_register_v1_0.py --output "outputs/discrepancy_register_v1_0_utf8"
```

Use a different new output name if that folder already exists. No redownloads or reference rebuilds are required.
