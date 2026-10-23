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

**Status:** Accepted · **Revision:** 309

- Protocol category is separate from session Control: Media presentation, Texture
  drift or 3D navigation. Preserve projector rows, row-local Layer management,
  parameter columns and a Motion source choice (Self/Linked) for link-capable textures.
  Self shows motion parameters; Linked replaces them with a Linked to selector and
  requires an eligible source. Fade-in/Fade-out controls sit in Advanced settings
  below their row. Switching category remembers and restores its last trial
  schedule/selection, including protocol save/load; Control and asset root stay shared.
  First use inherits compatible content, otherwise starts blank while retaining the
  departing content in its compatible category template. Templates validate atomically;
  legacy source stays intact until explicitly classified. V02 owns executable validation.
- Monitor defaults to Combined: one renderer-owned GPU rig view maps the live
  calibrated output crops onto the prepared screen planes, beside shared instruments.
  Left-drag rotates the inspection camera with the protocol preview's sensitivity
  and elevation limits; double-click resets its home view. This camera changes no
  stimulus observer, state, output geometry or recording. No pixel readback is added.
  Combined gives the rig view the expanding image area, collapsing unused camera
  space. Drift shares compatible projector vectors on one polar plot with stable
  projector colors and common speed/angular scales; incompatible units remain separate.
  Its parameter table has projector rows and Speed, Direction and Angular speed
  columns with units; unavailable values stay explicit. Per-projector retains
  individual image/plot pairs in Left, Front, Right, Bottom order, adapting rows and
  image/plot stacking to available space. Static projectors retain their plots.
  Presentation omits motion controls/instruments. Navigation uses
  the single observer's arena map and motion instruments with projected output views.
  Restore camera video space when a camera preview is selected in any category;
  replace the old standalone stimulus
  composite tile with this stimulus area. Existing preview visibility, authority and
  renderer ownership apply; missing tracking never becomes simulated live motion.

- Camera and Visual Stimulus previews display the newest available frame at up to
  20 Hz, using the source rate when slower, without duplicate frames or catch-up
  bursts. Capture, recording and projector presentation rates are independent.
- Preview stream headings and Show controls sit eight logical pixels above their native
  frame, with measured source and preview FPS directly below. Hidden, unavailable or
  three-second-stale measurements show a dash; layout reserves the footer when choosing
  stream columns.

- Devices/Projectors provides an explicit RGB LED current and Adjust action for all
  USB-detected TI projector interfaces. The controller owns SDK access under E02/E08,
  requiring the current control lease, configuration revision and Configuration phase;
  serialize it with existing manual device work and block Setup until E08 confirms
  exact native cleanup. Use E08's registered brightness helper role and original
  operation deadline.
  Review reports intent only. SDK readback/failure is authoritative; partial application
  is reported without rollback or automatic retry. E04 records the latest observed
  attempt in experiment metadata; requested current is never measured luminance or
  evidence of unchanged hardware at Start. See the [brightness contract](../../contracts/projector-brightness.md).

- Synchronization adds Launch photodiode placement and Launch blackout placement. The former starts black when its initial pulse definition is empty/incomplete, then runs V22's bright/dark submission sequence on black as complete live edits arrive; the latter previews black zones on neutral gray. Reuse V01 diagnostic Open/Update/Close, one active view, authority/revision/sequence gates and Idle restoration. During active placement enable only the relevant pixel rectangles/target or blackout add/remove controls; debounce complete bounded edits and retain the last valid presentation while typing. Unknown state permits Close only. Live Frame/Pulse/target edits preserve the diagnostic sequence; Close/reopen restarts it. These previews do not establish optical acceptance.

- Projector window creation and recreation preserve the current desktop cursor
  position; disable automatic fullscreen cursor centering in the native window owner.

- Tab and Shift+Tab move forward/backward through visible enabled GUI form controls,
  including persistent editors inside tables. Tables retain arrow-key selection;
  read-only text views pass Tab to focus traversal rather than trapping it.

- Rig clipping and numerical geometry tolerances are file-only under V15/E14.
  Remove their GUI editors and draft persistence. Existing numeric calibration and
  review files remain loadable; discard legacy projection overrides while preserving
  physical measurements and other settings. Calibration and submission use the
  owning Visual Stimulus TOML.

- Projector availability does not gate saving/restoring local GUI drafts or accepting
  structurally valid settings with saved display identities/properties. Retain assignments,
  participation and authoring fields while outputs are disconnected. With no identified
  projectors, display an availability explanation and instruct the operator to turn them
  on and refresh before projector tests/Setup. Setup remains clickable under ordinary
  authority/phase gates; refresh inventory on click, then log the reason and submit no
  configuration or Setup command when none are identified. Physical output validation
  remains required for projector tests and backend preparation under E07/V19.

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
  V15/V19/V22 own final composition and trial/Idle behavior; both GUI modes share controls outside the staged review candidate below.
- Review and runtime share the same Microcontroller and Projector Synchronization
  editors and portable files. Microcontroller places Inputs and Outputs directly
  below connection, before the column's expanding spacer. Inputs supports named,
  enabled pin drafts and Add/remove; hide the empty table/header but retain Add input.
  Keep unfinished inputs and inline output type/pin drafts across save/restore,
  including legacy Review files. Outputs retain supported identities, fixed pin
  ownership and camera participation ownership. Both modes follow existing phase,
  authority and device-operation gates; input authoring does not enable A11's
  deferred physical input capture or diagnostics.
  Synchronization retains independent Frame/Pulse drafts by logical screen; blank
  screens add no pulse. Pulse-display VSync requests all enabled pulse screens under
  V20; V22 owns runtime multi-output drawing and evidence. Full and projector-only
  files preserve every screen and load in either mode, migrating legacy single-screen
  files without discarding settings. Local Review uses its modeless placement fixture;
  runtime uses the authenticated V01 diagnostic Open/Update/Close path. Both repeat
  V22's pattern and preserve its index during complete live edits. Camera connection
  actions follow the inventory rule below; MCU wiring stays in the owning controls.
- Omit explanatory body descriptions throughout GUI cards, editors and dialogs;
  useful guidance belongs in control tooltips. Retain field labels, units, live
  summaries/status, empty-state messages, errors and required operator choices.
- Review and managed runtime use the same DashboardWindow page construction,
  shared cards, fields, navigation and responsive layout rules. Mode-specific wiring
  supplies local fixtures or authoritative state and command availability; it adds no separate page layout. Dashboard cards have identical geometry in both modes:
  no Runtime-only control button or hint row. Take control, confirmed Take over and
  Release remain in Runtime's Control menu; command gates follow actual authority.
  Review-only inspection menus and runtime authority
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
- GUI Subject ID entry requires exactly four ASCII digits before Setup, preserving
  leading zeros as text. Species is a non-editable choice of Sepia Pharaonis,
  Sepia Latimanus or Sepioteuthis lessoniana; absence remains optional. Loaded legacy
  IDs/species remain visible and round-trip without truncation; an unlisted species
  is a disabled legacy item requiring replacement before Setup. No historical
  outputs or headless/backend identifiers are rewritten.
- Managed session submission retains optional species, sex, age in dph, size in mm
  and condition beside subject/experiment identifiers. Absent values remain absent;
  numeric age is finite and nonnegative and size is finite and positive. E07 owns
  validation, stale-revision rejection and persistence; incomplete local drafts never
  authorize Setup with different accepted settings.
- Main navigation orders **Dashboard, Protocol, Devices, Tracking**. Protocol owns
  session mode and V02/V03 stimulus programming. Protocol type with Load/Save as sits
  left of one Assets folder (E07 root); narrow windows stack the pair. Dashboard owns
  camera/stimulus video recording, Tracking velocities and **Save spikeglx** in a
  Saving options card below Session config, grouped under Data first (Tracking velocities
  and Save spikeglx), then Videos (camera videos and Visual stimulus video), using two columns
  within each category, a clear gap between categories and a wider column gutter,
  with each checkbox beside its label. Prefix every option label with Save. Save spikeglx is the existing E12 per-session pairing flag; keep one
  checkbox/state and its existing persistence, confirmation and phase/authority gates. Assets are prepared externally. Tracking participation follows
  E10 without a Protocol status indicator; required acquisition/rendering is independent
  of optional video recording. Device controls stay in Devices.
- Cameras, Protocol, Microcontroller, Projectors, SpikeGLX and Tracking own reusable JSON
  Load/Save as controls. Omit full-GUI Load/Save buttons from the sidebar; automatic
  GUI draft history retains Dashboard metadata, camera drafts and recording choices. The
  [snapshot contract](../../contracts/gui-configuration-files.md) owns formats and
  inventories. Validate all sections before restoring local drafts, save atomically,
  preserve unset/dormant settings and close choosers on authority loss. Asynchronous
  file/folder pickers use the normal native Windows Explorer dialog through the
  shared queued modal execution; cancellation before startup stops the owned launch
  timer, and native execution stops the Windows helper's pending timer. Keep immediate
  rejection, existing owner/path validation, stale-result fencing and deferred deletion;
  no arbitrary delay or global dialog setting. Full files
  retain explicit rig identities and require matching inventories; projector-only
  files remain portable under the calibration contract. Loading starts no device,
  uploads no firmware and restores no runtime status, ownership or credentials.
  E07 submission/Setup validates runnable settings; loaded camera/MCU drafts survive
  polling and enter the normal configuration proposal. SDK PFS import remains A10-owned.
  Role, participation and pin edits to loaded camera/MCU drafts remain local until
  submission; update camera rows and supported outputs together. Selected-camera
  Connect submits that camera's current assignment, timing, PFS and pulse
  parameters, then continues only after controller acceptance and required SDK
  import/cleanup; no Setup is required. Bulk Connect uses that same per-camera path.
  Serialize the chain with configuration edits,
  reject changed bases, and preserve unrelated local drafts while adopting confirmed
  camera revisions. Failure or lost authority prevents the subsequent camera action.
  Microcontroller Test submits the selected diagnostic pin/rate and COM port when
  they differ from confirmed settings, then starts only after exact controller
  acceptance. Preserve other local drafts; a changed base or rejection prevents
  the diagnostic and reports its reason. Log a sent test only after dispatch.
  Internal clock omits external TriggerSource and TriggerActivation requests in both
  immediate camera settings and loaded proposals; retain explicit edge choices for
  External controller and preserve strict SDK capability validation.
  Inactive loaded Tracking drafts stay local until required. SpikeGLX files restore
  editable pulse rows without a separate Save pulse mapping button; GUI Save/Load
  persists drafts without writing the controller inventory. Saved host/pairing
  references remain informational; E12/E14 host files supply endpoint and new-session defaults.
