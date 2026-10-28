# Unprepared-session catalogue regression — 2026-10-28

Source base: e4dd8f2694aa075380fe6711a884fe5894763c6f plus existing dirty tree.
Input: owner screenshot/copied errors and emergency-1173345912101600 report.
Method: focused coordinator test with real ResourceObligationRegistry validation,
new session identity, prior coordinator revision0/12, worker revision25, exact
cleanup replay and retained-obligation rejection. Raw worker evidence and prior
revision stay unchanged. Before repair:1 passed/1 failed; revision12 reproduced
the exact first-catalogue rejection. Final suite output: [pytest.txt](pytest.txt).

Command (repository Python3.11):
```powershell
.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_coordinator.py tests/visual_stimulus/test_lifecycle.py tests/supervisor/test_registration.py -q -m 'not windows and not rig' --timeout=30 --basetemp=.tmp-unprepared-catalogue-final
```

173 passed,1 deselected. Initial two unbounded sandbox attempts were interrupted;
bounded15s attempt localized the hang to Windows asyncio socketpair creation,
before tests. Approved execution outside sandbox completed. Initial test formatting
check failed; formatted, final scoped Ruff check/format and Win32 mypy on
coordinator/reports.py pass. Boundaries:792 modules/zero violations; size advisory
reviewed in the owning report. No native renderer/device/optical acceptance,
watchdog root cause, application restart or successful failure/retry established.
