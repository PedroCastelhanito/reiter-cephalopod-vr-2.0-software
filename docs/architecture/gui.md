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

**Status:** Accepted · **Revision:** 93

- Main navigation orders **Dashboard, Protocol, Devices, Tracking**. Protocol owns
  session mode and V02/V03 stimulus programming. Protocol type with Load/Save as sits
  left of one Assets folder (E07 root); narrow windows stack the pair. Dashboard owns
  camera/stimulus video recording and Tracking velocities in a Recordings card below
  Session config, using two columns with each checkbox beside its label. Assets are prepared externally. Tracking participation follows
  E10 without a Protocol status indicator; required acquisition/rendering is independent
  of optional video recording. Device controls stay in Devices.
- Protocol uses a widened Trials column beside Trial timeline, with a full-width Epoch
  editor below at all widths. Trials provides a selectable list and compact Add/Delete
  controls. Trials and timeline cards keep a fixed height; extra trials/layers scroll
  internally, without a resize grip. Center the timeline count/duration summary.
  Align the overview's left edge with the projector labels and its right edge with
  the projector rows; leave a clear vertical gap before current-epoch details.
  A single duration-proportional overview bar shows all epochs; matching ordered
  stimulus settings, assets, projector mappings and scene background share a color,
  ignoring epoch names, durations and scene/instance identifiers. Color is an authoring
  cue, not a serialized epoch type. Unknown timing uses sequence order. Click selects
  one source, Shift a range, Ctrl/Command toggles membership. Beneath the bar, show
  the current occurrence's name/duration and one row per enabled projector, including
  ordered layers, prepared asset names and compact parameter descriptions. Full text
  is available on hover; batch multi-selection retains the current occurrence details.
  Groups expand for authoring inspection; example shuffled order never chooses Setup's retained seed.
  Repeated occurrences select their shared source and identify that edit scope. No
  nested-scope timeline replaces the full-trial overview. No trial table, HUD/log,
  draft badge or standalone Validate action. Configuration content scrolls within
  the fixed navigation shell.
- Rig review startup discovers attached Basler cameras, secondary Windows displays
  and COM ports without assigning surfaces or claiming Setup readiness. Camera
  refresh preserves drafts by serial; Test enabled opens, identifies and closes each
  enabled camera. Display refresh preserves local assignments/participation. Explicit
  test fixtures may still supply simulated displays for isolated frontend checks.