- Protocol uses a widened Trials column beside a persistent Trial timeline, with a
  full-width Sequence editor below. Trials and timeline use matching top borders,
  title heights and a taller shared minimum card height (320 logical pixels). Trials
  provides a selectable scrolling list: show × on the hovered row, or keep it visible
  on the selected row when no row is hovered, and show a +
  immediately below the last row, reachable by scrolling. Remove the separate
  bottom Add/Delete toolbar. Deletion confirms the targeted trial, preserves saved
  files and replaces the final deleted trial with a blank trial. Deleting the last
  scheduled trial clears the newly final trial's gap; retain edit authority
  and pending-draft checks. Omit Seed/Gap controls and the Selected trial section;
  preserve loaded seeds and legacy gaps under E01/E07. Setup retains seed ownership.
  The overview shows direct source epochs and collapsed canonical groups in sequence
  order, with name, duration and group repetition/occurrence totals. Blocks have a
  readable minimum width and horizontal navigation; paint only visible blocks.
  Matching epoch content shares an authoring color, never a serialized epoch type.
  New GUI trials contain groups only; each group contains source epochs only.
  Flat controller and saved-schedule trials use a single listed, once-only group
  for editing so runtime and Review expose the same subgroup controls. Preserve
  the original source on submission/export until the program is edited; Undo back
  to that source restores its original representation. Retain nested/mixed imports.
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
  Left-align trial totals beneath the card heading; keep Preview at the right.
  Size the card to its contents. Use dark unselected group blocks and an accent
  border/fill for selection. Show repetitions and duration on separate lines on roomy blocks; omit
  per-group epoch counts. Trial totals retain the overall epoch count.
  Put group names in a heading above their timeline cards, matching epoch subgroup headings.
  Add a subtle divider and compact Selected group label before the editing footer,
  retaining readable repetition fields at narrow widths.
  Put selected group name and repetitions
  below the blocks in a compact row aligned with the last group's visible right edge,
  keeping the Sequence editor for subgroup controls. Crowded group blocks show only
  repetitions when repetition/duration text does not fit; retain complete
  details on hover. Balance card spacing without duplicating these fields. Omit Order and preserve imported ordering.
  Protocol removal buttons (trials, groups, subgroups and variation rows) appear
  only while hovering their item, use the same compact × button role as MCU signal
  tables, and reserve enough space for centered glyphs and consistent insets.
  Trial and epoch timeline rows use the full editing-content width, with the trailing
  add button flush to the content right edge and no extra reserved right gutter.
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
  refresh preserves drafts by serial. Camera connection actions follow the inventory
  rule below and preserve explicit experiment participation. Camera roles include Eye
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
  Review draft version 2 stores MCU pins by logical camera role independently of
  discovered devices; version 1 migrates saved role/pin associations without
  changing camera participation or guessing unknown/ambiguous assignments.
- Runtime saves its complete editable GUI configuration to `config/runtime_gui.json`
  atomically, with read-back verification, before normal closure. Reuse the full GUI
  snapshot validators and inventory identities; controller connectivity, lease and
  experiment validity are not prerequisites for this local save. A failed local save
  keeps the window open unless the operator explicitly chooses Close without saving.
  Restore once after initial inventory/base installation in Configuration/Ready,
  marking restored settings as local edits subject to E07 validation. Later snapshots
  and delayed SpikeGLX inventory replies preserve those drafts; explicit controller
  reload discards them. An unreadable/incompatible or not-yet-restored previous file
  is preserved, with a clear reason; active-session synchronization takes precedence
  and retains the previous file. Runtime and Review keep separate local files.
  E07 alone owns accepted controller history; startup-only SpikeGLX host references
  remain read-only under E12. Local retention grants no Setup, Start or device action.
