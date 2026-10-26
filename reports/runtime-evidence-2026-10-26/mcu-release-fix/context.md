# MCU shutdown-release fix — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a plus concurrent dirty workspace.
A11/E08: never infer claim release from controller exit. Root cause is a redundant
Close RPC from acquisition.main._close after acknowledged session cleanup cleared
the client's claim_id. Empty-claim close is now a no-op; failed RPC keeps claim_id.
ARCH-002: existing state, two-line guard; no policy/deadline/ownership change.

Validation using .venv/Scripts/python.exe:
pytest tests/acquisition/test_main.py tests/acquisition/test_cleanup_aggregation.py tests/acquisition/test_coordinator.py -q --basetemp .test-tmp-mcu-release-fix
156 passed0.34s with required permissions. Earlier default-temp invocation stalled
and was interrupted, not a pass. Ruff check/format source and owning test pass;
Win32 mypy microcontroller_client.py passes; boundaries760/zero passes.

Native saved-protocol session SP0004-124048; generation
1e622f82-a99a-469c-b116-af4fe84cd854; session b5f24f48-9c48-4af6-8ce6-b6da8a76d049.
Trial12:41:00–12:41:45 (~45s). running.json records Behavioral30Hz/Tracking60Hz
MCU output streams; stopped.json Configuration/cleanup_confirmed=true/no errors.
shutdown.json normal authenticated command succeeded; processes-after.json empty.
Final launch.stderr.txt has only launcher controller/supervisor EOF notices, no
MCU warning, process-inspection failure or bool_dealloc. Their older occurrences
remain independent unresolved findings; not claimed fixed by this guard.
Original runtime_gui.json/last_configuration.json restored byte-for-byte.
Output preserved; no full-duration, recording decode, electrical/DPI acceptance.
