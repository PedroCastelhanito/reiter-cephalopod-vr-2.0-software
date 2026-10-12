# GUI client

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

GUI navigation, connection and control rules. The controller remains authoritative;
the GUI is a client.

Related: [controller authority](experiment.md#e02),
[process startup/shutdown and state transport](system-contracts.md#e08).

Configuration: [gui_config.toml](../../config/backends/gui_config.toml).

## Decisions

<a id="g01"></a>
### G01 — GUI navigation and settings ownership

**Status:** Accepted · **Revision:** 162

- Projectors/Synchronization uses a two-row Frame/Pulse table with Origin X,
  Origin Y, Width and Height in pixels. Frame origins use bottom-left output
  coordinates; Pulse origins are relative to the Frame. Both dimensions are
  independently editable, and the Pulse must fit wholly inside its Frame.
  Complete rectangles must fit their assigned output at submission/Setup.
  Retain unfinished draft fields without inline errors. Portable full files version 7
  save these fields by logical face; version 6 square Size migrates to equal Pulse
  Width/Height, and older standalone markers retain their original rectangle until
  Pulse fields are supplied. An independent Blackout zones table provides
  Screen/X/Y/Width/Height and Add/remove; hide its header when empty and refit after
  Add/remove and restore through the shared table rule. Planning preview shows final-space
  black regions and a white pulse as placement, never optical timing.
  V15/V19/V22 own final composition and trial/Idle behavior; both GUI modes share controls.
- Review and managed runtime use the same DashboardWindow page construction,
  shared cards, fields, navigation and responsive layout rules. Mode-specific wiring
  supplies local fixtures or authoritative state and command availability; it never
  adds a separate page layout. Review-only inspection menus and runtime authority
  actions retain their distinct purpose. Older saved review drafts migrate through
  the owning validators without discarding valid settings or changing source files
  during load; genuine invalid drafts remain preserved and explicitly reported.
- Tracking derives its input from the unique camera assigned the Tracking role in
  Devices; no second source selector or discovery-order fallback. Its pipeline card
  precedes Preprocessing, Calibration, Pose and Motion subtabs, with the shared
  fixed HUD/log column and independently scrollable settings. Preprocessing drafts
  input crop then isotropic downscale; Calibration owns the image-plane distance
  reference after T20 anatomical points; Pose places T16 search region before
  T05/T06 controls and sampling geometry; Motion owns optical-flow, estimator and
  always-expanded flow quality controls. Fresh drafts default to Water flow and
  Manual pose; show the fixed NVIDIA OF method explicitly.
  Show only applicable method fields and retain separate water/fin analysis drafts.
  Camera settings, recording and stimulus gains keep their existing owners.
- The local Tracking frontend supports draft Load/Save as and a detached reference
  image annotation tool. Input crop and pose-search rectangles support synchronized
  integer X/Y/Width/Height fields in original camera pixels. Keep overlay visibility
  separate from these configuration controls; no Draw region buttons.
  Distance endpoints, anatomical references and manual landmarks have named, editable
  source-pixel X/Y rows synchronized with drawing; incomplete coordinate edits retain
  the committed annotation. Two distance endpoints and a positive known length derive
  source-image px/mm and mm/px independently of downscale, required for enabled
  Tracking/locomotion diagnostics under T20. T38 declares mm/s and deg/s outputs;
  gain controls show mm/mm and deg/deg. Source/image changes invalidate annotations;
  missing/ambiguous/disabled Tracking assignments remain visible in the HUD.
  Subject reference places Set points and Clear together on the left; Clear removes
  only anatomical references. Local documents migrate older draft formats without
  inventing calibration. Hide uncalibrated scale and output-size captions. Manual
  pose uses a content-sized form with Set landmarks aligned left above the shared
  coordinate table; method switching retains each method's settings.
- Tracking stage switches apply only to pre-experiment configuration, preview and
  diagnostics. Label them Enable. Pose, sampling region, optical flow, flow quality
  and locomotion default enabled; disabling a stage retains its parameters.
  Preprocessing has only its existing Enable crop and downscale controls, without
  an additional stage switch. Store diagnostic-stage choices separately from
  experiment settings. Experiments requiring Tracking run
  every required stage of the selected T02 pipeline regardless of diagnostic switches;
  optional crop/downscale and method settings retain their meaning. Older drafts
  migrate with all diagnostic stages enabled; discard the obsolete preprocessing
  diagnostic flag while retaining crop/downscale settings. T08 owns selected-stage
  availability and the image/preprocessing-only empty-mask path for first annotation.
- Tracking edits follow authority/session locking; no new participation toggle.
  Diagnostic Begin sends a separate bounded typed local draft against the accepted
  camera/configuration revision without publishing experiment settings. Encode only
  runnable selected inputs; retain dormant incomplete fields locally. Changes to
  active diagnostic settings require confirmed Close and fresh Begin. Ordinary
  experiment submission remains strict under E07; annotations stay local until
  accepted. Preserve T01/T20 acquired-image lineage and coordinates.
- Managed session submission retains optional species, sex, age in dph, size in mm
  and condition beside subject/experiment identifiers. Absent values remain absent;
  numeric age is finite and nonnegative and size is finite and positive. E07 owns
  validation, stale-revision rejection and persistence; incomplete local drafts never
  authorize Setup with different accepted settings.
- Main navigation orders **Dashboard, Protocol, Devices, Tracking**. Protocol owns
  session mode and V02/V03 stimulus programming. Protocol type with Load/Save as sits
  left of one Assets folder (E07 root); narrow windows stack the pair. Dashboard owns
  camera/stimulus video recording and Tracking velocities in a Recordings card below
  Session config, using two columns with each checkbox beside its label. Assets are prepared externally. Tracking participation follows
  E10 without a Protocol status indicator; required acquisition/rendering is independent
  of optional video recording. Device controls stay in Devices.
- Cameras, Protocol, Microcontroller, Projectors, SpikeGLX and Tracking own reusable JSON
  Load/Save as controls; sidebar controls compose a full GUI snapshot including
  Dashboard metadata, camera drafts and recording choices. The
  [snapshot contract](../../contracts/gui-configuration-files.md) owns formats and
  inventories. Validate all sections before restoring local drafts, save atomically,
  preserve unset/dormant settings and close choosers on authority loss. Full files
  retain explicit rig identities and require matching inventories; projector-only
  files remain portable under the calibration contract. Loading starts no device,
  uploads no firmware and restores no runtime status, ownership or credentials.
  E07 submission/Setup validates runnable settings; loaded camera/MCU drafts survive
  polling and enter the normal configuration proposal. SDK PFS import remains A10-owned.
  Inactive loaded Tracking drafts stay local until required. SpikeGLX files restore
  editable pulse rows without a separate Save pulse mapping button; GUI Save/Load
  persists drafts without writing the controller inventory. E12/E14 startup host/pairing
  values are informational references and retain their owning TOML authority.
- Protocol uses a widened Trials column beside a persistent Trial timeline, with a
  full-width Sequence editor below. Trials and timeline use matching top borders,
  title heights and a taller shared minimum card height (320 logical pixels). Trials
  provides a selectable scrolling list: show × only on hovered rows and a +
  immediately below the last row, reachable by scrolling. Remove the separate
  bottom Add/Delete toolbar. Deletion confirms the targeted trial, preserves saved
  files and replaces the final deleted trial with a blank trial; retain edit authority
  and pending-draft checks. Omit Seed/Gap controls and the Selected trial section;
  preserve loaded seeds and legacy gaps under E01/E07. Setup retains seed ownership.
  The overview shows direct source epochs and collapsed canonical groups in sequence
  order, with name, duration and group repetition/occurrence totals. Blocks have a
  readable minimum width and horizontal navigation; paint only visible blocks.
  Matching epoch content shares an authoring color, never a serialized epoch type.
  New GUI trials contain groups only; each group contains source epochs only.
  Sequence editor opens directly on the first epoch when a supported trial is created,
  loaded or selected; clicking a group selects its first epoch. No Trial breadcrumb
  or back level. Match trailing + heights to their trial row or epoch block.
  Put a trailing + after the final group and subgroup blocks;
  group addition appends one blank epoch in a new group, while subgroup addition
  copies the current editor template. Immediately select the new block. Show a ×
  only at each hovered group/subgroup top-right; subgroup deletion removes
  all its source members. Preserve at least one group and one subgroup per group,
  showing the final delete action disabled. Keep Preview in the header, removing
  the separate + Group, − Group and + Epoch controls. Reuse draft validation and
  Undo; inline actions respect edit authority and remain reachable by horizontal scrolling. No nested-group creation or Group selected/Repeat-vary action is exposed.
  Existing imported programs are preserved verbatim; unsupported legacy structure
  is inspectable with creation controls unavailable, never flattened with an invented
  shuffle seed. Canonical/headless V08 nesting remains supported.
  Place the selected group name and repetitions inside the timeline card above its
  blocks, keeping the Sequence editor for subgroup controls. Balance card spacing
  without duplicating these fields. Omit Order and preserve imported ordering.
  Protocol removal buttons (trials, groups, subgroups and variation rows) appear
  only while hovering their item, use the same compact × button role as MCU signal
  tables, and reserve enough space for centered glyphs and consistent insets.
  Timeline duration labels use hh:mm:ss, retaining fractional seconds when present.
  Layer selectors use a narrow index-only column with descriptive tooltips. Subgroups are
  separately identified batches of flat source epochs, using V03 authoring metadata;
  equal labels do not merge batches. Clicking a batch header or any member selects
  the complete subgroup; parameter edits affect all members and parent-group repetitions.
  Group contents show compact source blocks; projector details live in the unified
  form without a second summary grid. No widgets/images are allocated for repeated occurrences. Keep horizontal block scrolling and page-shell form
  scrolling, responsive controls and centered count/duration totals. Shift/Ctrl/Command
  select source epochs within the group. No trial table, HUD/log, draft badge or
  standalone Validate action is introduced.
- The design-review launcher uses simulated cameras, projector displays and a
  microcontroller inventory; review actions send no device commands. Its optional
  real-device inventory mode opens no COM port; physical pin tests and firmware
  operations use the managed controller API. The managed
  runtime launcher starts the controller-backed GUI and discovers attached Basler
  cameras, secondary Windows displays and COM ports without assigning surfaces or
  claiming Setup readiness. Camera
  refresh preserves drafts by serial. Test selected checks the exact assigned camera
  without enabling it or
  starting capture/pulses, preserving prior ownership. Camera roles include Eye
  tracking for third-camera preview/video only; its external trigger remains pending
  under A01/A11, while the unique Tracking role still owns locomotion input.
  Display refresh preserves local assignments/participation. Explicit
  test fixtures may still supply simulated displays for isolated frontend checks.
- An assigned camera's Use flag may be enabled or disabled regardless of its
  current device, trigger, PFS or recording settings. Commit participation-only
  edits under E07 without applying hardware settings. Control/ownership and session
  locking still apply; capture and Setup enforce their complete configuration gates.
- Local design review saves its editable draft state atomically on normal close and
  restores it after inventory discovery on the next review launch. Match camera and
  display drafts by stable identity; an absent device stays unavailable. A failed
  save offers Retry or Close without saving; an unreadable previous draft is warned
  and preserved unless the operator explicitly replaces it. This local review draft
  never becomes the controller's E07 accepted configuration or authorizes Setup.
- Sequence editor has one subgroup form, reusing the reference composer and numeric
  variation controls with per-projector layers and parameters. No Generate/Edit tabs,
  target filters, duplicate epoch inspector or batch selector. Stimulus mode, Duration,
  and Name share a responsive row; Apply/Discard follow the form. Group repetitions
  alone repeat the full sequence, equally for all epochs; no subgroup Copies control.
  Omit epochs-per-repetition, one-repetition, edits-apply and footer count helper text.
  Selecting a subgroup populates its first source template; unchanged parameters
  retain each member's existing values. Explicit variation rules replace the selected
  subgroup's pattern; retain active rule controls after Apply, selection
  changes, Undo and file reload. Save rules as V03 authoring metadata alongside concrete
  settings; unchanged rules do not resample on unrelated edits or Apply.
  The trailing subgroup + copies one current template, independent of variation rules; valid
  pending edits are applied first. Invalid input stays visible and prevents mutation.
  Changing selection or saving requires Apply/Discard; Undo first discards a draft.
  Apply atomically validates the whole trial, preserving source identities and
  unrelated epochs, projector settings and shared declarations. Incompatible layer
  layouts reject a bulk composition edit without changing the subgroup.
  Validation follows G02 action-time warnings. Focus changes and reference preparation
  remain quiet and retain invalid drafts. Loss of editing authority closes file
  pickers and disables forms. Fixed durations retain exact fractions; imported
  variable durations are preserved. Projector-local changes use copy-on-write.
  Show each enabled projector's selected layer, prepared asset filename and
  stimulus-specific parameters in one compact row; full paths remain on hover.
  Omit the Projector heading and display Looming as the short family name. The
  stimulus dropdown resets the selected layer's asset when changing family;
  incomplete choices remain drafts and block Apply and + Epoch.
  Share column headings, repeating parameter headings only when meanings or units
  change; reserve equal heading space to keep projector rows evenly spaced. A Layer
  dropdown per projector selects the visible asset/parameters; its ordinal follows
  stack order. Prepared asset paths can be copied and pasted between projector rows;
  pasted paths resolve within the Assets folder and use the same validation as file
  selection. Successful file selection leaves no status line. Layer management and
  advanced settings use the row menu: Add layer, Remove layer, Move layer with
  Move up/Move down, and a checkable Advanced settings action. Disable unavailable
  moves at the local layer boundaries. Add layer creates an empty local slot
  without opening a stimulus picker; choose its family and prepared file afterward.
  Reserve the advanced linking/fade row’s minimum height after narrow reflow.
  Keep canonical settings per instance/projector when switching layers. Empty slots
  are editor drafts, excluded from generated programs and runtime delivery.
  Image rows expose Fit (Contain/Cover/Stretch), Move speed and Direction; zero
  speed is still. Initial position and whole-image rotation sit in Advanced settings.
  These edit existing 2D object motion, never texture phase. New Images use Contain;
  omitted legacy fit keeps Stretch under V04. The editor offers a Fit dropdown;
  numeric variation excludes Fit. Fitting precedes the existing geometry/calibration
  pipeline in both the planning preview and renderer.
  Stimulus mode, Duration (hh:mm:ss) and Name share one row at wide
  widths, with widths reflecting their values; narrow widths wrap. Leave extra
  separation before stimulus rows. Arena mode omits the redundant type selector and exposes Longitudinal/Lateral/Angular
  movement toggles and signed gains under V24 (zero gain disables an axis). Keep
  imported programmed motion and custom feedback unchanged unless explicitly edited.
  Tracking channel conflicts reject the edit.
  Advanced settings occupy one shared-style card beneath the selected projector
  row, with its left edge aligned to Layer. Retain state is first when relevant;
  Linked to and fade-in/out durations follow, then control entries. Video hides
  Retain state and Linked to; 3D arena hides Retain state; Looming hides Linked to.
  Other edits preserve loaded Video/arena reset values, with Video playback
  continuity owned by V07/V09.
  New GUI-created stimuli retain
  state by default (reset false); loaded explicit reset values and boundary
  assignments remain unchanged. No opacity editor: new stimuli use a constant base
  opacity; fades are ordinary V05 linear opacity keyframes, defaulting off. Preserve
  imported custom opacity functions rather than flatten them; simple fade authoring
  requires a fixed duration and a recognizable constant/envelope. Reject negative,
  nonfinite, sub-nanosecond or overlapping fade durations atomically. Explicit GUI
  duration changes retain standard fade-in/out lengths and move fade-out to the new
  epoch end; durations too short reject the edit. Linked to remains disabled until
  V02's source/target feedback ownership and complete runtime contract are settled.
  + Control sits below the settings/entries inside Advanced settings, available only for Texture
  and Looming with Closed-loop selected. Hide its action while a Control draft is
  being configured; show an entry only after Add control commits, and restore the
  action on commit or cancellation. Edit its draft in a separate dialog rather
  than expanding the projector row. Offer Tracking's Longitudinal, Lateral and
  Angular velocity channels; no free-form input definition. The 2D screen conversion
  is Open and cannot be inferred from body-relative inputs; disable committing an
  unsupported mapping. Preserve imported bindings/functions and existing arena
  axis controls; removing an entry does not erase declarations another epoch uses.
  Control validation remains atomic; Cancel changes neither declarations nor mappings.
  Stimulus mode selects Per-projector stimuli or 3D arena; retain
  the other mode's draft while generating only the selected mode. Keep projector
  edits independent and retain inactive-projector content. Narrow windows stack
  the same controls with labels.
  Optional variations use one shared-style card with an always-visible Add variation
  rule button and no Enable checkbox. Added rules are active; removing the last rule
  leaves only the add button. Do not activate legacy disabled drafts on load.
  Rules share table columns for Projectors, Layer, Parameter, Method, Values / range
  and hover-only removal. Keep Layer narrow, reserve full control widths and align
  cells across rules. Values / range grows on wide windows; the table scrolls
  horizontally on narrow windows without widening the page. All projectors covers the enabled reference screens and
  offers common layer ordinals; explicit missing/stale targets reject generation.
  A selected local ordinal maps to the corresponding canonical instance on each
  projector; isolate shared 2D instances for independent values. Accept explicit values or bounded min/max/step
  sweeps, or Random for numeric parameters. Random shows Minimum, Maximum,
  Precision (positive value step), with an unchecked Share random values across projectors
  option. Independent target draws are the default; sharing explicitly reuses one list.
  No manual resample or count field. Without a fixed list, draw for every existing
  subgroup source epoch (one for a new subgroup). With paired Values/Sweep lists, materialize the
  ordered source pattern once. Draw independently for each subgroup occurrence and
  projector across all group repetitions; independent draws may coincide by chance.
  Keep source blocks and saved V08 seeded rules compact, without an occurrence-count
  limit in subgroup authoring. Resolve only representative values for editing; changing
  repetitions preserves existing seeds and the sampled prefix. Explicit source-list
  generation and expanded previews retain their separate bounds; Setup checks its
  configured expanded-plan limit before allocation.
  Draw uniformly with replacement from multiples of the precision inside inclusive
  bounds; reject invalid/nonfinite ranges or an empty precision grid. Persist controls
  and seeds; edits to range, precision or targets create a new seed. V08 resolves
  executable rules at Setup, independently of order/duration seeds; rendering never
  samples. Retain legacy concrete repetition tables when loading existing programs.
  Pair rules by value position with equal list lengths, without Combine. Explicit
  Values remain in entered order. Parameter choices share
  the selected stimulus columns and captions, including units: Rotation replaces
  Angular speed in the UI, without changing its canonical key. Exclude Width, Height
  and Opacity. Mixed targets offer only compatible common columns; unsupported
  targets reject generation. Video At end accepts ordered categorical values, without
  a numeric sweep. Validate the resulting sequence on Apply. Materialize variants as
  flat canonical source epochs edited together through their subgroup.
  No Shuffle trial action is exposed; group-order and Setup seed ownership remain unchanged.
  Store optional batch labels and distinct generated-batch identities under V03.
  The trailing + appends a new subgroup; Apply changes the selected subgroup in place.
  Hide the older insertion/replacement controls in this workflow. Bound each generation to 2000 epochs without charging
  existing group repetitions against that source-list allowance. Validate the assembled trial
  atomically; cancellation, invalid settings or failed insertion leave it unchanged.
- Trial timeline has a Preview action opening a separate modeless planning window
  showing stimuli on a single rotatable 3D tank/screen view, following CephVR1.0.
  Use Devices screen placement and subject geometry. Enabled projector faces show
  their content from either side, without back-face culling; inactive faces retain
  dim outlines. Omit the planning-description banner, enabled-projector legend and
  subject marker; retain the subject position for projection math. Label visible screen identities,
  drag to rotate and double-click to reset. The initial/reset view places the rig
  Left plane to the left of Right in the image, without swapping face assignments
  or reflecting calibration. Paint screen faces from far to near in view depth.
  Snapshot the authored trial, rig geometry
  and current screen calibration. After surface composition, apply the exporter's
  shared per-face scale, pixel offsets and axis inversions. Normalize pixel offsets
  by the assigned display resolution, never the reduced preview image dimensions.
  Blank correction fields use the same identity defaults as calibration export;
  nonzero offsets without an assigned resolution or invalid/out-of-bounds corrections
  show a per-screen error rather than an uncorrected output. Retain geometry/corrections
  independently of projector enablement. Reopen the snapshot after changing settings;
  provide Play/Pause, scrubbing, previous/next epoch and playback speed. Reuse V07
  boundary state/retention and canonical expansion with an explicit example seed;
  reject unresolved random durations. This preview sends no device commands, applies
  no live Tracking and does not establish optical/runtime equivalence. Label unset
  geometry with a Devices configuration prompt rather than inventing tank dimensions;
  arena rendering remains approximate. Missing
  or unsupported content remains visible as an error, not silently substituted.
  Load assets on demand with bounded caches and arena complexity, release inactive
  video decoders, stop playback work when paused, and release resources on close or
  loss of editing authority. Keep this separate from managed backend-owned viewers.
- Cache source paths/content keys and aggregate counts/durations by immutable program
  identity and scope in a bounded four-view cache. Selection does not expand repetitions
  or rebuild the trial; unchanged metadata flushes preserve program identity. Keep the
  existing 2000-occurrence bound for explicit expanded/animated previews and source-list generation,
  without applying it to the compact overview. Do not decode assets for timeline blocks. GUI JSON reads/saves use the existing shared
  16 MiB engineering default guard; managed Setup's configured limits remain
  authoritative. Local measurements do not establish Windows/full-workload capacity.
  To fade only the first independently generated source epoch, generate with zero
  fades then select that source and use Batch edit / All parameters. A repeated source
  affects every occurrence; use a separate introductory source outside the repeated
  group when only the first occurrence should fade.
- Batch edit places Epochs and Parameter selectors on one row. Duration is a single
  epoch-wide value without projector or layer controls. For stimulus parameters,
  each projector has its own layer selector and value field or prepared-file picker;
  the rig-wide arena has one row. The parameter dropdown lists supported values in
  the selected epochs. Common values are shown directly and differing values as Mixed;
  only edited projector rows change on Apply. Shared duration, prepared file, applicable
  motion/playback, opacity and simple looming size controls support batching. Missing
  targets or invalid values reject the entire operation; no silent partial application.
  Pending batch changes block target/selection changes and saving until applied or
  discarded. All parameters opens the complete single-source editor, retaining custom
  functions, state, feedback and input declarations. Replace Placement controls with
  an Opacity override; preserve loaded placement/dimensions without exposing edits.
  Local field-completion edits there keep existing validation; untouched imported values are preserved.
- All mutation controls belong to Sequence editor, including naming, duration, layer
  management and structural controls. A first projector-local edit detaches a shared
  2D instance while retaining other projectors' identities, settings, assets and stack
  order. All projectors supports shared edits; arena remains rig-wide under V02.
  Disabled targets retain content/geometry and are labeled inactive. No enabled
  outputs shows a neutral lane for offline authoring. Epoch timing is shared across
  projectors; different boundaries remain separate epochs. No embedded rendering.
- Existing repeat/condition groups remain editable after canonical JSON reload;
  preserve child-block versus condition-row semantics, complete settings and V07
  continuity. Renaming a group also remaps its condition references. Structural
  duplicate/reorder/remove act on one source block; epoch rename acts on one source epoch;
  multiple-source changes use the explicit batch editor. The timeline exposes
  content-sized + Group, − Group and Preview buttons; group duplication/reordering
  remains in the context menu.
  Keep their natural label widths at the right. At narrow widths
  these actions sit below the title to avoid clipping. Ctrl+D and Backspace shortcuts
  respect the same selection/authority guards and preserve Backspace text editing;
  group actions target the overview, while epoch actions target group contents.
  The subgroup form omits the selected-epoch count line. Undo/Redo use
  Ctrl+Z/Ctrl+Y (with native macOS equivalents), without menu or toolbar entries.
  Protocol Load/Save as validates complete schedules with canonical trial programs,
  mode, asset root, seeds, gaps and arena boundaries; canonical single-program import
  remains supported. Trial deletion confirms the named local draft, preserves saved files
  and leaves a blank draft if deleting the last. Trial drafts are local documents,
  not an accepted session schedule until managed submission. The managed Trials list
  submits the explicit ordered session schedule under E01, preserving canonical
  program sources and optional seeds; gaps bind after their trial with no final gap.
  Expanded sequence inspection has an explicit Close action;
  Setup retains the final seed/order. Invalid mutations preserve the last valid program.
- CephVR1 texture designs resolve an existing exported PNG plus declared tile dimensions
  into canonical V03; missing/invalid companions fail without synthesizing appearance.
  File replacement is epoch-local and E07 root-relative. Omit texture-design controls;
  expose speed/direction/angular speed, opacity, playback, retain-state and feedback.
  Preserve imported canonical motion functions without flattening them. Managed application, session-setting persistence and scheduling
  remain unfinished; local authoring is not Setup readiness.
- Devices groups camera, microcontroller, SpikeGLX and projector/display hardware
  configuration and supported connection/output checks into device-specific sections.
  Tracking methods,
  subject landmarks and analysis geometry belong to Tracking. Each setting has one
  editing home. Devices orders its icon subtabs Cameras, Microcontroller, Projectors, SpikeGLX.
  Each Devices tab places Load/Save in its own Configuration file card immediately
  below the device tabs, before device connection and settings cards. Cameras then
  stacks Available devices above Camera config in the left column, with
  its HUD/log column at the right. The inventory provides experiment enablement,
  stable identity, role, selection, refresh, connect/disconnect and external preview.
  Selection restores each camera's saved PFS, timing source and rate; the PFS field
  shows a filename with its full path in the tooltip.
  Camera and Projector inventories share a compact Refresh icon in the header's
  upper-right corner, a first Use column and single-row selection. The shared
  capture action reads Connect when closed and Disconnect while capture or an
  editing connection is retained. Review simulates these states locally. Camera config omits
  the redundant selected-camera caption; identity remains in the inventory/HUD.
  The Devices footer has no draft-settings text; local fixtures remain identified
  in the review window title and activity messages.
  Inventory actions are ordered Test selected, Connect/Disconnect. Test selected
  checks only the selected assigned camera, including a disabled camera, without
  changing experiment participation, capture or existing ownership. Managed
  role assignments commit through E07 and leave the newly assigned camera disabled.
  Connect starts A10 manual capture and then Shows its acquisition-owned OpenCV
  window for the confirmed run; Disconnect stops capture and releases preview. Native X closure leaves capture running; backend
  visibility evidence updates the GUI selector. Show snaps the visible preview frame
  outside the GUI's top-right edge, shrinking the square to available right-hand
  space before using the left edge; clamp to the current monitor work area when
  neither side fits. Use physical visible-frame bounds without a tool-window gap
  or invisible resize borders. Reopening samples the current GUI position;
  an open window remains freely movable. A10 owns padding and wheel zoom/reset.
  The GUI owns no camera display reader. Disconnect releases an
  editing/cleanup owner when no capture is running. Camera/pulse settings remain
  locked while a camera is owned until E07 live-edit adoption is implemented.
  Pending commands lock repeated submission; failures remain visible and queued
  intents are discarded on controller disconnection. No Setup readiness is claimed.
  Camera config exposes role, an Internal clock / External controller dropdown, requested
  external trigger frequency and a PFS parameter-file path with Browse. Preserve
  per-camera drafts and unique roles; selection/connection never enables a camera.
  Detailed camera parameters are edited in PylonViewer and supplied through PFS;
  the GUI has no exposure/gain/ROI/pixel-format editors or PFS export controls for now.
  Trigger frequency edits the camera's requested A11 pulse rate, not a free-running
  frame-rate override; Microcontroller retains board/port/pin ownership. The asynchronous
  PFS picker selects an existing file, preserves cancellation and rejects late results
  after camera selection or editing authority changes. On selection or completed path
  editing, inspect the PFS FrameStart snapshot (bounded to 1 MiB) to populate the
  dropdown: TriggerMode Off is Internal clock; On with a Line source is External
  controller. Retain the exact source separately; missing, ambiguous or unsupported
  values leave the choice unset with an explanation. This offline hint does not
  apply or validate camera settings: A10's SDK import/readback remains authoritative.
  Changing the path clears stale hints. Omit Save camera settings: managed clients
  submit completed rate edits, explicit trigger selections and successful PFS hints
  through the controller configuration request. An explicitly selected PFS with a
  usable hint additionally performs A10 SDK import/readback and signals editing
  completion; retain the resulting baseline without reimporting on later rate edits.
  A filename without an imported baseline cannot start capture from this GUI.
  Import does not enable a camera for experiment. Snapshot loading is silent;
  incomplete hints remain drafts. Require Configuration/control and controller
  confirmation before treating any change as applied.
- Managed MCU connection/pin tests use controller-confirmed COM/pin/rate values.
  Pending commands lock edits and repeat tests. A11 diagnostic observations drive
  Test/Stop state; a bounded follow-up status query begins after confirmed execution,
  and control/connection loss cancels local timers. Firmware/edge reports do not prove
  physical receiver wiring.
- Microcontroller owns one selected COM port for all camera triggers; Cameras has
  no controller/port selector. COM discovery uses the shared compact Refresh icon
  beside the port selector, distinct from Test connection. Scan ports lists discovered COM-number names with
  the available device description, preserving the port identity separately and
  a still-present selection without opening devices. Do not expose
  macOS/Linux serial device names or invent a second controller in the draft.
  Inputs precedes Outputs. Add input/output and row removal select only supported
  signals. Hide empty signal-table headers (MCU Inputs/Outputs and SpikeGLX channels),
  releasing their height; restore them when rows are added or loaded. Inventory
  headers retain Refresh when empty. Supported choices are Projector flip input;
  Trial state and uniquely assigned Behavior/Tracking
  camera outputs. Each row has a supported-signal dropdown, pin, Test/Stop and remove
  action; no free-form signal, behavior selector or duplicated camera rate. Prevent
  duplicate active signals. Removing disables the signal and hides its row, retaining
  its pin for Add and file round-trips. Camera enablement shares Cameras' experiment
  participation; adding/removing a camera output enables/disables that camera. Eye
  triggering retains A01/A11's pending integration. Fixed input/output enablement is
  retained draft configuration in isolated review. Disabled signals cannot start tests
  or participate in pin conflicts. Add/remove/reassignment obey editing and diagnostic
  locks. Omit Save pins and Apply pin settings: managed clients submit completed pin
  edits, selected COM ports and
  fixed I/O enable changes through the existing controller configuration request.
  Inventory refresh and saved-state loading are silent. Lock managed edits during
  diagnostics; connection/pin tests still require confirmed configuration.
  Disabling a signal stops its active diagnostic; editing authority gates enablement.
  In the explicit local real-device diagnostic mode, Test connection and per-pin
  Test/Stop use A11's exclusive
  serial owner and firmware-bounded diagnostics. Display matched connection, start,
  stop and edge-count evidence or the actual failure; a command request alone is not
  a pass. Input tests listen without driving. Lock port/scan and pin editing during
  a diagnostic, stop on phase/control loss and close the port on window closure.
  Isolated frontend fixtures retain labelled, command-free review tests.
  Fixed active-high Trial state and
  rising-edge Projector flip behavior belongs to A11; no level/edge selectors remain.
  Camera test rates are read from Cameras rather than duplicated here. Output tests
  target one pin for observation in SpikeGLX; the input test observes rising edges,
  never drives the input pin. Test requests require Configuration/control, a COM port,
  a nonempty pin and no target-pin conflict; camera requests additionally require an
  enabled external-trigger role and valid retained rate. Managed diagnostics retain
  controller ownership; report requests without matched results as unconfirmed.
- Projectors uses a compact table of Display ID, Projector assignment, Resolution
  in pixels, plus a scaled Displays layout diagram. Its indices are GUI-owned,
  assigned to secondary displays by desktop position and shared with the diagram.
  A Use checkbox per display
  retains its assignment and geometry while disabling participation; edits follow
  Configuration/control gates. Preserve participation across inventory refresh.
  Save explicit display assignments immediately in local frontend preferences by
  stable display identity, retaining Unassigned and temporarily missing displays.
  On a new GUI's initial Configuration/Ready view, restore these as local drafts;
  differences from the controller base remain dirty and require normal submission.
  Active-session synchronization and explicit controller reload use confirmed values.
  Discovery/loading never writes preferences or guesses replacement displays;
  invalid preferences stay preserved and save/restore failures are reported.
  V15 owns output selection without altering calibrated surfaces.
  Below the inventory, sections are ordered Screen calibration, Synchronization,
  Rig geometry. Screen calibration uses a CephVR1.0-style per-face table containing
  only paired scale, pixel offset and inverse-axis controls. Up/Down keys step scale
  by 0.01 (two decimal places) and offsets by 0.1 px (one decimal place), using
  the same draft/live-update path as typing. Loading preserves saved precision;
  partial typed input is retained. Rig geometry owns tank
  dimensions and fixed subject distances labeled Subject → Left wall / Front wall /
  Bottom (mm). Perpendicular distances to Left, Front and Bottom screens sit below these
  in the Rig geometry card. The screen-dimensions table contains width, height,
  derived read-only estimated projector distance, with wrapped headers.
  Screen calibration and Pixel-to-mm calibration are sibling cards, without nesting.
  Put Launch projection calibration above the correction table and Launch reference
  calibration above the measurement table.
  Effective throw ratio is config-only. Pixel-to-mm calibration omits explanatory text and pixel-span columns;
  its table has Screen, paired Measured X / Y (mm) inputs under one header, and
  read-only X / Y (mm/px) estimates, with all three columns stretching evenly.
  Per-screen measured horizontal/vertical reference bars retain native output
  dimensions and config-only `reference_x_px` / `reference_y_px` lengths. These
  lengths control the actual calibration bars and the same conversion arithmetic;
  positive whole pixels must fit the assigned output. Older files migrate their
  original quarter-output spans; unset lengths retain those defaults. Complete
  measured pairs estimate mm/px independently of throw ratio; projected distance
  additionally requires a positive throw ratio.
  Known millimetres derive independent X/Y mm/px and full projected
  image dimensions; full projected width times throw ratio estimates ideal throw
  distance (Bottom: total folded path). Subject-to-screen distances stay independent.
  Measurements from another assigned projector are cleared; imported historical
  distances remain visible until measurements are supplied. Missing or partial
  measured pairs cannot produce a calibrated mapping. Clip/tolerance settings remain in Rig geometry without an Advanced
  subtitle. One Load… / Save as… action row handles the complete rig, projection
  limits, all-screen correction/dimension values, synchronization and participation
  plus reusable runtime profile references under the
  [GUI calibration contract](../../contracts/gui-calibration.md), replacing the
  per-screen profile picker. Validate the complete bounded document before applying;
  invalid files preserve drafts. Save atomically, retain unset values, respect editing
  authority and cancel pickers on authority loss. Full version 7 retains reference
  measurements and their native output dimensions alongside the former runtime
  display-profile import into this row. Exclude physical inventory and output assignments;
  load preserves current display mappings, restores participation and pulse selection
  by logical rig face, and retains geometry/color calibration references and shared-output
  coverage. Rebind references using current output properties at submission; missing roles
  fail without guessing. Legacy full version 3 and numeric-only versions 1/2
  load with unset measurements; numeric version 3 retains them. Legacy
  runtime profiles remain loadable through the same action. Loading is not backend preparation.
  Launch reference calibration and Launch projection calibration prepare calibration files before
  requesting output; no separate preparation button is shown. Preparation uses the current four enabled face
  assignments, current rig fields and native monitor identities to export a static
  arena asset, display profile and explicitly diagnostic geometric
  profiles into Protocol Assets. Reference measurement renders only raw-pixel bars
  on black, ignoring stored measurements and manual corrections. Frame/grid
  adjustment requires complete measurements matching each native mode and uses
  mm/px directly with rig geometry; neither action requires projector distance or
  throw ratio. The grid mapping combines measured physical screen/image ratios
  with each face's scale, pixel offset and inverse-axis drafts;
  reject corrections extending outside the output. Submission publishes new
  content-addressed measured affine assets for GUI-owned 2×2 profiles, preserves
  originals and rejects replacing imported nonlinear/masked/weighted calibration. Reject missing or
  ambiguous monitor bindings.
  Failed preparation does not send a launch request.
  Unmeasured profiles are diagnostic placeholders; measured affine mappings
  still require optical acceptance and do not set experiment defaults. Both actions
  target all four assigned projectors together;
  during an active frame/grid presentation only Scale X/Y and Offset X/Y remain
  editable. Debounce valid edits into bounded normalized mapping updates without
  rewriting protected assets, reopening windows or changing rig/measurement state.
  Coalesce newer edits behind one in-flight update; invalid/partial edits retain
  the last confirmed projection. Exact active diagnostic, controller/renderer
  generations, configuration revision and increasing adjustment sequence bind each
  update. Lost authority/disconnection, closing/unknown state or another diagnostic
  discard pending live intents; no stale replay. Actual all-output presentation
  confirms the new sequence. Other projector controls stay locked until closure.

  After confirmed output activation Launch projection calibration reads Close. It returns to
  Launch projection calibration only after confirmed closure; Launch reference calibration remains
  disabled while presentation is active or pending. Failed/pending commands never claim an
  output-state change. These actions and Close control V01's diagnostic presentation outside
  trial timing; preparation sends no output command.
  Retain per-face drafts without adopting measured defaults. Planar geometry
  conversion retains all four inward-facing surfaces and the fixed observer.
  Subject distances position screen planes independently of tank walls, parallel to
  their corresponding faces. Front is centered on the tank width/height; sides remain
  vertically centered and Bottom centered across the tank width. Side and Bottom
  front edges start at the Front screen plane, extending toward the tank back using
  their own dimensions. Changing Front distance moves these shared front edges. Require
  finite positive screen dimensions/distances; unset values never imply tank-wall
  placement. The owner-selected parallel-plane editor assumes equal left/right
  tank-wall offsets: right subject distance = tank width + left screen distance −
  twice subject-to-left-wall distance. Right distance has no independent editor or
  stored JSON field. Recompute for both diagram and projection; invalid/missing
  inputs cannot retain a stale right plane. Version 1 calibration import checks any
  explicit right distance against this rule before adopting; unequal offsets reject
  the whole load. Version 2 saves only independent calibration values.
  Diagram and projection conversion share the same corner calculation.
  Synchronization places VSync mode beside Pulse display. Pacing identity and the
  60 Hz target live in Visual Stimulus configuration only, without a GUI editor. Pulse-off dims and locks
  photodiode editors while retaining independent pulse/pacing values; Blackout zones
  remain independently editable under configuration authority;
  this editing gate does not couple their runtime ownership. Omit explanatory pulse,
  subject-offset and projected-width footer text.
  Projectors replaces its HUD with Displays layout above a tank/screen
  diagram without an explanatory footer, retaining the activity log below. Left-button
  dragging rotates only the view; double-click resets it. Fit tank, screens and ideal
  projection cones within the available plot. The plot has no element labels; its
  legend identifies the drawn elements.
  Enabled assigned projectors with finite positive distance/throw use centered
  optical paths: footprint width = total optical distance / throw, height = width /
  assigned display aspect ratio. Front/side axes are perpendicular to their screens.
  Bottom uses a 45° mirror below the tank, with its projector directly beneath the
  Right projector (same horizontal coordinates), aimed at the mirror. Locate the
  mirror from the retained Right geometry/distance and Bottom total optical path;
  the reflected axis reaches the Bottom screen center perpendicularly. Draw the
  mirror area intercepted by the ideal cone, not a measured reflector size. Right
  participation does not alter this placement. Missing/impossible central paths omit
  Bottom optics with a hover explanation; never substitute a direct Bottom projector.
  Outer-ray clearance failure alone retains the valid projector, central reflected
  axis and mirror-position marker. Draw the ideal footprint dashed and explain
  incomplete coverage on hover; do not invent a full mirror polygon. The Bottom
  view uses a simple schematic pyramid from mirror center to footprint corners,
  distinct from the physical reflected-ray/clearance calculation.
  Show full footprints including overspill;
  do not guess missing inputs or draw inactive output cones. Physical screens remain
  visible independently of participation. Compact checkable buttons independently
  toggle Tank, Screens, Projection and Subject. Projection groups
  projectors, rays, footprints and mirror in both visibility controls and one legend
  entry; footprints use a distinct violet color. Retain view choices through draft/phase changes; they never alter output
  participation, calibration or runtime control. The legend stays visible and identifies
  visible line/dot colors and ray styling. These outlines are an operator estimate,
  not measured optical calibration or a runtime warp model. Pulse-off retains inactive/missing targets without blocking;
  enabled pulses require valid target/placement under V22. Timing and geometry
  drafts remain local until managed configuration integration. Exclude the operating system's
  primary display from both views. Number discovered secondary displays locally
  from 1 in desktop-position order (left to right, then top to bottom); use the
  same CephVR number in the table, display layout and status labels. These numbers
  identify GUI rows for projector assignment and are independent of Windows
  Settings numbers. The operator compares the two layouts visually to associate
  them; no ID entry or inferred Windows-number claim is required. Refresh keeps
  projector assignments by display identity even if the local number changes.
  An empty inventory explains that no secondary displays were found. No Size column remains.
  Projector choices are Unassigned, Front, Left, Right and Bottom; account for
  Unassigned when sizing. Display uses its content width; Projector and Resolution
  share the remaining width evenly with shared cell padding. Refresh retains
  assignments and reports missing/duplicate identities without silently remapping.
  V15 surface/viewport/calibration ownership stays separate; no one-projector-per-
  surface constraint or output-mode changes are introduced.
- SpikeGLX connection omits explanatory prose; the read-only pairing tooltip
  retains its owning config path. SpikeGLX exposes local channel-mapping drafts for discovered camera roles, Trial
  state, Projector flip and photodiode only while pulse generation is enabled.
  Disabled sources retain dimmed mappings; hidden photodiode mappings survive toggles.
  Each mapping has a local Use checkbox, preserving values while disabled; this
  does not disable its source camera or waive E12 required-channel validation.
  Additional named inputs may be added and removed with the row's remove action.
  Source-derived rows remain linked to their owning device and can be disabled
  rather than independently removed. All edits/removals obey Configuration authority.
  Rows show Use, Signal and Channel index; Stream, Index and Bit editors are omitted.
  Preserve loaded stream identity/index and bit as mapping metadata. Digital-bit metadata remains an E12 configuration
  concern, not an inferred bit-zero default; camera triggers use OneBox under E12. Configuration
  authority gates edits. These drafts do not configure SpikeGLX acquisition, enumerate
  remote saved channels or prove physical recording; managed adoption/validation is pending.
- Page grouping preserves E02/E08's backend ownership: acquisition owns cameras;
  the controller owns Microcontroller I/O, Visual Stimulus owns display output, and
  E12's controller client
  owns SpikeGLX. Connection checks do not establish E05 Setup readiness or E15 physical
  verification. New diagnostic operations require defined backend behavior; navigation
  follows ARCH-001's integration order and A11's explicit Configuration upload rule.
- Dashboard keeps compact runtime readiness above session actions, then subject/session
  details in the left column, with a runtime HUD and activity console in the right.
  The Session config card places Subject ID and Experiment in the first field row,
  followed by a full-width output directory. Spacing separates the species, sex, age,
  size and condition fields below, without a subsection heading.
  Runtime readiness uses a horizontal row inside System controls with independent
  read-only round indicators and detailed status
  in tooltips/accessibility text. Setup spans both columns above equally sized Start and
  Stop buttons. Subject age is labeled Age (dph); experiment phase appears in the HUD
  only, without a System controls badge. Setup requests
  preparation in Configuration and E05 New session in Ended; the latter returns to
  Configuration after cleanup and still requires fresh Setup/Start.
  Stop requests Cancel Setup in SettingUp/Ready. During a session it opens a chooser:
  Stop now maps to E06 Abort now, Stop after trial retains E06's trial-completion meaning,
  and Cancel/window dismissal sends no command. The chooser keeps current phase/control
  gates, closes when none remain available and rechecks authority on selection.
  These contextual controls replace the redundant Session menu; backend commands remain
  distinct and no automatic session progression is introduced.
  The HUD includes recording and metadata evidence. Dashboard excludes trial-plan
  editing, backend participation/use editing, the separate session-progress card,
  embedded previews, the design-review banner, frontend footer and header
  connection/local-control badges. Removing badges does not change command authority.
  Camera experiment enablement belongs to Devices. Dashboard shows a video-recording
  switch for each camera role and Visual Stimulus, plus Tracking velocities.
  Recording selections are retained but disabled while their source is inactive.
- A secondary **Previews…** button at the right of the Dashboard header opens one reusable modeless
  selector, with one checkbox per available camera/tracking/stimulus viewer and no
  open-window count. The same button toggles the selector open/closed. First opening without valid saved geometry snaps the selector's
  outer frame to the right of the main window with a shared 12-pixel gap and aligned
  top edges, constrained to the available screen. Remember its position across
  close/reopen and frontend restarts using local GUI preferences; Qt restores saved
  geometry within available screens, then fits width/height to the current rows. Closing the selector via its toggle or
  window controls leaves viewer visibility unchanged.
  The selector uses a compact bordered Source/Show grid, with source labels left,
  aligned visibility checkboxes right, blue column captions and shared hover/focus
  styling. It contains no duplicate window heading, instructions,
  footer buttons or redundant Open/Hidden labels. Pending/error/unavailable status
  remains visible; the local review label lives in the window title.
  Checkboxes reflect reported visibility, including external-window closure; pending
  requests and unavailable viewers disable their controls with explanatory status.
  Preview rows are ordered Behavior cam, Tracking cam, any further configured camera
  roles, Tracking, Visual stimulus. Retain inactive sources as dimmed, disabled rows:
  a camera must be enabled for the experiment; experiment Tracking requires an active
  protocol pipeline; Visual stimulus requires protocol participation. Explicit T08
  Configuration diagnostics instead require the accepted enabled Tracking-camera
  preview and their selected diagnostic pipeline, independently of experiment Tracking
  participation. Check active state again
  when requesting visibility. The Devices preview button uses the same participation
  restriction and additionally requires the selected editing connection. GUI restrictions
  do not expand A10's manual-preview phase or backend authority. Visibility never changes
  participation, recording or session actions. Protocol Tracking participation updates
  review preview availability; the review menu retains labelled backend fixtures.
  Managed Protocol integration remains unfinished.
  Controller/owning backends admit visibility requests and own external rendering;
  no image stream enters the Dashboard. Initial local review demonstrates labeled
  sample state only; transport, runtime viewers and performance acceptance remain
  unfinished under E03/E08/E15 and owning backend preview rules.
- Output directory has an asynchronous existing-folder picker beside the editable
  path. Cancellation preserves the draft; selection rechecks editing availability.
  Camera Connect and the Dashboard selector target the same source identity and
  visibility state, with one backend-owned external viewer per source. The local
  review updates visibility fixtures only and creates no image window.
  Path display is compact when unfocused, with the full path in its tooltip and
  unchanged full text for editing/copying. Activity logs follow new messages only
  when already at the bottom; otherwise preserve the retained message being read,
  falling back to the oldest retained entry if it is evicted. These GUI conveniences
  do not reserve output, validate experiment storage or change backend state.

- Devices/Microcontroller provides a firmware path and explicit Upload governed by
  A11. Select `.ino` for compile-then-flash or `.hex` for direct upload. Controller owns
  compilation/validation/serial handoff; the GUI never invokes compiler or serial tooling.
  The path is an operator preference; review mode presents the same controls without
  flashing. In managed mode Upload is available only in idle Configuration, with
  diagnostics stopped and all camera ownership/native cleanup released. A displayed
  MCU compatibility failure alone does not block this explicit repair operation.
- Launch projection calibration prepares the geometry grid using measured mm/px and saved corrections:
  world-phase colored solid/dashed lines, full-face center crosses, face dimensions
  and a 50 mm ruler where it fits. Existing physical screen planes and offsets remain
  authoritative; no separate placement-only/no-grid mode is offered.

<a id="g02"></a>
### G02 — Shared frontend formatting

**Status:** Accepted · **Revision:** 37

- Device subtabs preserve their text color on hover. Tracking places Load/Save beside
  Pipeline and diagnostic/annotation actions in a separate, evenly sized row.
  File actions use Load… / Save as… captions across tabs. Devices' Configuration
  file cards share a Load-first row with equal-width/equal-height buttons, zero
  inner margins and the shared field gap, including Projectors.
  Inventory Refresh shares one icon/size/accessible-name helper and header placement;
  port discovery uses that same control beside its selector. Participation is the
  first Use column; inventory row selection shares the same behavior. Shared table
  fitting handles hidden signal headers without leaving an empty header gutter.

- Use the current CephVR1.0 Dashboard as the visual template: dark blue/black
  surfaces, subtle bordered cards, blue primary actions, muted red stopping actions,
  Segoe UI control text and pink monospace HUD/log panels. Use the shared coral
  accent for page headings, selected sidebar labels and active subtab text; keep
  form labels neutral, use bright blue coordinate headers and retain blue action/focus treatments. Embedded stimulus plots
  are excluded from the initial Dashboard increment.
- Form errors never occupy inline labels. Keep editing and passive validation quiet;
  when an explicit action requires missing/invalid values, show a window-modal
  warning and preserve the draft/document. Leave validation actions callable so
  users can obtain the reason. Reuse one warning per form, close it when editing
  authority is lost, and route routine status messages to the activity log.
  Semantic device state and authored-content/count displays remain normal UI data.
- One GUI-owned theme defines palette, typography, spacing, radii and sizing tokens.
  Small shared components, layout helpers and value formatters apply those tokens;
  pages compose them using focused data and callbacks under ARCH-002. Do not copy
  page-local styles or introduce a generic form/runtime framework.
- Keep a common content-measured title row, with Dashboard Previews at the right.
  Device icon subtabs occupy the top of the left content column, followed by the
  per-device Configuration file card and then connection/settings cards. Subtabs expand to fill their column and align their top edge
  with the HUD card’s painted top border. The right HUD stays at the same top position across pages and
  device subtabs in the two-column layout. Use the existing stacked layout on narrow
  windows; tab overflow scrolls without replacing navigation with a dropdown.
- Wheel/trackpad events never change combo, spinbox or slider input values, even
  with focus; route them to the enclosing scroll container. Explicit clicks, typing
  and keyboard edits remain available. Apply this once at application scope.
- Use one dim selection color for rows, navigation, subtabs and text selections,
  distinct from table-header fill. Table cells and headers share horizontal padding;
  content-sized columns include that padding rather than ending at their text width.
  Header sections round their outer top corners with transparent header backgrounds
  so native header fills do not protrude beyond the table outline.
- All tabular inventories and forms reuse the Cameras native Qt header, blue header
  band, padding and rounded border through one shared table helper, including device
  I/O, signal mappings, projection calibration, screen dimensions and point editors.
  Persistent controls fit their styled height plus cell insets; content-sized columns
  include control width and padding. Coordinate tables retain 2:1:1 name/X/Y columns and
  centered numeric headers/values. Fit single-line rows to their content; use no
  separate coordinate-header/divider theme. Cells remain directly editable with
  hover/focus affordances and dash placeholders. Preserve descriptive names,
  keyboard editing and existing validation.
- Section-level enable controls have an extra shared 8 px of space before their
  dependent fields, in addition to normal layout spacing. Apply the margin to the
  dependent section so hidden sections leave no empty gap; preserve compact
  same-row/table checkboxes beside their associated values.
- Keep page alignment, fixed card gaps, labeled fields, natural button heights,
  content-measured table columns, semantic status labels and inherited dialog styling
  consistent across pages. Same-row controls share their tallest natural height
  through the shared row helper, including pin/Test and path/Browse pairs. Compact
  checkbox/radio indicators and icon-only header actions are explicit exceptions.
  Shared card headers leave extra vertical space before
  content. A shared compact Card density (12-pixel padding, 8-pixel title gap)
  keeps small Inputs/Outputs cards fitted without changing other cards. Their shared
  row layout separates enable, signal name, pin and Test/Stop into aligned columns:
  compact centered checkboxes and equally distributed name, pin and action columns.
  Both cards use the same column proportions and spacing; longer names wrap.
  Card titles sit near the top-left corner in a true gap in the rounded
  outline, with transparent captions and continuous card fill. Console cards contain
  no Clear button or separate action row.
  Reflow/scroll before clipping; preserve widget ownership
  and state during layout changes. Connection evidence remains distinct from Ready.
- Except Protocol's G01 full-width planner and Projectors' display/tank diagram column, every page and device subtab keeps controls at the left, with a fitted HUD above
  an expanding Activity log at the right; placeholder pages retain this same layout.
  HUD height follows its rendered text, including wrapped lines and panel padding.
  The Activity log fills the remaining column height. Shared fitted-text helpers,
  size policies and layout stretch implement this rule; retain readable log minimum
  height. The shared left configuration column scrolls independently when inventory
  or controls exceed available height; the right status/diagram/log column stays in
  place. Hide vertical and horizontal scrollbar tracks throughout the Qt GUI,
  retaining wheel/trackpad and keyboard scrolling. Their zero-size gutter is stable
  across tabs regardless of overflow. Protocol scrolls its authoring region while navigation and the page heading stay fixed. Other pages have no outer whole-page scroll. Narrow windows stack the columns.
  Activity logs wrap at word boundaries without forced splitting of long tokens;
  an over-width indivisible token remains horizontally scrollable. Preserve the
  visible message and wrapped-line offset when appending or evicting old entries.
- Implement the native frontend with PyQt6, matching the reference. Initial local
  design review uses explicitly labeled presentation fixtures, no device/runtime
  calls and no admitted experiment commands. Managed bootstrap, E03 transport/leases
  and E15 full application/rig acceptance remain separate unfinished work.

<a id="e03"></a>
### E03 — GUI disconnection and control lease

**Status:** Accepted · **Revision:** 29

- **Closure and loss:** intentional GUI closure is allowed. GUI connection loss or
  crash never pauses, stops, restarts, or resumes the experiment. Unexpected
  connection loss produces a warning and triggers reconnection.
- **One GUI:** run at most one GUI process; ignore GUI launch requests while it is
  running. No automatic GUI relaunch and no standby GUI: after a crash the operator
  reopens it from the normal launcher while the experiment continues. Headless
  clients may still observe state concurrently.
- **Incidents:** during experiment execution, show E06's single updating incident
  window. Continuable incidents offer Continue session / Abort session while the
  original timeline runs; blocking incidents explain automatic stopping and allow
  acknowledgement. Restore retained incidents after reconnect, coalesce repeats and
  never block backend work. Closing the window is not consent; decisions use the
  existing control lease and revision-checked RespondToPrompt binding in the
  [incident contract](../../contracts/operator-incidents.md).
- **Control lease:** exactly one client holds the control lease required for
  configuration, Setup, Start, Stop after trial, Abort now, and other state-changing
  operator commands. Scope each lease to the controller process/generation and
  session.
- **Lease liveness:** the holder's exact open `WatchState` subscription is its lease
  liveness; there is no renewal call or reconnect reservation. On observed
  stream/transport loss, atomically release control and invalidate its generation.
  Accepted commands/operations and active experiments continue; in-flight commands
  not yet admitted recheck authority. Manual preview and retained camera editing
  connections follow A10's [control-loss cleanup rules](acquisition.md#a10).
- **Take control:** every new/reconnected/reopened GUI subscription starts as an
  observer. After installing current state/configuration and acknowledging existing
  reconnect warnings, try once to acquire an unheld lease automatically through
  AcquireControl. A concurrent holder or rejected claim leaves the GUI observing;
  replacing another holder requires explicit confirmed Take over control. Manual
  release does not trigger reacquisition within the same subscription. Reconnection
  uses a fresh claim, never restores an old lease generation or credentials.
- **State views:** `WatchState` sends one consistent current control-state view on
  connection and whenever that state changes. Clients replace their control view
  atomically; reconnecting starts from fresh state, without replaying events or
  merging patches. Keep the GUI Synchronizing/read-only until it installs the initial
  view and its matching configuration. `GetSnapshot` remains a read-only one-shot
  query; do not poll it periodically.
- **View identity:** identify views by controller generation and increasing state
  revision. Revisions may skip; reject older views without treating a skipped revision
  as missing work. Configuration values arrive with the first view of each stream and
  whenever their revision changes (E08); within that stream, a view without values
  uses the values installed at its revision. Never reuse values across streams.
  Missing/mismatched configuration invalidates the view; remain read-only and
  resubscribe. Command admission still revalidates authority, configuration and
  lifecycle.
- **Reconnect warnings:** built from the Snapshot's retained errors, recoveries and
  runtime incidents for the current Setup/session, bounded by
  `[control].max_retained_incidents` (default 256; oldest resolved entries evicted
  first, active incidents never). The Snapshot reports the retained coverage start and
  truncation; do not imply a complete history of a longer absence. There is no
  separate history RPC. Exclude scientific data, raw RPCs and unchanged heartbeats.
- **Warning modal:** after synchronization following an unexpected disconnect or
  crash, show a modal warning. Keep state-changing GUI controls disabled until the
  operator acknowledges it. Acknowledgement changes only GUI state: it does not pause
  execution, clear errors, recover or claim a lease, or alter controller state.
- **Reconnect schedule:** after unexpected controller-connection loss, the GUI retries
  immediately, then after 1, 2, and 5 seconds, and every 5 seconds thereafter, until
  connected or the GUI is intentionally closed. A successful connection resets the
  schedule. Retry duration does not extend control ownership. E08 automatic
  application shutdown overrides this loop after confirmed controller/supervisor loss;
  display the shutdown reason while alive without delaying process exit.
