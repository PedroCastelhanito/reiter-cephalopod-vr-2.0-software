# Live preview retest — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a plus dirty concurrent workspace.
Requested restart/dummy/toggle/header-drag verification under G01/E15.
Initial GUI absent but old runtime idle with cleanup confirmed; ordinary launch
attempt did not replace it. Authorized authenticated takeover shutdown succeeded
(old-shutdown.json), then fresh generation cad3278e-db30-4754-b200-3df65192f87a.
First Setup rejected nonexistent test output folder; created it and retry passed.
Session0777f33b-2b34-4bec-8e6e-ce614f3b6d16, SP0004-123249.
Saved50-minute protocol started12:33:09, manually stopped12:36:00 (~171seconds).
Both behavior/tracking recording selections retained, outputs preserved locally.

Native UI through sky: opened both camera previews and Stimulus; Video off removed
both cameras while Stimulus continued, Video on/reselect reopened both. Repeated
cycle after dragging divider from x851 to951 at1442x972: reopened cameras retained
x951 split. Images fill square targets without the obsolete caption reserve.
video-off.json confirms both preview_visible=false, preview_running=true;
reopened.json confirms both visible/running=true; neither snapshot has errors.
Screenshots video-off.png/restored-divider.png corroborate settled native layout.

Header dragging NOT verified: list_windows and list_apps expose Dashboard and
renderer but omit both blank-title camera windows. Manual check requested during
run; owner subsequently replied they cannot test now. No fabricated window handles or
synthetic UI drag pass. Prior isolated native hover/close geometry tests remain
separate evidence; live pointer dragging/Snap remains pending.

stopped.json: Configuration, cleanup_confirmed=true, no controller errors.
shutdown.json: normal ShutdownApplication succeeded; processes-after.json empty.
restart.stderr.txt subsequently reports MCU claim release unconfirmed because the
registered controller exited before Close RPC completed. Native bool_dealloc/
process-inspection errors from earlier run did not recur, but MCU shutdown warning
remains an unresolved finding, not clean end-to-end shutdown acceptance.
Original runtime_gui.json and last_configuration.json restored byte-for-byte.
No code changes or recording decode/full-workload/DPI acceptance in this increment.