- Sequence editor has one subgroup form, reusing the reference composer and numeric
  variation controls with per-projector layers and parameters. No Generate/Edit tabs,
  target filters, duplicate epoch inspector or batch selector. Stimulus mode, Duration,
  and Name share a responsive row; completed valid edits update automatically, without
  Apply/Discard buttons. Group repetitions
  alone repeat the full sequence, equally for all epochs; no subgroup Copies control.
  Omit epochs-per-repetition, one-repetition, edits-apply and footer count helper text.
  Selecting a subgroup populates its first source template; unchanged parameters
  retain each member's existing values. Explicit variation rules replace the selected
  subgroup's pattern; retain active rule controls after automatic updates, selection
  changes, Undo and file reload. Save rules as V03 authoring metadata alongside concrete
  settings; unchanged rules do not resample on unrelated edits.
  The trailing subgroup + copies one current template, independent of variation rules; valid
  pending edits are applied first. Invalid input stays visible and prevents mutation.
  Changing selection or saving first commits valid pending edits; invalid input blocks
  the action. Undo first discards an invalid draft, otherwise undoes the last update.
  Each update atomically validates the whole trial, preserving source identities and
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
  incomplete choices remain drafts and block navigation, saving and + Epoch.
  Share column headings, repeating parameter headings only when meanings or units
  change; reserve equal heading space to keep projector rows evenly spaced. A Layer
  dropdown per projector selects the visible asset/parameters; its ordinal follows
  stack order. Prepared asset paths can be copied and pasted between projector rows;
  pasted paths resolve within the Assets folder and use the same validation as file
  selection. Successful file selection leaves no status line. The Layer dropdown
  includes Add layer, Remove layer, and Move layer with Move up/Move down.
  The row's ellipsis button directly toggles Advanced settings. Disable unavailable
  moves at the local layer boundaries. Add layer creates an empty local slot
  without opening a stimulus picker; choose its family and prepared file afterward.
  Reserve the advanced fade row’s minimum height after narrow reflow.
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
  Fade-in/out durations follow, then control entries. Link-capable texture rows keep
  Motion source and Linked to in the parameter columns above. Video hides
  Retain state and Linked to; 3D arena hides Retain state; Looming hides Linked to.
  Texture omits initial position/orientation controls and preserves imported pose values.
  Expose initial position/orientation for arena, Video and Looming in Advanced settings,
  Arena shows aligned Initial position XYZ (mm) and Orientation yaw/pitch/roll (degrees)
  sections. New arena X/Y default to zero at arena center, Z copies the configured subject
  height, and yaw/pitch/roll default to zero (forward +Y, level horizon). Require a finite
  configured height when creating an arena; validate before switching modes. A rejected
  mode change keeps the previous editor/selection and shows its missing-setting error.
  Later geometry changes preserve existing poses.
  Z edits the existing fixed height; runtime motion remains planar under V16.
  Use plain numeric inputs without type/reference selectors for all six fields.
  Preserve loaded pose values on unrelated edits; imported condition references remain
  read-only saved values instead of being flattened into numbers.
  All arena Advanced settings inputs share equal column tab stops: movement limits
  align with position, and wall clearance aligns with orientation. Descriptive region text
  spans the columns. Keep these stops at narrow widths.
  Arena movement limits appear first, above position/orientation, and use arena-file geometry by default with editable 30 mm wall
  clearance. Show declared file bounds as an authoring preview; protected Setup is
  authoritative. Preserve saved explicit regions and unrestricted mode. Retain boundary
  drafts in Protocol snapshots, Undo and Redo; invalid clearance blocks navigation/save.
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
  epoch end; durations too short reject the edit. Linked sources follow V02's
  source/target and feedback ownership constraints.
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
  a numeric sweep. Validate the resulting sequence on each automatic update. Materialize variants as
  flat canonical source epochs edited together through their subgroup.
  No Shuffle trial action is exposed; group-order and Setup seed ownership remain unchanged.
  Store optional batch labels and distinct generated-batch identities under V03.
  The trailing + appends a new subgroup; edits update the selected subgroup in place.
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
  shared per-face centered pixel rectangle and axis inversions. Usable view extents
  derive from measured X/Y mm/px and valid integer dimensions, using the assigned
  native resolution. Invalid or unresolved pixel sizes show a per-screen error.
  Retain geometry/corrections
  independently of projector enablement. Reopen the snapshot after changing settings;
  provide Play/Pause, scrubbing, previous/next epoch and playback speed. Reuse V07
  boundary state/retention and canonical expansion with an explicit example seed;
  bind linked textures through the runtime motion resolver using the snapshot geometry
  at each boundary, with the same pivot validation and reproducible backward seeking;
  reject unresolved random durations. This preview sends no device commands, applies
  no live Tracking and does not establish optical/runtime equivalence. Label unset
  geometry with a Devices configuration prompt rather than inventing tank dimensions;
  arena rendering remains approximate. Missing
  or unsupported content remains visible as an error, not silently substituted.
  Procedural texture recipes use the renderer's generator and declared/default seed,
  not their preview-file thumbnail. Bound generation before allocation and display
  linear recipe samples in sRGB for the operator monitor; unsupported dependencies
  or transfers retain explicit errors.
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
  only edited projector rows change on automatic update. Shared duration, prepared file, applicable
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
  Epoch subgroup titles show only the supplied name; unnamed subgroups use
  Epoch 1, Epoch 2, and so on in sequence order, without a Batch prefix.
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
  Physical-screen direction authoring uses the shared rig frame: Right0°, Front90°, Left180°,
  Back−90°, with wall flow interpreted in V02's unfolded plane. Apply the same
  convention to per-projector controls, batch/condition edits and new variation
  rules. Convert to each screen's existing mapped Cartesian motion fields; texture
  translation remains rig-fixed independently of rotation. Preserve untouched local
  phase functions and saved legacy variation semantics. Legacy variation rows label
  their local or earlier rig convention; recreate those rows to use current rig directions. Shared layers
  with incompatible screen frames require per-projector editing. Visual-angle
  sources retain their explicit angular-frame controls and units.
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
  Inventory actions are ordered Connect selected, Connect all; omit Test selected.
  The selected action becomes Disconnect selected while that camera is open or
  cleanup is pending, including a session-disabled camera. Connect all connects
  enabled cameras sequentially, skipping those already connected, without changing
  participation. It becomes Disconnect all when all enabled cameras are connected
  or any enabled camera has pending cleanup; bulk disconnect releases enabled open/
  cleanup-pending cameras sequentially. A failed/cancelled Connect stops the remaining
  batch and retains previously connected cameras; Disconnect all attempts remaining
  releases after an individual failure. Cancellation uses the initiating bulk button
  and existing per-camera cleanup. Lock camera edits while the batch is pending;
  stop on authority/connection loss, and derive final labels from confirmed state.
  Keep unrelated disabled cameras untouched. Managed
  role assignments commit through E07 without changing the role's participation
  flag; Use remains an explicit Cameras choice.
  Connect starts A10 manual capture and then Shows its acquisition-owned OpenCV
  window for the confirmed run; Disconnect stops capture and releases preview. Native X closure leaves capture running; backend
  visibility evidence updates the GUI selector. Show first reveals a Win32 preview
  at its measured initial size and position in the current Preview grid, after
  hidden creation/placement and without activation: Dashboard's runtime preview layout, or
  below the existing HUD/log column on Devices/Cameras and Tracking. Keep the HUD and log
  at their existing top/right alignment; do not add a third column that shifts or
  narrows them. On Cameras/Tracking show Preview only while at least one preview is reported open;
  share remaining height with the log then. When the last preview closes, hide
  Preview and let the log reclaim its height. To place the first opening, measure
  the expanded-frame layout temporarily and restore its prior visibility even on
  failure; measurement does not declare a viewer open. Native Review X closure
  updates visibility even in Observer mode. Fit the initial image to available
  space. The shared runtime/review shell opens maximized
  and reapplies maximization once after the first native/layout event pass; later
  operator Restore remains available.
  Other tabs reclaim Preview space. Previews remain detached,
  never embedded or reparented. Preview uses bracketed native-window footprints instead of
  ordinary cards, each captioned with its source (`[ BEHAVIOR CAM ]`); the native window
  carries no title text and `[ PREVIEW ]` names only the empty footprint. Retro doubles
  each bracket and shows static, centered `-- NO SIGNAL --` text without a caret
  in an empty footprint. Dashboard
  reserves named footprints for active experiment streams, including waiting or
  unavailable viewers. Camera footprints additionally require video recording selected;
  an already-open viewer retains its frame and Hide control until closed. Recording
  changes do not send viewer/capture commands. Reported visibility alone controls
  Show state. Cameras includes only
  enabled camera identities from its current drafts/readback, excluding Tracking
  and Visual stimulus streams and disabled cameras even if connected or visible.
  Its Preview visibility/log compaction follows only those eligible cameras;
  Dashboard retains all its source types. In-page grids arrange only open eligible windows: one
  centered full-area footprint, two side by side, three/four in two rows, then
  additional two-column rows. Fit the largest bounded square in each footprint.
  Reflow existing untouched native windows when the grid changes. Any operator
  move or resize opts that window out of automatic placement until close/reopen
  or an explicit centered Snap button restores that source's grid position/size;
  GUI translation and minimize/restore preserve this choice. A layout refresh may
  update only an existing viewer and must never reopen one closed through X.
  Both pages retain external OpenCV previews. Dashboard hosts them in its runtime
  preview layout (G02): the footprints share the Dashboard window, so native viewers
  follow that one host. Its stream grid chooses up to three columns to maximize the
  fitted square size over the shown streams; showing or hiding a stream reflows it. Leaving
  the Dashboard tab or the runtime layout hides the viewers without ending capture or
  clearing their Show state; returning restores them. Cameras retains its in-page grid.
  Switching pages retargets the native display owner only within the same verified GUI
  process; native windows remain above their current host, following its movement and
  hide/minimize/restore. Restore refreshes the geometry baseline without clearing
  a previously observed manual opt-out. Fix the Cameras/Tracking log to four visible
  text lines while its in-page Preview is shown; on this
  collapse scroll to the latest entry. Retain manual scrolling thereafter and
  restore expanding height on last close.
  Initial measurement uses the same compact log geometry and restores it on failure.
  Choose the
  largest initial square within the existing size bounds that fits the footprint's
  visible intersection with the desktop, and center its native frame there. Include title bar, borders and platform minimum frame width; report
  insufficient visible space instead of opening a frame over neighboring controls.
  Local Cocoa Review converts its work-height window origin to the Qt desktop
  origin; Windows retains physical client-to-screen
  coordinates and native DPI metrics. Review and Windows runtime previews use
  a native owner link to remain above their GUI without global topmost status or
  activation. Follow GUI movement and minimize/restore; minimization retains the
  open viewer and Show state, without changing capture or interpreting it as X
  closure. Windows verifies the exact GUI process lifetime and top-level window
  before linking; stale/missing owners fail the display only, requiring explicit
  Show after reconnection. The GUI identity hint grants no device/process authority.
  Reopening samples the current layout. When the requested source has no eligible
  slot on the current page, retain monitor-constrained placement beside the GUI;
  an open window remains freely movable. A10 owns padding and wheel zoom/reset.
  The GUI owns no camera display reader. Disconnect releases an
  editing/cleanup owner when no capture is running. Camera/pulse settings remain
  locked while a camera is owned until E07 live-edit adoption is implemented.
  Pending commands lock repeated submission; failures remain visible and queued
  intents are discarded on controller disconnection. No Setup readiness is claimed.
  Manual Connect/Disconnect operates independently of experiment Use and never
  enables participation; A10 retains capture, ownership and complete-input checks.
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
  Changing the path clears stale hints. Omit Save camera settings: edits and PFS
  hints remain local drafts until an explicit selected-camera action or normal
  configuration submission. Connect submits the selected complete draft and performs
  required A10 SDK import/readback before capture; A10 owns identity-only diagnostics.
  Retain an unchanged imported baseline without reimporting on later rate edits.
  A filename alone cannot establish the imported baseline required for capture.
  Import does not enable a camera for experiment. Snapshot loading is silent;
  incomplete hints remain drafts. Require Configuration/control and controller
  confirmation before treating any change as applied.
- Camera, MCU and Projector settings can be drafted in any order. Incomplete local
  values survive snapshot polling and do not become accepted controller state or
  silently reuse earlier values for an explicit action. Keep participation independent
  of wiring and retain device settings when Use is disabled. Show concise missing
  prerequisites beside the affected action and contextual wiring access in Cameras
  only. Identity checks require only their actual inputs;
  capture, pulse tests and calibration require their own complete selected inputs.
  E07 still validates submissions and all participating Setup dependencies; local
  readiness hints never establish hardware or experiment readiness. Projector patch
  placement, presentation pacing and the MCU flip-input connection remain distinct
  settings with their existing V20/V22/A11 owners. VSync mode
  remains editable when the photodiode patch is disabled.
- Managed MCU connection/pin tests use controller-confirmed COM/pin/rate values.
  Pending commands lock edits and repeat tests. Camera Connect selected/all, MCU
  Test connection/pin Test and the read-only SpikeGLX connection check replace their
  initiating button with Cancel, then disabled Cancelling while the current bounded
  call settles. Cancellation skips remaining steps without aborting transport or
  extending the in-flight deadline. Confirm cleanup of newly created camera/MCU
  resources before reporting cancellation; retain pre-existing resources and accepted
  settings. Cleanup failure, lost authority/connection or changed generation remains
  an explicit unconfirmed outcome, never a successful cancellation. Firmware Upload
  and safety Stop/Disconnect retain their existing completion behavior.
  A11 diagnostic observations drive
  Test/Stop state; a bounded follow-up status query begins after confirmed execution,
  and control/connection loss cancels local timers. Firmware/edge reports do not prove
  physical receiver wiring.
- Cameras also exposes the selected role's MCU output pin beside trigger frequency.
  Synchronize it with the same Microcontroller draft and retain authority, capture
  and diagnostic locks; the existing identity-fenced contextual editor remains.