- Epoch editor has **Batch generate** and **Batch edit** tabs within the card;
  wheel gestures do not switch tabs.
  Forms use the existing configuration scroller. Switching tabs preserves local
  drafts without committing; explicit Add/Apply commits, and Discard changes resets
  pending edit patches. Invalid input stays visible. Loss of editing authority closes
  file pickers and disables forms. All parameters opens the complete single-source
  inspector in the card.
  Batch generate owns a local reference
  epoch with prepared assets, independent projector layers, exact duration and complete
  family parameters. Show each enabled projector's reference layers and prepared
  asset filename and stimulus-specific values in one compact row; full paths remain
  available on hover. Omit the Projector heading and display Looming as the short
  family name. The stimulus dropdown changes the selected layer's type, resetting
  its asset; incomplete asset choices remain local drafts and block generation.
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
  Leave a clear gap below the batch tabs. Stimulus mode, Duration (hh:mm:ss),
  Repetitions (at most three digits), Batch label and Insert share one row at wide
  widths, with widths reflecting their values; narrow widths wrap. Leave extra
  separation before stimulus rows. Arena mode omits the redundant type selector and exposes Longitudinal/Lateral/Angular
  movement toggles and signed gains under V24 (zero gain disables an axis). Keep
  imported programmed motion and custom feedback unchanged unless explicitly edited.
  Tracking channel conflicts reject the edit.
  Advanced settings occupy one shared-style card beneath the selected projector
  row, with its left edge aligned to Layer. Retain state is first; Linked to and
  fade-in/out durations follow, then control entries. New GUI-created stimuli retain
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
  Optional variations use one shared-style card with an Enable checkbox
  first inside its body. Each rule separates Projectors (one or All projectors), Layer (local
  ordinal or All layers) and Parameter on the first row, with removal aligned to
  those controls. Put Method and all value-related controls on the second row;
  Random groups Minimum/Maximum/Precision with Method. Match
  heights within each row. All projectors covers the enabled reference screens and
  offers common layer ordinals; explicit missing/stale targets reject generation.
  A selected local ordinal maps to the corresponding canonical instance on each
  projector; deduplicate shared targets. Accept explicit values or bounded min/max/step
  sweeps, or Random for numeric parameters. Random shows Minimum, Maximum,
  Precision (positive value step). No manual resample action. Batch Repetitions
  determines the random epoch count; no separate Epochs field. Without a fixed list,
  generate one random epoch per repetition. With paired Values/Sweep lists, repeat
  their ordered sequence and draw per resulting epoch, within the existing 2000
  expanded-epoch authoring bound; do not repeat the materialized batch again.
  Draw uniformly with replacement from multiples of the precision inside inclusive
  bounds; reject invalid/nonfinite ranges or an empty precision grid. Cache draws
  while range/precision and resulting count are unchanged, so preview/commit uses the same values; input changes
  create a new set. Persist concrete epoch values, not an
  unresolved runtime random rule; Setup seeds and V08 shuffle ownership are unchanged.
  Pair rules by value position with equal list lengths, without Combine. Explicit
  Values remain in entered order. Parameter choices share
  the selected stimulus columns and captions, including units: Rotation replaces
  Angular speed in the UI, without changing its canonical key. Exclude Width, Height
  and Opacity. Mixed targets offer only compatible common columns; unsupported
  targets reject generation. Video At end accepts ordered categorical values, without
  a numeric sweep. Preview count/duration before Add epochs. Materialize variants as individually
  editable canonical source epochs; nonrandom repetitions retain listed order in V08 groups.
  Trial-wide shuffle belongs to a separate epoch-reordering action.
  Store the optional batch label on every generated source epoch under V03; Batch
  edit can select all source epochs with that label, including nested groups.
  Insert at beginning/end, before/after the selected top-level block, replace the
  trial, or distribute one generated block after every N existing top-level blocks
  and append the remainder. Groups count as blocks, retaining repetition semantics.
  After label inserts an independently identified batch after every original matching
  source epoch in its existing group scope, retaining repetition/condition semantics.
  List labels from the current trial; missing matches or invalid results reject the
  entire operation. Bound the expanded label-insertion result to 2000 epochs.
  Replacement is explicit and undoable. A short reference
  is not itself a trial: final insertion validates the complete trial and remains
  atomic. File cancellation, invalid settings or failed insertion leave it unchanged.
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
- Reuse expanded timeline paths/content keys for immutable program identities in a
  bounded four-view cache; changed programs invalidate by identity and selection
  does not rebuild the trial. Unchanged metadata flushes preserve the program identity.
  Keep the painted timeline and existing 2000-epoch preview bound; do not create a
  widget or decode an asset per epoch. GUI JSON reads/saves use the existing shared
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
- All mutation controls belong to Epoch editor, including naming, duration, layer
  management and structural Actions. A first projector-local edit detaches a shared
  2D instance while retaining other projectors' identities, settings, assets and stack
  order. All projectors supports shared edits; arena remains rig-wide under V02.
  Disabled targets retain content/geometry and are labeled inactive. No enabled
  outputs shows a neutral lane for offline authoring. Epoch timing is shared across
  projectors; different boundaries remain separate epochs. No embedded rendering.
