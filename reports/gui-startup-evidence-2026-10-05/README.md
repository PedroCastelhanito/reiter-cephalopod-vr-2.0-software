# Managed GUI startup probe — 2026-10-05

Source: `fe1825f` plus uncommitted GUI and backend work in this checkout.

- Method: ran `.venv/Scripts/python.exe scripts/start_runtime_gui.py` from the
  repository and repeated it with process observation and redirected stderr.
  No Setup, camera capture, output test or session command was issued.
- Initial result: the inherited DACL on
  `C:\Users\ReiterU_PC\AppData\Local\CephVR\runtime` was rejected by
  `verify_owner_only` in both controller and GUI. `icacls` showed inherited SYSTEM,
  Administrators and user ACEs. The repository's `ensure_owner_only` helper repaired
  that exact directory; `verify_owner_only` then passed.
- The first post-ACL launch created supervisor, controller, acquisition, Visual
  Stimulus, Tracking, GUI and renderer processes, then lost the renderer first.
  [Initial stderr](managed-launch-stderr.txt) contains secondary shutdown errors.
  Timing traces isolated the first rejection as `INVALID_HEARTBEAT: lifecycle and
  sender time are required` ([worker trace](heartbeat-trace.txt)). After the worker
  supplied a configuration phase, the coordinator's idle aggregate still sent an
  unregistered cleanup catalogue revision; the supervisor rejected it as
  `UNKNOWN_CATALOGUE` ([peer trace](peer-timing.txt)). The temporary timestamp
  adjustment and all diagnostic print instrumentation were removed.
- The worker now supplies a lifecycle phase for initial and resource heartbeats;
  the coordinator forwards it and only forwards a cleanup revision after Setup
  registers a session catalogue. In the final bounded live observation, all managed
  roles remained alive for more than 25 seconds and the GUI had a real
  `CephVR2.0 — Dashboard` window. Repeated renderer heartbeats were accepted
  ([final trace](process-order-stderr.txt)). A separate offscreen managed GUI
  construction inventoried two cameras and two COM ports.
- Closing the diagnostic GUI did not end its launcher in the next 30 seconds,
  consistent with E08's intentional GUI-closure behavior. After
  verifying its exact process command line and that no Setup or output command had
  occurred, the diagnostic launcher was terminated and its Windows Job closed;
  a subsequent process query found no managed launch processes. This bounded
  startup probe does not verify a full session, physical outputs or authorized
  application shutdown. A later attempted second launch was rejected by the
  application guard because one diagnostic launcher tree still held the mutex.
  Its exact process identity and ancestry were verified, then it was stopped;
  the application mutex became available. An intermittent `QueryFullProcessImageNameW` access error was
  seen in an earlier run ([trace](primary-trace.txt)); it did not recur in the
  successful observation. See [the current runtime report](../runtime.md#dashboard-frontend-implementation).