- Microcontroller owns one selected COM port for all camera triggers. Cameras and
  their contextual editors use that same port and the relevant output pin; edits update the MCU draft rather than creating another controller or mapping. COM discovery uses the shared compact Refresh icon
  beside the port selector, distinct from Test connection. Scan ports lists discovered COM-number names with
  the available device description, preserving the port identity separately and
  a still-present selection without opening devices. Do not expose
  macOS/Linux serial device names or invent a second controller in the draft.
  Projector flip is deferred under A11; omit Inputs and Add input. Show Trial state
  output and logical Behavior/Tracking/Eye camera outputs with explicit pin editors
  and Test/Stop. Every supported output row has Remove: clear its pin and disable fixed
  I/O signals while leaving camera participation/source/rate unchanged. Unassigned
  rows are hidden and empty table headers disappear. Add input/output offers only
  missing supported signals with an explicit pin; readding fixed I/O enables it.
  Camera outputs can be added before physical discovery/assignment; no free-form
  signal or duplicated camera rate. Camera inventory is titled Available cameras;
  omit the explanatory text beneath its action buttons and retain wiring tooltips.
  SpikeGLX retains its own Add/remove table and hidden empty header. Inventory
  headers retain Refresh when empty. Camera output assignment/removal changes wiring only;
  clearing a camera pin never changes Cameras' Use flag or timing source. Fixed input/
  output enable flags retain their signal meaning, independently of camera/projector
  participation. Eye has an independent A11 output; its pin/rate remain explicit and
  rig acceptance does not follow from adding the GUI row. Contextual editors close
  on role/inventory or authority loss and obey the same editing/diagnostic locks.
  Cameras owns participation, source and rate; Microcontroller owns port and pins.
  Fixed input/output enablement is retained draft configuration in isolated review. Disabled signals cannot start tests
  or participate in experiment pin conflicts. Explicit diagnostics also check their
  target against active signals. Wiring edits obey editing and diagnostic locks. Omit Save pins and Apply pin settings: managed clients submit completed pin
  edits, selected COM ports and
  fixed I/O enable changes through the existing controller configuration request
  only when the applicable proposal is complete; otherwise retain them as local drafts.
  Inventory refresh and saved-state loading are silent. Lock managed edits during
  diagnostics; connection/pin tests still require confirmed configuration.
  Pin editors display decimal numbers without a D prefix and accept numeric entry.
  Existing D-prefixed saved/controller pins restore as numbers; submission encodes
  the same canonical firmware token under A11/E14. This presentation change never
  flashes firmware or changes physical pin ownership/test behavior.
  Disabling a signal stops its active diagnostic; editing authority gates enablement.
  In the explicit local real-device diagnostic mode, Test connection and per-pin
  Test/Stop use A11's exclusive
  serial owner and continuous diagnostics until Stop. Poll matched status every
  500 ms to renew A11's firmware communication lease; no elapsed test limit. Display matched connection, start,
  stop and edge-count evidence or the actual failure; a command request alone is not
  a pass. Lock port/scan and pin editing during
  a diagnostic, stop on phase/control loss and close the port on window closure.
  Isolated frontend fixtures retain labelled, command-free review tests.
  Fixed active-high Trial state belongs to A11; no level selectors remain.
  Camera test rates are read from Cameras rather than duplicated here. Output tests
  target one pin for observation in SpikeGLX. Test requests require Configuration/control, a COM port,
  a nonempty pin and no target-pin conflict; camera requests additionally require an
  supported logical role and valid requested rate, independently of camera Use or
  timing source; this explicit pin diagnostic never starts camera capture. Managed diagnostics retain
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
  Below the inventory, sections are ordered Rig geometry, Projection calibration,
  Projection synchronization. Projection calibration uses a CephVR1.0-style per-face table containing
  paired integer Width/Height, separate Offset X/Y columns in pixels and inverse-axis controls.
  Omit table arrows; Up/Down keys step by exactly 1 px through the existing draft/live-update path.
  Partial typed input is retained; fractional dimensions fail validation. Rig geometry owns tank
  dimensions and fixed subject distances labeled Subject → Left wall / Front wall /
  Bottom (mm). Perpendicular distances to Left, Front and Bottom screens sit below these
  in the Rig geometry card. The screen-dimensions table contains width, height,
  derived read-only estimated projector distance, with wrapped headers.
  Pixel-to-mm calibration precedes the projection correction card within Screen
  calibration, matching the calibration workflow. Both are sibling cards, without nesting.
  Put Launch projection calibration above the correction table and Launch reference
  calibration above the measurement table. Omit description/prerequisite text
  inside both calibration cards; launch validation retains its existing behavior.
  Effective throw ratio is config-only. Pixel-to-mm calibration omits explanatory text and pixel-span columns;
  its table has Screen, paired Measured X / Y (mm) inputs under one header, and
  read-only X / Y (mm/px) estimates, with all three columns stretching evenly.
  Per-screen measured horizontal/vertical reference bars retain native output
  dimensions and config-only `reference_x_px` / `reference_y_px` lengths. These
  lengths control the actual calibration bars and the same conversion arithmetic;
  positive whole pixels must fit the assigned output. Older files migrate their
  original quarter-output spans; unset lengths retain those defaults until the first
  measurement fixes them. Complete
  measured pairs estimate mm/px independently of throw ratio; projected distance
  additionally requires a positive throw ratio. Display derived projector distances
  in millimetres with exactly one decimal place; measured mm/px and mapping
  calculations retain their existing precision.
  Known millimetres derive independent X/Y mm/px and full projected
  image dimensions; full projected width times throw ratio estimates ideal throw
  distance (Bottom: total folded path). Subject-to-screen distances stay independent.
  Measurements from another assigned projector are cleared; imported historical
  distances remain visible until measurements are supplied. A partial
  pair keeps the earlier distance and cannot produce a calibrated mapping. Clip/tolerance settings remain in Rig geometry without an Advanced
  subtitle. One Load… / Save as… action row handles the complete rig, projection
  limits, all-screen correction/dimension values, synchronization and participation
  plus reusable runtime profile references under the
  [GUI calibration contract](../../contracts/gui-calibration.md), replacing the
  per-screen profile picker. Validate the complete bounded document before applying;
  invalid files preserve drafts. Save atomically, retain unset values, respect editing
  authority and cancel pickers on authority loss. Full version 9 retains reference
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
  pattern into one of exactly two repository assets: `reference_bars.glb` contains
  a raw output-boundary frame and native-pixel bars; `frame_grid.glb` contains the
  measured physical frame/grid.
  Refresh only the selected file. Generated display/geometric profiles and an exact
  working copy live in separate per-step user runtime directories, independently of
  Protocol Assets. Missing/unwritable source or runtime files reject preparation
  without a launch request. Reference measurement renders a white native output
  boundary frame and raw-pixel bars on black, ignoring saved measurements and
  corrections. The initial frame supports aiming/focus/rough physical positioning;
  it does not claim the usable screen boundary or known mm scale. Align first,
  measure bars, then use the measured physical frame/grid for Width/Height
  refinement. Frame/grid
  adjustment requires complete measurements matching each native mode and uses
  mm/px directly with rig geometry; neither action requires projector distance or
  throw ratio. The mapping uses measured X/Y mm/px with physical screen dimensions
  and inversion.
  Projection calibration offers Width/Height in output pixels instead of Scale.
  Blank dimensions derive from physical screen size divided by measured mm/px,
  rounded to whole pixels and bounded by the native raster. Explicit whole-pixel
  dimensions define a valid rectangle, at least one pixel per axis. Cap edits at native
  Width/Height; center-relative integer Offset X/Y translates the window right/up,
  capped at plus/minus floor((native size - valid size)/2). Expanding a size reclamps its offset.
  Blank offsets mean zero. Numeric8/full11/review6 retain these pixel offsets; older
  removed offsets remain discarded and fractional legacy sizes round on migration.
  The usable physical view is valid Width/Height multiplied by measured X/Y mm/px
  and permuted into the physical surface axes (Bottom depth uses raw Y),
  centered on the physical screen plane placed from the 5 mm frame-gap references.
  Preview and newly prepared views share these extents and fixed-pitch mappings.
  Prepared GUI affine views render at their valid pixel resolution. V14 texture
  parameters retain physical units/shared phase; changing crop never rescales them.
  Saved profiles, live diagnostic cropping, prepared rendering and Idle retain
  the translated crop. Diagnostic grid assets/views span the full measured native raster;
  enlarging the live window reveals additional world-phase grid lines at fixed pitch.
  Isolate each diagnostic face plane to avoid overlap occlusion. A visible frame marks
  the crop, with a smaller centered screen name formed from contiguous glyph cells. Imported warps remain protected;
  missing measurements reject a GUI-owned crop. No throw ratio/distance is required;
  reject corrections extending outside the output. Submission publishes new
  content-addressed measured affine assets for GUI-owned 2×2 profiles, preserves
  originals and rejects replacing imported nonlinear/masked/weighted calibration. Reject missing or
  ambiguous monitor bindings.
  Failed preparation does not send a launch request.
  Unmeasured profiles are diagnostic placeholders; measured affine mappings
  still require optical acceptance and do not set experiment defaults. Both actions
  target all four assigned projectors together;
  during an active frame/grid presentation only Width/Height and Offset X/Y remain
  editable. Debounce valid edits into bounded normalized mapping updates without
  rewriting protected assets, reopening windows or changing rig/measurement state.
  Coalesce newer edits behind one in-flight update; invalid/partial edits retain
  the last confirmed projection. Exact active diagnostic, controller/renderer
  generations, configuration revision and increasing adjustment sequence bind each
  update. Lost authority/disconnection, closing/unknown state or another diagnostic
  discard pending live intents; no stale replay. Actual all-output presentation
  confirms the new sequence. During confirmed active reference-bar presentation,
  measured X/Y millimetres remain editable and update retained drafts/derived estimates;
  pixel lengths/native modes, rig geometry, assignments and corrections remain locked.
  Measurement edits do not rewrite protected inputs or send display updates. Pending,
  unknown or lost-authority states retain the measurement lock. Other projector controls
  stay locked until closure.

  After confirmed output activation the active step's launch button reads Close:
  reference bars use Launch reference calibration, frame/grid uses Launch projection
  calibration; placement actions are defined above. Disable other diagnostic launches
  while a view is active and all actions while pending.
  Restore launch labels only after confirmed closure. Failed/pending commands never claim an
  output-state change. These actions and Close control V01's diagnostic presentation outside
  trial timing; preparation sends no output command.
  Retain per-face drafts without adopting measured defaults. Planar geometry
  conversion retains all four inward-facing surfaces and the fixed observer.
  Subject distances position screen planes independently of tank walls, parallel to
  their corresponding faces. Front and Bottom are centered across the tank width.
  The frame separates usable screen regions by 5 mm at both lower and front
  junctions, declared in the GUI policy. Front/Left/Right lower edges sit at subject Z
  minus subject-to-Bottom-screen distance plus 5 mm; physical heights stay unchanged.
  Changing Bottom distance moves all four screens vertically together. Side and Bottom
  front edges start 5 mm behind the Front screen plane, extending toward the back
  using their own dimensions. Bottom image width/X runs front-to-back (+rig Y);
  height/Y runs across the tank (-rig X), so 126×94 mm retains a 94×126 mm footprint.
  The Bottom projector is below Right with the same physical orientation and a
  folded mirror path. GUI-owned
  mappings rotate surface coordinates 90° before the saved output-axis inversions:
  (u, v) maps to (1-v, u). Output-axis inversions follow the operator's physically
  verified calibration; preview placement must not require an additional Y inversion.
  Raw pixel widths/heights, offsets, reference bars and masks
  stay output-local; Bottom surface extents/pitches and render-target axes swap.
  The rig preview undoes the Bottom portrait quarter-turn and folded optical mirror
  when placing its raster onto the physical plane; output-local calibration remains
  unchanged. Imported warps retain
  their declared mapping; regenerated GUI profiles adopt this correction at fresh Setup.
  Numeric version 6/full version 9 retain pixel valid-area dimensions and migrate
  older Scale bounds to crop sizes using retained native measurements; reject a
  non-neutral legacy Scale without enough dimensions to migrate truthfully.
  Older Bottom physical-axis migration remains. Review draft version 4 follows
  the same conventions. Changing Front distance moves these shared front edges. Require
  finite positive screen dimensions/distances; unset values never imply tank-wall
  placement. The owner-selected parallel-plane editor assumes equal left/right
  tank-wall offsets: right subject distance = tank width + left screen distance −
  twice subject-to-left-wall distance. Right distance has no independent editor or
  stored JSON field. Recompute for both diagram and projection; invalid/missing
  inputs cannot retain a stale right plane. Version 1 calibration import checks any
  explicit right distance against this rule before adopting; unequal offsets reject
  the whole load. Version 2 saves only independent calibration values.
  Diagram and projection conversion share the same corner calculation.
  Projection synchronization is the last Projectors tab, following Rig geometry
  and Projection calibration. It offers Free run (no VSync), VSync on pulse display, and VSync on all
  displays under V20, without an MCU input prerequisite or contextual MCU editor.
  Projector flip and camera-trigger phase offsets remain deferred under A11,
  independently of presentation pacing. Existing mode labels migrate on draft load.
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
  visible independently of participation. Clickable legend entries independently
  toggle Tank, Screens, Projection and Subject, without separate plot buttons. Projection groups
  projectors, rays, footprints and mirror in both visibility controls and one legend
  entry; footprints use a distinct violet color. Retain view choices through draft/phase changes; they never alter output
  participation, calibration or runtime control. The legend stays visible and identifies
  line/dot colors and ray styling; hidden groups retain dimmed clickable entries.
  Legend clicks do not rotate the view. These outlines are an operator estimate,
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
- SpikeGLX connection omits explanatory prose. Dashboard Recordings owns the
  Save spikeglx checkbox; Devices retains connection/mapping controls. Pairing is the E12 per-session
  synchronization enabled flag, editable with Configuration/control authority through
  revision-checked controller configuration updates. Pending edits disable repeats;
  display confirmed values and retain them on rejection/disconnection. The tooltip
  identifies the host-file new-session default; endpoint settings remain read-only.
  Test connection remains read-only and available without editing control, independently
  of pairing; connection success does not start recording.
  SpikeGLX exposes local channel-mapping drafts for discovered camera roles, Trial
  state and photodiode only while pulse generation is enabled; no new Projector flip
  mapping source is exposed while A11 is deferred.
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
  Dashboard System controls shows read-only Cameras, Visual stimulus and Tracking
  status radio indicators inside the card below its title and above two equal-width
  buttons side by side. Show Cameras only with enabled cameras and Tracking only
  when saving tracking velocities or using closed-loop mode; Visual stimulus remains
  required independently of its video-saving choice. Preview
  System controls omits those indicators. One primary button reads Setup in Configuration/SettingUp/Ended
  and Start after preparation; enable Start only under current Ready and authority
  gates. Keep Setup disabled during preparation and preserve Stop cancellation.
  Subject age is labeled Age (dph); experiment phase appears in the HUD only.
  The primary button's Setup action requests
  preparation in Configuration and E05 New session in Ended; the latter returns to
  Configuration after cleanup and still requires fresh Setup/Start.
  Interrupted sessions return there automatically through E05 after confirmed cleanup;
  reflect the controller's Configuration state without a GUI New session command.
  In Ended, configuration editors unlock as next-session drafts only after confirmed
  cleanup, synchronized configuration and current operator authority. Retain those
  drafts through New session; completed-session metadata remains immutable.
  Configuration remains editable after failed/cancelled Setup returns there;
  device operations and replacement Setup retain controller cleanup/admission gates.
  Stop requests Cancel Setup in SettingUp/Ready. During a session it opens a chooser:
  Stop now maps to E06 Abort now, Stop after trial retains E06's trial-completion meaning,
  and Cancel/window dismissal sends no command. The chooser keeps current phase/control
  gates, closes when none remain available and rechecks authority on selection.
  These contextual controls replace the redundant Session menu; backend commands remain
  distinct and no automatic session progression is introduced.
  G02 owns the current compact HUD rows. Dashboard excludes trial-plan
  editing, backend participation/use editing, the separate session-progress card,
  embedded previews, the design-review banner, frontend footer and header
  connection/local-control badges. Removing badges does not change command authority.
  Camera experiment enablement belongs to Devices. Dashboard shows a video-recording
  switch for each camera role and Visual Stimulus, plus Tracking velocities.
  Recording selections are retained but disabled while their source is inactive.
