# Native GUI audit observations — 2026-10-27

Baseline source a28ed144 plus the three behavior-preserving cleanup files.
Managed launch: `scripts/start_runtime_gui.py --no-tracking`; controller
e6bd99f1-bd74-4dda-baa2-da5116be09b7. Root Computer Use interaction at1442x972;
screenshots were inspected inline. This is a bounded interaction record, not
exhaustive acceptance of every control, state, DPI or physical output.

| Area | Actual interaction/observation |
| --- | --- |
| Dashboard | Configure/Monitor navigation; Video Off/On; individual Behavior/Tracking Show; Advanced Off/On; Combined/Per-projector mode; Left projector toggle Off/On. Native previews return after individual Show. |
| Protocol | Opened page/category selector and dismissed without classification changes. Trial preview Open/Play/Close worked with saved texture content. |
| Cameras | Opened role selector with all four roles; selected existing Behavior assignment. Connect all succeeded for40065509/40747103 with configured settings. Monitor source readouts30/60fps and preview readouts approximately20fps. |
| Microcontroller | Opened tab and Test connection; COM8 protocol6/cephvr2_uno_6 verified, outputs stopped. No upload or output-test pulses invoked. |
| Projectors | Opened Geometry, Calibration and Synchronization subsections; scrolled Calibration. Four output mappings visible. Calibration/brightness/photodiode values not changed. |
| SpikeGLX | Inspected connection/input tab. No remote command or pairing mutation. |
| Tracking | Opened Preprocessing, Calibration, Pose and Motion. Backend unavailable in this explicitly no-Tracking launch; no scientific processing or calibration edits. |
| Styles | Amber initial, Standard then Retro; navigation and camera viewers inspected. |
| History | Control menu/Review controller history opened and dismissed. |

## Findings and limits

- Per-projector polar plots show lower-axis/status text overlap in Standard/Retro
  with two camera cards. Source fix moves the existing footer below the axis label;
  six offscreen cases check non-overlap and clipping across three themes/two sizes.
- Camera windows remain visible over Configure and Protocol after leaving Monitor.
  This persists after settling and after opening/closing Trial preview. No manual
  camera-window move occurred. Existing native owner sees the still-visible main
  HWND; Qt slot hiding does not suppress it. Contract/authority review is pending.
- Tracking image is black; the configured scene/illumination cause is unresolved.
  Source readout and image presentation do not establish useful scene content.
- Two attempted edge drags did not resize the application; no alternate-width or
  alternate-DPI native pass is claimed.
- Initial capture approval timed out. Refreshed selection and activation worked.
  After fresh controller e498a719 launch, activation timed out twice; no native
  visual retest of the plot fix is claimed. No stale coordinates were used afterward.
- Firmware, calibration edits, remote paired acquisition, destructive controls and
  Tracking processing were excluded. Load/recording results are separate evidence.

The full offscreen GUI suite passed1085 tests before the footer fix; six focused
final-source cases pass. These checks do not imply every GUI element was clicked.