- Existing repeat/condition groups remain editable after canonical JSON reload;
  preserve child-block versus condition-row semantics, complete settings and V07
  continuity. Structural rename/duplicate/reorder/remove act on one source epoch;
  multiple-source changes use the explicit batch editor. Undo/Redo remain in Actions,
  without toolbar buttons. Load/save validates canonical JSON and saves atomically
  per trial. Trial deletion confirms the named local draft, preserves saved files
  and leaves a blank draft if deleting the last. Trial drafts are local documents,
  not a session schedule. Expanded sequence inspection has an explicit Close action;
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
  Cameras stacks Available devices above Camera config in the left column, with
  its HUD/log column at the right. The inventory provides experiment enablement,
  stable identity, role, selection, refresh, connect/disconnect and external preview.
  Refresh is an icon action in the inventory header's upper-right corner; Connect
  toggles to Disconnect for the selected editing connection. Camera config omits
  the redundant selected-camera caption; identity remains in the inventory/HUD.
  The Devices footer has no draft-settings text; local fixtures remain identified
  in the review window title and activity messages.
  Inventory actions are ordered Test enabled, Connect, Preview. Test enabled
  targets enabled cameras without changing selection or connection
  state. Initial review only logs requested checks as not tested; actual backend
  check semantics/integration remain unfinished and no Setup readiness is claimed.
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
  Changing the path clears stale hints; later explicit dropdown edits remain drafts.
- Microcontroller owns one selected COM port for all camera triggers; Cameras has
  no controller/port selector. Scan ports lists discovered COM-number names with
  the available device description, preserving the port identity separately and
  a still-present selection without opening devices. Do not expose
  macOS/Linux serial device names or invent a second controller in the draft.
  Inputs precedes Outputs. Inputs lists Projector flip; Outputs lists Trial state
  followed by configured camera roles, with no camera subsection heading or Hz column.
  Each row contains an enable checkbox/name, pin and a Test/Stop toggle with stable
  geometry. Camera enablement shares Cameras' experiment participation state;
  retain disabled rows for re-enabling and preserve their pins. Fixed input/output
  enablement is local draft configuration. Disabled signals have dimmed pin/test
  controls, cannot start tests and do not participate in pin-conflict checks.
  Disabling a signal ends its local review test; editing authority gates enablement.
  In local review, Test enters labelled review state and Stop exits it; no pulse is
  claimed. Lock port/scan and pin editing during review tests. Reset affected camera
  tests when their configuration changes, and reset all review tests on port or
  phase/control loss. Live start/stop acknowledgements remain integration work.
  Fixed active-high Trial state and
  rising-edge Projector flip behavior belongs to A11; no level/edge selectors remain.
  Camera test rates are read from Cameras rather than duplicated here. Output tests
  target one pin for observation in SpikeGLX; the input test observes rising edges,
  never drives the input pin. Test requests require Configuration/control, a COM port,
  a nonempty pin and no target-pin conflict; camera requests additionally require an
  enabled external-trigger role and valid retained rate. Until managed diagnostics
  are integrated, report requests as not tested/no command sent, never as pulse evidence.