- Dashboard side navigation places Configure and Monitor beneath Dashboard in the
  main sidebar, reserving no second content column. Disabling the shared G02
  navigation preference restores the top tab bar. Configure shows the session
  form; Monitor shows the runtime preview layout. Entering a run phase (Starting,
  Running, Stopping, Finalizing) switches to Monitor and leaving it switches to
  Configure; only these transitions switch automatically, and the operator may switch
  either way at any time (Monitor before Start shows no previews; editing stays gated
  by the existing session locks). There is no separate window or geometry preference.
  The Dashboard's own System controls card (with its backend indicators) moves
  unchanged into Monitor's top row, stretching to that row's height, and returns to
  the form afterwards; it is never duplicated. A Timeline card holds the epoch timeline
  only. A separate full-width Preview controls card below it holds the Video/Advanced
  previews toggles in its header, then a Video row with one
  checkbox per stream (named by the stream; checking opens its viewer when ready) and an
  Advanced row with one checkbox per projector; each row shows only while its master
  toggle is on. Only shown or opening streams take frames, so unchecked streams free
  their space; reasons for an unshown stream appear in its checkbox tooltip. Hidden
  projectors free their space in the Projectors card. Stream frames keep no
  background. Recording selections and Session config are not shown in Monitor.
  Show a compact HUD using the Dashboard's same status, trial and time values, as
  label-aligned columns, with no recording lamp or symbol text. The HUD is the
  middle card of the top row, between System controls and Console. Advanced previews
  is a standard checkbox in Preview controls, enabled independently of operator authority.
  A **Video previews** checkbox beside it (default on, remembered locally) shows or
  hides the stream section; hiding closes any open viewer through the normal Show
  request, leaves capture unchanged, and Show must be chosen again after it returns.
  The current trial (or selected draft) epoch timeline
  always spans the full body width in its Timeline card directly below the HUD.
  Below Preview controls,
  streams fill the available width when Advanced previews is off (default,
  remembered locally). Enabling it shows a fitted grid of projector
  cards on the right at one third of the available width; a draggable splitter
  resizes both sections continuously. Every projector source, including linked
  followers and stationary baselines, gets a card with a plain colored heading.
  Order projector cards Left, Front, Right, Bottom across rows, with other sources
  after them. Omit the reference suffix and repeated projector/stimulus titles inside
  instruments; retain accessible dial names. Use16px section/card gaps and divider
  spacing. There are no per-source visibility toggles. Center each instrument in its grid
  cell and choose rows/columns to maximize their scale within the available width
  and height. When projector cards fit in a single row, center that row vertically
  in the section, keeping headings with their instruments; multi-row grids use the
  available height. Scale the complete instruments proportionally, including labels and
  readouts, so every card stays visible without horizontal or vertical scrolling.
  Advanced size lanes remain aligned to the timeline.
  Stream grids choose up to four columns to maximize square frame size, including
  three or four streams in one row when larger than a two-column arrangement.
  Frame headings keep brackets with their words. These controls never change Show
  state, capture or execution. Each dial's arrow gives direction and, against labelled rings, speed;
  a surrounding signed ring gives angular speed with CW/CCW and °/s. Stationary
  translation has no arrow but reports current planned orientation (layer rotation
  or arena yaw, normalized to 0–360°), including continuity/reset semantics; it does
  not retain the last movement direction. Unavailable/feedback-driven samples keep
  their explicit messages. Texture dials show each projector's own planned motion in arena coordinates
  (Right 0°, Front 90°, Left 180°, Back −90°). Physical sources use V02's
  calibrated unfolded plane and retained layer rotation; angular sources use the
  standard face display rotations. Tracking-form dials show a longitudinal/lateral mm/s vector: live Tracking
  drive commands, and authored position trajectories as planned velocity in the moving
  layer's or arena's heading frame. Arena previews add a top-down virtual-world map of
  the path so far and current pose beside their tracking-form dial; feedback-driven
  textures pair their texture dial with the driving tracking dial. Never mix units on
  one dial. A source whose width or height varies adds a planned size lane (deg or mm)
  aligned to the timeline. Refresh at5Hz. While running,
  advance planned time locally between reported elapsed-time updates; stop advancing
  on disconnection or a non-running phase, and clamp to the planned trial end.
  The epoch timeline and size lane share a60s window that pins trial start to the left
  edge until current time reaches its center, then keeps current time centered. Draw
  solid size history through current time and the remaining planned size to the window
  end as a dimmed dashed trace. Clip traces and epoch blocks to that range and keep
  nonnegative absolute trial-time ticks at5s intervals, coarsened to multiples of5s
  on narrow plots and never overlapping, to keep clock labels readable.
  Format timeline axis ticks as mm:ss while the visible range stays below one hour;
  switch all ticks to hh:mm:ss when its right edge reaches one hour. Hover readouts
  remain hh:mm:ss; legend entries omit units.
  The not-measured caveat lives in the card tooltip, not a context line.
  Hovering the timeline shows time, epoch and each source's planned values; clicking it
  inspects a planned instant until the next refresh. Group the same projector/layer
  across epochs, with separate plots for each surface of a shared source. Linked
  follower dials use V02's calibrated renderer link binding at each epoch boundary,
  preserving V07 retained phase/orientation, stop and reset behavior. Convert each
  follower's resolved local vector through its own calibrated surface into arena
  directions, retaining its own angular speed, orientation and trial-wide scale.
  Leftward Bottom rotation shows Bottom rotation, Right toward Front, Left toward
  Back and Front toward Left; reversing rotation reverses these directions.
  Use the current loaded or edited projector geometry and rebuild the plan when it
  changes. Missing or
  invalid geometry, references or motion remain explicit per-source unavailable states.
  Unsupported sources explain their limits without hiding valid sources. Reuse canonical
  bounded expansion/function evaluation; planned values are not measured output or
  timing evidence. Unresolved duration/order and combined texture motion show as
  unavailable. Live-only dials and poses stay visible but empty, showing Waiting for
  tracking, until reported values reach the GUI; previews introduce no commands.
  Frame headings use source labels, Show checkboxes and pending/error details with
  shared hover/focus styling. An empty workspace explains
  that no streams are enabled. It contains no duplicate window heading,
  footer buttons or redundant Open/Hidden labels. Pending/error/unavailable status
  remains visible; the local review label lives in the window title.
  Checkboxes reflect reported visibility, including external-window closure; pending
  requests disable their controls with explanatory status. Unavailable sources
  remain selectable under existing authority, participation and recording gates;
  retain that local selection until ready, then issue one normal Show request.
  Unchecking, hiding Video previews, losing control, removing/deactivating the
  source or turning its recording off cancels the waiting selection. Once sent,
  reported visibility remains authoritative; do not retry a failed Show automatically.
  Preview rows are ordered Behavior cam, Tracking cam, any further configured camera
  roles, Tracking, Visual stimulus. Omit inactive closed sources from the workspace:
  a camera must be enabled for the experiment and selected for video recording;
  check both before Show, allowing Hide for an already-open unrecorded camera.
  Device diagnostics do not depend on recording selection. Experiment Tracking requires an active
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
  sample state only. Managed camera viewers use A03 session slots during Running;
  Show/Hide never enables manual capture or editing during a session. Visual stimulus
  is a managed Dashboard row: enabled participation plus current renderer-attested
  availability after Setup admits Show/Hide in Ready/Starting/Running. Commands use
  the current lease, session and configuration; visibility never changes recording.
  Its renderer-owned native window uses E13's cropped Left–Front–Right / Bottom
  display layout without labels or header spacing, the shared placement/owner binding, manual-position preservation
  and Snap. Native X
  hides it and updates the row. Tracking viewer integration and full-workload
  performance acceptance remain pending under E03/E08/E15.
