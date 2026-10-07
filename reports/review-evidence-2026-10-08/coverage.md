# Portable test coverage, 2026-10-08

Command: `COVERAGE_FILE=<scratchpad> .venv/bin/python -m coverage run --branch --source=src/cephvr --omit='*/gui/*,*/v1/*,*_pb2*.py' -m pytest tests/{controller,supervisor,acquisition,visual_stimulus,tracking,launcher,client,platform,shared} -q -m "not windows and not rig"` with coverage 7.16.2 (added to the dev extras). Source revision: HEAD `e4c653c` plus uncommitted work; 1089 passed, 6 skipped, 5 deselected, 1 failed (see the note). Statement counts below are statements, not branches; the run also measured branches.

| Package | Line coverage | Statements |
|---|---|---|
| acquisition | 45.9% | 7547/16458 |
| client | 70.9% | 224/316 |
| controller | 70.2% | 6449/9186 |
| launcher | 66.2% | 470/710 |
| platform | 36.0% | 1132/3144 |
| shared | 73.7% | 2113/2866 |
| supervisor | 79.0% | 1780/2253 |
| synchronization | 67.3% | 686/1019 |
| tracking | 74.2% | 3534/4761 |
| visual_stimulus | 65.7% | 7869/11975 |

Local portable coverage is not rig coverage: native Windows, GPU and hardware paths run only on the rig (E15).

## Largest portable gaps

Process entry points and Windows launchers are expected to sit at 0% here (`acquisition/main.py`, `acquisition/worker/main.py`, `acquisition/worker_launcher.py`, `controller/startup/application.py`, `tracking/main.py`, `visual_stimulus/worker/main.py`, `visual_stimulus/feedback/native.py`); they need managed processes and belong to rig acceptance.

The notable gap is the acquisition worker runtime, which has no portable test of its own although it holds deadline, cleanup and report logic: `worker/execution.py` (326 statements, 0%), `worker/owner.py` (199, 0%), `worker/cleanup_lifecycle.py` (131, 0%), `worker/preview_lifecycle.py` (127, 0%), `worker/health.py` (109, 0%), `worker/report_dispatch.py` (77, 0%) and `worker/camera_resolution.py` (184, 7.7%). They need a fake camera adapter in place of the Basler adapter. Other low modules (under 15% line coverage, 60+ statements): `acquisition/coordinator/evidence_lifecycle.py` (215), `acquisition/recording/session.py` (261), `acquisition/camera/settings.py` (192), `acquisition/coordinator/session_payloads.py` (121), `acquisition/coordinator/incidents.py` (131), `acquisition/coordinator/evidence_operations.py` (128), `visual_stimulus/resources/video_index.py` (186), `visual_stimulus/resources/prepare.py` (106), `visual_stimulus/recording/encoding.py` (81), `tracking/methods/model_assets.py` (64). Some are covered indirectly in other runs or need native imports, so each needs a look before tests are written.

## Note on a flaky test (fixed)

`tests/visual_stimulus/test_transport.py::test_authenticated_setup_compiles_and_hands_off_exact_prepared_trial` failed once in this run and in 2 of 25 solo runs without coverage. Cause: a test race, not a product defect. The worker's transport returns the InitializeDisplay receipt at admission and the retained command runs afterwards on the GL owner thread (`shared/admission.py`: "the RPC is an admission boundary"), but the test asserted the announced display resource immediately after the receipt. The test now waits (bounded) for the resource; it passed 120 of 120 solo runs afterwards.