- Projectors uses a compact table of Display index, Projector assignment, Resolution
  in pixels, plus a scaled Displays layout diagram. Its indices are GUI-owned,
  assigned to secondary displays by desktop position and shared with the diagram.
  A Use checkbox per display
  retains its assignment and geometry while disabling participation; edits follow
  Configuration/control gates. Preserve participation across inventory refresh.
  V15 owns output selection without altering calibrated surfaces.
  Below the inventory, sections are ordered Screen calibration, Synchronization,
  Rig geometry. Screen calibration uses a CephVR1.0-style per-face table containing
  only paired scale, pixel offset and inverse-axis controls. Rig geometry owns tank
  dimensions and fixed subject distances labeled Subject → Left wall / Front wall /
  Bottom (mm). Perpendicular distances to Left, Front and Bottom screens sit below these
  in the Rig geometry card. The screen-dimensions table contains width, height,
  projector distance and throw ratio, with an unlabeled row-name column and wrapped
  headers. Clip/tolerance settings remain in Rig geometry without an Advanced
  subtitle. One Load JSON / Save as action row handles the complete rig, projection
  limits and all-screen correction/dimension values under the
  [GUI calibration contract](../../contracts/gui-calibration.md), replacing the
  per-screen profile picker. Validate the complete bounded document before applying;
  invalid files preserve drafts. Save atomically, retain unset values, respect editing
  authority and cancel pickers on authority loss. The JSON excludes discovered
  display/projector lists, output assignments and participation; load leaves these
  untouched. Loading is not backend preparation.
  A separate Prepare calibration files action uses the current four enabled face
  assignments, current rig fields and native monitor identities to export a static
  arena asset, display profile and explicitly diagnostic geometric
  profiles into Protocol Assets. The exported mapping applies each face's scale,
  pixel offset and inverse-axis drafts, defaulting unset values to diagnostic
  identity; reject corrections extending outside the output. Reject missing or
  ambiguous monitor bindings.
  These profiles are uncalibrated optical placeholders and do not set experiment
  defaults. Launch calibration targets all four assigned projectors together;
  after confirmed output activation the same control reads Close. It returns to
  Launch only after confirmed closure. Failed/pending commands never claim an
  output-state change. Launch/Close controls V01's diagnostic presentation outside
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
  all other synchronization editors while retaining independent pulse/pacing values;
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
- SpikeGLX exposes local channel-mapping drafts for discovered camera roles, Trial
  state, Projector flip and photodiode only while pulse generation is enabled.
  Disabled sources retain dimmed mappings; hidden photodiode mappings survive toggles.
  Each mapping has a local Use checkbox, preserving values while disabled; this
  does not disable its source camera or waive E12 required-channel validation.
  Additional named inputs may be added and removed with the row's remove action.
  Source-derived rows remain linked to their owning device and can be disabled
  rather than independently removed. All edits/removals obey Configuration authority. Rows identify stream, stream index, saved
  channel; no Bit editor is shown. Digital-bit metadata remains an E12 configuration
  concern, not an inferred bit-zero default; camera triggers use OneBox under E12. Configuration
  authority gates edits. These drafts do not configure SpikeGLX acquisition, enumerate
  remote saved channels or prove physical recording; managed adoption/validation is pending.
- Page grouping preserves E02/E08's backend ownership: acquisition owns cameras and
  microcontroller I/O, Visual Stimulus owns display output, and E12's controller client
  owns SpikeGLX. Connection checks do not establish E05 Setup readiness or E15 physical
  verification. New diagnostic operations require defined backend behavior; navigation
  does not lift ARCH-001's integration order or A11's firmware/flashing deferral.
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
  a camera must be enabled for the experiment; tracking requires an active protocol
  pipeline; Visual stimulus requires protocol participation. Check active state again
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
  Camera Preview and the Dashboard selector target the same source identity and
  visibility state, with one backend-owned external viewer per source. The local
  review updates visibility fixtures only and creates no image window.
  Path display is compact when unfocused, with the full path in its tooltip and
  unchanged full text for editing/copying. Activity logs follow new messages only
  when already at the bottom; otherwise preserve the retained message being read,
  falling back to the oldest retained entry if it is evicted. These GUI conveniences
  do not reserve output, validate experiment storage or change backend state.

<a id="g02"></a>
### G02 — Shared frontend formatting

**Status:** Accepted · **Revision:** 23

- Use the current CephVR1.0 Dashboard as the visual template: dark blue/black
  surfaces, subtle bordered cards, blue primary actions, muted red stopping actions,
  Segoe UI control text and pink monospace HUD/log panels. Embedded stimulus plots
  are excluded from the initial Dashboard increment.
- One GUI-owned theme defines palette, typography, spacing, radii and sizing tokens.
  Small shared components, layout helpers and value formatters apply those tokens;
  pages compose them using focused data and callbacks under ARCH-002. Do not copy
  page-local styles or introduce a generic form/runtime framework.
- Keep a common content-measured title row, with Dashboard Previews at the right.
  Device icon subtabs occupy the top of the left content column, with configuration
  cards below them. Subtabs expand to fill their column and align their top edge
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

**Status:** Accepted · **Revision:** 28

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
  observer. Install current state/configuration, acknowledge existing reconnect
  warnings, then require explicit **Take control** to acquire or replace the lease.
  This atomic action may replace the old lease at any time and invalidates its
  generation. No recovery tokens, replacement credentials, grace timer or automatic
  lease restoration.
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