- Output directory has an asynchronous existing-folder picker beside the editable
  path. Cancellation preserves the draft; selection rechecks editing availability.
  Camera Connect and the Dashboard selector target the same source identity and
  visibility state, with one backend-owned external viewer per source. The local
  isolated Review opens blank black detached OpenCV windows by default on camera
  Connect or an active source's Show, using the same placement helper. Keep the
  review label in the native title; omit image annotations, grids and animation.
  Disconnect/Hide and Review exit close
  them. Native X closure clears visibility while leaving the fixture connected.
  These blank images have no camera reader or runtime connection and establish
  layout review only, not acquisition or rig acceptance.
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
  thin solid neutral grid lines at the shared physical spacing, a clear screen border
  and one simple screen name. Omit center crosses, dimensions, rulers, rainbow/dashed
  lines and the tank outline. Existing physical screen planes and offsets remain
  authoritative; no separate placement-only/no-grid mode is offered.

<a id="g02"></a>
### G02 — Shared frontend formatting

**Status:** Accepted · **Revision:** 140

- GUI startup displays a compact text-only `CephVR2.0` / `Initializing` splash,
  using the saved Style (legacy fallback and unknown-to-Standard behavior retained),
  a thin indeterminate segment moving side to side and no terminal cursor. During
  widget construction, repaint only the splash without dispatching queued callbacks;
  animation uses elapsed time and stops on close. Standard uses white/blue,
  Retro coral/cyan and Amber amber/gold; Retro-family scanlines/glow respect CRT effects.
  Construct and style the main window while hidden, then maximize it transparently.
  After construction, deliver native expose/layout events and repaint its backing
  store before restoring opacity and closing the splash; do not queue a second
  maximize after reveal. Child controls must be parented before visibility changes.
  The managed GUI bootstrap shows the splash before frontend imports; it does not own devices,
  extend startup deadlines or wait indefinitely for controller connectivity. Startup
  failures retain their existing propagation and close the splash.
- Amber phosphor themes every popup and dialog surface: combo drop-downs open below
  the field with a dim-tint highlight (no solid accent slab or default scroller strips),
  message boxes draw Amber glyph icons instead of the native coloured ones, and expanding
  tab bars (Projector setup, Tracking) elide text rather than show Qt's unthemed
  scroll buttons. Microcontroller Inputs/Outputs use the standard card padding, and the
  review window shares one View menu.
- Amber navigation gives every main page, sidebar child and in-page tab a leading
  `>`; selected entries add a trailing `<`, with both markers, icon and label coral.
  Sidebar children show selection only while their owning main page is active;
  retain the current child for return and automatic state changes on hidden pages.
  Main-page leading markers are larger than child/tab markers. Idle entries are
  dim; hover brightens their markers, icon and label to cream. Reserve marker
  gutters so labels cannot overlap the trailing marker. Balance sidebar markers
  around the icon/title group: the gap from `>` to the visible icon edge equals
  the gap from the title to `<`. Exclude the icon width and icon-to-text gap from
  this outer spacing; account for transparent icon padding and native text inset.
  Reserve the trailing gap before eliding long labels.
  Each trailing `<` uses the same marker font and size as its leading `>`.
  In-page tabs use equal gaps around the rendered icon/title (including elision),
  with both markers positioned from the same native text bounds.
  Dim inks, borders, disabled text and hover fills keep at least
  4.5:1 (tabs), 4.0:1 (disabled), 3:1 (field underlines), 2.4:1 (card frames) and 4.5:1
  (dark text on hover fills) against the Amber surfaces. Disabled fields stay unfilled,
  placeholders use the dim tab ink, and table headers use the field-caption style
  (uppercase, tracked, regular weight, units kept, line breaks as spaces) with
  width-capped cell editors left-aligned under them. Read-only log consoles show the
  block caret only while focused, the epoch readout aligns with the first epoch tile and
  the unfilled Setup geometry card does not reserve the 3D view.
- Shared interface, label, title, console and sidebar fonts are enlarged by one pixel
  across Standard and Retro-family styles; retain their relative hierarchy.
- Runtime preview layout card titles, projector headings and stream headings use the same coral-red hue as
  the main GUI; retain the existing borders, type and console palette.

- Preview rate footers use two centered muted rows with one decimal place, following G01
  freshness and E08 measurement semantics.

- Runtime logs show the current action and observed ongoing states. Background
  inventory reads and routine admission remain silent. Append observed results to
  the original action row, preserving its timestamp: `[Done]`, `[Failed]`,
  `[Rejected]`, `[Cancelled]` or `[Unconfirmed]`; retain diagnostics on that row.
  Setup retains each observed preparation stage as a checklist row, including
  enabled camera preparation and observed MCU connection/configuration. Counts update
  within their stage; later stages never erase earlier ones. Required backend Ready
  or successful owning Setup completion finishes its observed rows; leaving Setup
  without that evidence marks remaining rows Unconfirmed. Stage changes alone never
  prove completion. Retain exact attempt/generation scope and do not replay completed
  checklists on reconnect. Coalesced snapshots can omit stages; never invent unseen
  device substeps, physical activation or recording. Replace bare Ready messages with
  the observed connection state or Setup complete/waiting for Start.
  Other actions update progress and stage changes in their existing row, preserving
  timestamps and unrelated rows; only terminal evidence appends a result.
  Finalization keeps Setup, Start/New session and protocol editors locked until
  confirmed cleanup. Use the exact latest retired session/trial evidence to finish
  existing rows across automatic Configuration reset; never replay old successes
  on reconnect. Missing/disappearing work alone never proves success. Omit separate success-result rows. Explicit startup recovery/deletion also emits one confirmed
  terminal result, stating whether files were preserved or deleted; never leave only
  its running message after success or replay old completions from retained snapshots.
  Preserve errors, rejection, cancellation and unconfirmed
  outcomes with details. Render each row as local `HH:MM:SS`, a bracketed uppercase
  subject column and a terse sentence-case step. Every entry has a category; use GUI
  when the message supplies no subject and retain an existing bracketed category.
  Widen each console's subject column
  to its longest observed category and realign retained rows when it grows, preserving
  timestamps, diagnostics and row identities. Keep the width until the console is
  cleared; skip exact consecutive repeats.
  Deduplicate unchanged snapshot/poll observations; never
  fabricate progress or readiness. Camera Live requires A10 frame evidence and
  session Idle requires confirmed cleanup. E04 audit records and retained technical
  history keep their existing evidence; these are operator-log presentation rules.

- Log consoles expose a vertical scrollbar only while retained/wrapped lines
  overflow the viewport, with a visible theme-matched handle in both appearances.
  Preserve G01's reading position and follow-at-bottom behavior.

