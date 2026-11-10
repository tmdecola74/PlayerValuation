# v1.15.1 packaging and frozen-market identity fix

Extract directly into `D:\JonAPythonClass\pycharm\PlayerValuation`, replacing the v1.15 adapter/test files. The package now includes the unchanged `dc_roster_simulator_v1_3.py` runtime dependency. No reference, projection, configuration or output files are included or modified.

Run:

```powershell
python -m unittest discover -s tests -p "test_draft_integration_v1_15.py" -v
python draft_integration_v1_15.py --sources homegrown reconciled_consensus --output "outputs/draft_source_integration_v1_15_1"
```

If SciPy is missing, install the previously delivered requirements first:

```powershell
python -m pip install -r requirements_draft_integration_v1_15.txt
```

## Changes

The old market check keyed duplicate detection only by NFBC ID, although frozen assets may contain hitter and pitcher role rows for one two-way NFBC asset. The fix validates the entire frozen domain by `(NFBC ID, player_type)`. Before simulation pooling, matching canonical two-way rows are reduced to the one role selected by the existing global valuation engine. Their unselected role is reported as `TWO_WAY_NONSELECTED_ROLE_ONE_NFBC_ASSET`. If neither role has usable valuation, both are explicitly excluded rather than guessing the market role. Conflicting canonical identities, duplicate same-role rows, different ADPs, or multiple selected roles still fail. Different NFBC IDs sharing a name are never merged.

A second supported frozen-export shape is an originally blank market canonical ID with an already resolved universe identity. It is accepted only when the exact NFBC/role membership, universe_id AND MLBAM ID agree with the frozen universe. No name matching occurs. An already populated conflicting ID is rejected. Original CSV/JSON references are unchanged; the resolution occurs only in a working copy.

`market_identity_resolution.csv` records each original market ID, resolved ID, and method. The build report adds `build_implementation_version: 1.15.1` and `frozen_market_identity_bridges`. Hash binding to v1.14 inputs remains mandatory. Identity errors now identify the relevant asset and conflicting fields rather than returning only a generic message.

The user's full production market/universe files were not supplied with the traceback. These tests reproduce the supported two-way and blank-ID export shapes, not a verified identification of a particular production player. If the revised run still fails, its detailed exception will identify the row requiring investigation; do not edit the frozen files or disable their hashes.

No statistical forecasts, model choices, role requirements, selection policy, or 2026 labels change. The homegrown GS dependency remains explicit. This fix does not supply missing role forecasts. Outputs use a new folder and complete verified backup as before.

The source report retains schema `version: 1.15.0` for compatibility with the simulation adapter and adds implementation version `1.15.1`. To simulate the fixed output, use:

```powershell
python simulate_draft_sources_v1_15.py --sources homegrown reconciled_consensus --integration "outputs/draft_source_integration_v1_15_1" --output "outputs/draft_source_simulation_v1_15_1"
```

A source with missing projected GS is still blocked, as documented in v1.15.