- Device subtabs preserve their text color on hover. Tracking places Load/Save beside
  Pipeline and diagnostic/annotation actions in a separate, evenly sized row.
  File actions use Load… / Save as… captions across tabs. Devices' Configuration
  file cards share a Load-first row with equal-width/equal-height buttons, zero
  inner margins and the shared field gap, including Projectors.
  Inventory Refresh shares one icon/size/accessible-name helper and header placement;
  port discovery uses that same control beside its selector. Participation is the
  first Use column; inventory row selection shares the same behavior. Shared table
  fitting handles hidden signal headers without leaving an empty header gutter.
  Projector measurements content-size Screen and derived scale columns, leaving the
  measured X/Y pair the remaining width. Display mm/px with one decimal without
  rounding calculation inputs. Pair calibration Offset X/Y in one column like Width/Height.
  Caption the projector diagrams Displays layout (without the Display IDs suffix)
  and Setup geometry. Caption shared log cards Runtime log and the projector timing
  card Photodiode. Its caption uses the shared content-sized title/frame gap.
  SpikeGLX Input channels sizes Use to contents so its heading stays on one line.
  All tab HUDs share Dashboard formatting through the shared StatusColumn row renderer:
  uppercase labels, one aligned value column across groups, Retro colon separators,
  explicit blank-line section spacing and shared fitted-console/palette treatment.
  Appearance switches re-render retained rows without changing values or diagnostic
  state. Tracking's status/log column follows this shared appearance independently
  of its controls. Preserve each tab's information until separately reviewed.
  Camera HUD shows found/enabled counts, a separator, then selected camera role,
  connected status, Trigger source (Internal clock / External controller),
  controller-configured external Trigger rate and backend-received
  acquisition rate. Missing rate readbacks remain unknown; never substitute a local
  edit or configured trigger frequency for measured acquisition rate.
  Shared directory/stimulus path fields accept Ctrl and Command-style select-all,
  copy, cut and paste, preserving full path text and existing validation/edit locks.
  Focused paths use native text/selection painting even when read-only.

- Standard uses the current CephVR1.0 Dashboard as the visual template: dark blue/black
  surfaces, subtle bordered cards, blue primary actions, muted red stopping actions,
  Segoe UI control text and pink monospace HUD/log panels. Use the shared coral
  accent for page headings, selected sidebar labels and active subtab text; keep
  form labels neutral, use bright blue coordinate headers and retain blue action/focus treatments. Embedded stimulus plots
  are excluded from the initial Dashboard increment.
- Review and runtime offer the same window-bar Style menu with Standard, Retro
  console and Amber phosphor. Amber phosphor is a Retro-family style modelled on
  the owner's satellite HUD reference. It keeps Retro's fonts, glyphs, prompts and
  CRT rules on cool near-black, with red-orange card titles shown as `< TITLE >`,
  pale-gold values over readable muted amber labels, slightly lifted dark surfaces
  and frames, and wide-tracked regular headings. Cards
  are recessed to the log surface with a dim outline and bright corner brackets;
  HUD/log cards keep only corners and centred edge segments, with unboxed text and
  dim log column titles aligned to the log columns. Fields are underlined, checkboxes
  inset (hover brightens the box and label), tabs unboxed with dim text/icons and
  corner brackets (gold current tab, dim hover), table headers plain over a dashed rule, nested cards
  as flush subsections, epoch tiles neutral with the epoch name above one tint bar
  and `Epoch N · duration` below, subsection headings shown as `| NAME |`, and the page heading omitted.
  The sidebar wordmark is centred and navigation is left-aligned: `< Icon Title >` with bright brackets when selected, dim
  brackets on hover. Selected text stays coral-red under hover; repaint
  navigation icons and labels on the checked-state signal before page-layout work. Buttons rest as plain orange outlines and fill orange
  on hover; Stop, Abort, Disconnect and Cancel actions do the same in red; disabled
  buttons are dim outlines and toggles fill only when checked. Selection elsewhere (trials, group/epoch blocks, batch bands) has no fill: pale-gold
  text and a bright outline. HUD and
  log text share the value colour; wrapped log rows continue under the message
  column for display only (copied text is the stored row). Focus is bright amber,
  ready lamps are cream, waiting is orange and faults red; Amber phosphor has no cyan. Its CRT scanlines
  remain stronger than Retro but softened for readability, so bright fills read as striped. With CRT effects on, Retro-family
  popups, menus and owned windows carry the same scanline film. Exclude projected
  preview image areas (trial rig/surface canvases and native preview footprints)
  from scanlines, vignette and refresh band; surrounding controls retain the style.
  Decorations are display-only: stored
  titles and headings are unchanged. The palette follows the owning window.
  The Style menu retains a shared frontend preference with legacy Review fallback.
  Retro console
  styles Dashboard, Devices, Tracking, Protocol planner/editor, Previews selector and window chrome with green-black surfaces, blue frames
  and actions, muted red-orange card titles, cyan page headings and field labels,
  restrained amber branding, pale green readouts/logs, cyan navigation/focus and warm warning/stop
  accents, unnumbered uppercase card headers, aligned monospace HUD columns, square
  controls and instrument frames, labelled glyph status lamps from the current view,
  and card/terminal edge ticks with periodic longer marks,
  dashed section rules confined to the HUD, and cyan focus corners on styled editors.
  The HUD shows Status (reported outcome when available, otherwise current phase)
  with a blank-line gap before Trial and the Trial time/Total time elapsed / duration
  pairs. Omit Control and separate Phase and Outcome rows.
  Trial time uses authoritative timing. Total time shows planned schedule progress:
  preceding configured trial durations/gaps plus current trial elapsed time and
  reported gap progress, excluding preparation/finalization overhead. Derive durations
  from the accepted configuration using bounded canonical expansion; unresolved
  durations leave totals unknown. Explain this scope in both HUD tooltips, while
  Review supplies explicitly simulated values. Dashboard adds an Output dir row with the
  reserved E04 session directory (— before reservation); omit Reservation and Metadata rows.
  Status captions use brackets. Omit the trial-position strip; the HUD trial
  row retains the current index/count. Ready lamps are green,
  preparation/waiting amber, explicit faults red and unavailable states neutral;
  preserve the exact status in the label/tooltip. No synthetic plots or telemetry.
  Switch live using the existing widgets, preserving drafts, command gates,
  actual status/log content and responsive layout. Both modes restore the saved
  style on opening; appearance changes never enable Review simulation in runtime.
  Protocol shares card frames/titles/glow, fonts, fields, menus and focus/caret treatment.
  Its timelines use the active palette, square Retro blocks and inverse selected blocks;
  unselected epochs retain their content-color identity. Compact symbolic buttons retain
  their glyphs without brackets. Narrow group controls reserve room for both labelled
  fields by omitting the redundant Selected group caption and balancing field widths.
  Newly available screen rows receive matching advanced-card titles and glow. Preserve
  canonical source, selection/hit geometry, edit history, validation and execution locks;
  rendered stimulus previews retain their content colors.
  The shared theme owns both palettes; the experiment configuration excludes this
  cosmetic preference. Unknown saved styles fall back to Standard.
  Owned warning, confirmation and tool windows inherit the full selected theme,
  including existing windows on a live style switch and newly opened dialogs.
  Keep stimulus/image content unchanged. OS title bars and G01 native file pickers
  retain their platform appearance.
  Retro uses bundled IBM Plex Mono Regular with its OFL license, inverse-video hover/selection,
  uppercase bracketed button labels in both enabled and disabled states, a selected-navigation prompt,
  and blinking block cursors in Runtime logs. Prefix each nonempty HUD/log entry
  visually with `>` in a reserved gutter, including Dashboard and all device pages.
  Leave section separators and wrapped continuation lines unmarked; preserve stored
  text, per-entry details and copy/selection content across style changes.
  Log error entries use the palette's coral-red error color, including the Retro
  prompt; normal entries retain the current console color. Use explicit command
  success/failure when supplied, with recognizable error wording as a fallback
  for unstructured local messages. Ordinary cancellation and negated error wording
  are not errors. Preserve diagnostics, selection and scroll-follow behavior.
  Styled input fields use one native block
  caret at the insertion position: typed text sits directly to its left, without a
  floating gap or second caret. Qt owns editing, selection, scrolling and cursor blinking.
  Icon-only buttons retain a dark hover/pressed fill with an accent border so their
  fixed-color symbols remain visible.
  The empty log displays `-- NO ENTRIES --` plus its cursor without inserting log data.
  Omit the Experiment Control subtitle beneath the sidebar brand.
  Retro uses a single-line CEPHVR wordmark with a thin lower rule and no text-drawn box
  (version appears only in the sidebar footer). Review also stages
  double-line frames on every Retro card (an owner-review trial) and shape-coded status glyphs
  (ready ●, waiting ◐, fault ▲, unavailable ○) for owner review. Unselected Retro epoch
  tiles use a stable identity tint from the Retro accents (dim fill, tinted frame) in
  place of the Standard hash colors; selection remains the inverse accent fill.
  One mouse-transparent window overlay caches scanlines (about 7% alpha) and a
  vignette; the separate Previews window has its own matching cached film.
  The local Style-menu CRT toggle controls the films and heading/lamp glow;
  main page headings share the card-title glow. In Previews, Advanced previews and Show
  are standard checkboxes matching the GUI Use-column controls; Retro also
  glows stream and projector headings, shows projector titles uppercase and gives each
  projector card the Retro card's inner line and marks.
  An off-by-default Refresh band
  toggle adds a faint rolling band; it repaints continuously, so it stays opt-in.
  Retro console text sits close to its frame: the log's `>` prompt gutter is a left
  viewport margin, so top/bottom padding stays small.
  Standard has neither. Omit the extra review/phase/clock banner; phase remains in
  the HUD. Stream headings are bracketed names (`< NAME >` in Amber phosphor, which also
  shows projectors as `| NAME |` sections with dials directly under the heading);
  the HUD and log cards are titled HUD and LOG console on every page and device tab,
  without backend prefixes (Retro-family styles retain uppercase decoration). Place epoch labels in a separate
  strip, with only the right-aligned epoch readout directly above it. Source legend
  controls sit directly above the motion plots in their own section, independent of
  the timeline header; hiding a source never hides its control or the epoch timeline. The epoch readout is only `Epoch n / N` (unknown n is
  `—`); omit epoch title and elapsed/duration text below the strip. The timeline card takes only its content height; align
  stream headings and native frame tops across each row.
  Advanced dials and maps sit beside the streams below the full-width timeline, each above aligned source/direction/
  speed/rotation readouts. Dial values share one numeric row with units; zero motion
  shows zero rather than Still. Signed angular speed is positive CCW; tracking values
  are forward then animal-left. Unavailable samples retain their explicit message.
  The epoch timeline and size lanes share one console surface; the source legend
  belongs to the adjacent motion section and follows Advanced visibility. Within Previews, card titles and stream headings use
  the accent color rather than coral, unavailable-before-Setup headings stay bright,
  and muted text and plot labels use the label shade for contrast.
  Align the epoch strip to time; keep the zero size trace inside its lane.
  Tick scales use rounded multiples of five or ten, coarsened for wider ranges.
  Each source uses one distinct theme color across its legend toggle, size trace,
  dial arrow, surrounding rotation ring and value. Texture dials label Back −90° down, Right 0° right,
  Front 90° up and Left 180° left, with moving readouts in the same frame; tracking-form dials put forward up and rightward lateral motion to the right.
  These display rotations do not change stimulus or tracking values. Its modeless
  visibility/authority/pending gates remain unchanged. Device diagram geometry and
  semantic palette roles remain unchanged; diagrams use the active appearance palette.
  These preferences never enter experiment configuration.
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
- Keep a common content-measured title row.
  Device icon subtabs occupy the top of the left content column, followed by the
  per-device Configuration file card and then connection/settings cards. Subtabs expand to fill their column and align their top edge
  with the HUD card’s painted top border. The right HUD stays at the same top position across pages and
  device subtabs in the two-column layout; only Dashboard's fallback Configure | Monitor
  top tab bar and its card gap shift that page's controls and HUD together. Use the existing stacked layout on narrow
  windows; tab overflow scrolls without replacing navigation with a dropdown.
- Navigation pairs labels with theme-colored outline icons: Dashboard panels,
  Protocol timeline, Devices USB, Tracking CephVR1 six-arrow flow, Configure sliders,
  Monitor eye, Cameras camera, Microcontroller chip, existing Projector, SpikeGLX
  waveform, Rig geometry cube, Projection calibration scan corners and Projection
  synchronization nested pulse squares. Icons follow selected/inactive palette colors;
  the main sidebar reserves room for icons and complete bracketed labels.
- View > Side navigation defaults on, retaining an explicit saved local preference.
  Dashboard shows compact Configure and Monitor links below its main sidebar button
  at every window width. Devices likewise shows
  Cameras, Microcontroller, Projectors and SpikeGLX beneath its main sidebar button
  at every window width. Both groups remain expanded across main-page changes;
  choosing a child opens its owning page and selects that child. Neither page
  reserves a second navigation column. Projectors' Rig geometry,
  Projection calibration and Projection synchronization tabs remain below Displays
  in the content column, independent of the rail. Rails mirror/drive existing view
  tabs and preserve automatic session transitions and manual selection. Disabling
  Side navigation restores top tabs on both pages; control and authority gates are
  unchanged. The262px main sidebar fits complete selected device labels and markers beside their icons. Main page
  links are left-aligned; their child links are indented32px with12px text,16px
  icons and compact rows separated by6px of vertical margin. Reserve40px per child
  row and16px between sidebar entries, keeping child groups together beneath their
  parent while main sections have more breathing room. Selected sidebar child links
  use a slim left accent bar and brighter text/icons on an unfilled background;
  neither selection nor hover draws a surrounding box.
- Empty inventory tables and the Displays layout say what to do (for example, use the
  refresh button) instead of showing a blank body. A disabled Load/Save as button's
  tooltip states why: editing is locked (controller not connected, another window holds
  control, or a session is in progress), or the live diagnostic must be closed first.
- Condition suggests the last 10 distinct values (case-insensitive,
  most recent first) from the local GUI settings, recorded only when Setup is accepted
  for request, and never part of the experiment configuration. After Subject ID or
  Output directory editing finishes, an ID with earlier sessions in that directory gets a
  tooltip and one activity-log line (scan of `<root>/<date>_<experiment>/<subject>-<time>`,
  bounded and read-only, silent when unreadable). Select the latest session by date,
  then time including seconds, using experiment name only to break timestamp ties.
  If the same Subject ID already has a
  session for the same experiment today, Setup first asks once (Change Subject ID or
  Continue setup); it closes without a request if authority is lost. A reused ID never
  overwrites a session, so this is advice, not validation.
- Wheel/trackpad events never change combo, spinbox or slider input values, even
  with focus; route them to the enclosing scroll container. Explicit clicks, typing
  and keyboard edits remain available. Apply this once at application scope.
- Use one dim selection color for rows, navigation, subtabs and text selections,
  distinct from table-header fill. Retro table rows use a dark blue-teal selection
  with light text so enable checkboxes remain distinct; navigation/menu inverse
  selection is unchanged. Table cells and headers share horizontal padding;
  content-sized columns include that padding rather than ending at their text width.
  Shared Qt headers wrap to measured section widths and refit height after resize/font
  changes, preserving empty-header visibility and owner-supplied extra table height.
  Variation-table remove controls share one hover owner; defer visibility changes
  until pointer-event dispatch finishes and resolve against the current rows.
  Header sections round their outer top corners with transparent header backgrounds
  so native header fills do not protrude beyond the table outline.
- All tabular inventories and forms reuse the Cameras native Qt header, blue header
  band, padding and rounded border through one shared table helper, including device
  I/O, signal mappings, projection calibration, screen dimensions and point editors.
  Persistent controls fit their styled height plus cell insets; content-sized columns
  include control width and padding. SpikeGLX custom-input remove controls use
  centered 26-pixel icon buttons with a column sized for the button and shared padding.
  Coordinate tables retain 2:1:1 name/X/Y columns and
  centered numeric headers/values. Fit single-line rows to their content; use no
  separate coordinate-header/divider theme. Cells remain directly editable with
  hover/focus affordances and dash placeholders. Preserve descriptive names,
  keyboard editing and existing validation.
- Section-level enable controls have an extra shared 8 px of space before their
  dependent fields, in addition to normal layout spacing. Apply the margin to the
  dependent section so hidden sections leave no empty gap; preserve compact
  same-row/table checkboxes beside their associated values.
- Camera trigger source/rate/pin fields align at their bottom edge when labels wrap.
  VSync mode occupies a Display synchronization card aligned to sibling card edges;
  its field fills the shared card body within the normal padding.
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
  an expanding Runtime log at the right; placeholder pages retain this same layout.
  HUD height follows its rendered text, including wrapped lines and panel padding.
  The Runtime log fills the remaining column height. Shared fitted-text helpers,
  size policies and layout stretch implement this rule; retain readable log minimum
  height. The shared left configuration column scrolls independently when inventory
  or controls exceed available height; the right status/diagram/log column stays in
  place. Hide vertical and horizontal scrollbar tracks throughout the Qt GUI,
  retaining wheel/trackpad and keyboard scrolling. Their zero-size gutter is stable
  across tabs regardless of overflow. Protocol scrolls its authoring region while navigation and the page heading stay fixed. Other pages have no outer whole-page scroll. Narrow windows stack the columns.
  Activity logs use readable action names and concise admission/outcome lines;
  admission never claims execution or completion. Keep exact command identities and
  diagnostic messages in accessible per-entry details, bounded with their retained
  entries. Wrap at word boundaries without forced splitting of long tokens;
  over-width indivisible tokens remain horizontally scrollable. Preserve the visible
  message and wrapped-line offset when appending or evicting old entries.
- Implement the native frontend with PyQt6, matching the reference. Initial local
  design review uses explicitly labeled presentation fixtures, no device/runtime
  calls and no admitted experiment commands. Managed bootstrap, E03 transport/leases
  and E15 full application/rig acceptance remain separate unfinished work.

<a id="e03"></a>
### E03 — GUI disconnection and control lease

**Status:** Accepted · **Revision:** 35

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
  important reconnect warnings, try once to acquire an unheld lease automatically through
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
  Controller warning delivery may retain one exact preceding trial or just-retired
  session scope; session warnings must match its frozen configuration revision.
  Clear that allowance on a configuration revision change or another session.
  Preserve producer generation and occurrence validation; a late optional warning
  cannot reactivate work or prove resource/output closure.
- **Reconnect warnings:** built from the Snapshot's retained errors, recoveries and
  runtime incidents for the current Setup/session, bounded by
  `[control].max_retained_incidents` (default 256; oldest resolved entries evicted
  first, active incidents never). The Snapshot reports the retained coverage start and
  truncation; do not imply a complete history of a longer absence. There is no
  separate history RPC. Exclude scientific data, raw RPCs and unchanged heartbeats.
  Present groups with distinct category headings in a compact vertically scrolling
  body; treat diagnostic content as literal text. Show retained issues and pending choices before routine
  successful-operation counts. Keep all actionable operation outcomes visible;
  copied technical details retain exact identities/messages and explicitly mark
  bounded history omissions. Use a themed review dialog without a warning icon or
  technical-detail pane; its only actions are Copy details and Continue.
  Copy details copies the current retained diagnostics, including all errors,
  without acknowledging or changing controller state. Do not imply every retained event occurred during the
  latest disconnection or that retained history is complete.
- **Warning modal:** after synchronization following an unexpected disconnect or
  crash or GUI launch, show a modal review only for retained errors/incidents,
  pending choices, failed or unconfirmed terminal operations, active/failed/unknown
  recoveries, or important warnings. Exclude explicitly completed recoveries with
  completion evidence and no terminal failure, and exact nonfatal configuration
  notices tied to current completed/valid validation. Unclassified warnings remain
  important; never classify by message keywords. Successful operation history,
  ordinary in-flight operations, history truncation and connection loss alone do
  not require this review. Full retained history remains manually available and
  copying it does not require or grant control. Keep state-changing GUI controls disabled until the
  operator acknowledges it. Acknowledgement changes only GUI state: it does not pause
  execution, clear errors, recover or claim a lease, or alter controller state.
- **Reconnect schedule:** after unexpected controller-connection loss, the GUI retries
  immediately, then after 1, 2, and 5 seconds, and every 5 seconds thereafter, until
  connected or the GUI is intentionally closed. A successful connection resets the
  schedule. Retry duration does not extend control ownership. E08 automatic
  application shutdown overrides this loop after confirmed controller/supervisor loss;
  display the shutdown reason while alive without delaying process exit.
