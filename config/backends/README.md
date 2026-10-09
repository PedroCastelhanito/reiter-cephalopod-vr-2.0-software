# Backend defaults

These operator files contain only settings you may change, with their defaults.
Fixed architecture policy lives in the matching versioned
[`contracts/policy/<backend>_policy.toml`](../../contracts/policy/) file, which is not
edited here. [E14](../../docs/architecture/system-contracts.md#e14) defines the split,
the file-to-decision map and maintenance rules. Owning runtime loaders validate
operator values and fixed policy bindings; file presence does not enable a backend.

Files: `experiment_config.toml`, `supervisor_config.toml`, `acquisition_config.toml`,
`visual_stimulus_config.toml`, `gui_config.toml`, `tracking_config.toml`,
`synchronization_config.toml`, and the controller-owned `microcontroller_config.toml`.
Each starts with `format_version` and a `policy_version`
that must equal its policy file's.

## Editing

- Change a value only to another accepted value; a field is not permission to select
  an unsupported policy. A new key goes here only if an operator may change it;
  otherwise it belongs in the policy file (E14).

- TOML uses `[sections]`, `name = value` entries, `# comments`, and `true`/`false`.
  Names ending in `_s` are seconds, `_ms` are milliseconds, and `_bytes` means bytes.
  Decimal 10 GB is
  `10_000_000_000` bytes. `format_version = 1` describes this default-file format,
  separately from the JSON logging schema version.
- Start cutoff values are positive offsets **before** the scheduled target, not
  additional delays. For example, 100 ms means the deadline is `target - 100 ms`.
  Require `start_lead_time_ms > controller_release_cutoff_before_start_ms >
  backend_release_cutoff_before_start_ms > 0`.
- Central metadata queue/deadline settings belong to experiment_config.toml;
  supervisor_config.toml keeps health, reservation/emergency and shutdown settings.
  Control reconnection has no grace timer; a fresh synchronized GUI subscription
  automatically claims an unheld lease after warning acknowledgement under E03.
  Replacing another holder requires explicit takeover. Old removed keys are rejected, not silently ignored.
- Each setting has one owner. Microcontroller COM, general I/O defaults and serial
  timing belong to `microcontroller_config.toml`; camera-specific trigger pins/rates
  remain in the camera defaults. For example, change heartbeat policy only in
  `supervisor_config.toml`. Its resolved values are shared with every process that needs
  them, including controller-loss fallback; all processes read/validate health at
  startup and changes require an application restart. No session-policy duplicate.
- E07 resolves media references against the configurable `assets.asset_root`, which
  may be on another disk. Its optional baseline belongs in `experiment_config.toml`;
  no directory default is selected. Recording-output paths remain separate.
- Control scheduling, lifecycle timeout, health and persistence-deadline values
  are config-file-only under E05/E06/E14. Edit their owning TOML before Setup
  (or application restart for startup-only health/shutdown-backstop settings);
  GUI/headless session values and trial protocols cannot override them.
- A10 transport overrides are currently file-based: use each camera's `transport`
  table in `acquisition_config.toml` before preparation. Saved/session values cannot
  override these tables. GUI exposure remains a later decision.
- For other session settings, defaults fill missing values. Explicit saved/operator settings, including
  `false`, retain their values. Existing stored stimulus seeds are also retained.
  For example, saved `save_visual_stimulus_data = false` stays false even though its default is true.
- Use values within the accepted policies: positive finite timeouts, a health
  silence limit longer than the heartbeat interval, and nonnegative gaps. The
  shipped defaults remain starting values awaiting rig validation. Shared deadline
  accounting is selected in E05/E06; backend-specific schema/binding gaps remain
  with their owning contract worklists.
- Effective settings must be resolved and validated during Setup, then locked at
  Start. Reload TOMLs at each Setup using E07's precedence rules. Startup-only
  changes, such as service ports, require an application restart. Editing a file
  cannot alter a prepared or active session; applying changes requires fresh Setup.
  V19 separately permits initial startup display preparation from adopted saved
  settings; editing values does not trigger live display reconfiguration.
- A file's presence does not activate its role. Visual Stimulus and control services remain
  required; camera and tracking activation follows the configured dependencies.
  The synchronization file records accepted E12 policies; its presence does not enable ephys recording.
- Unresolved choices are comments without assigned values. Do not use zero, empty
  strings or guessed values for timing, hardware, calibration, modes or seeds.
  E14 supplies engineering starting limits for resource queues/memory and operational
  timeouts. Validate the actual prepared workload against them; a ceiling is not a
  hardware capability or automatic preallocation. These defaults still require the
  applicable scientific and rig inputs before Ready.

## Defaults and session records

The controller-owned `config/last_configuration.json` stores one current reusable configuration,
grouped by backend with shared experiment/protocol settings. Rejected edits are not saved;
there is no rollback section. GUI initialization reads it, while controller owns atomic
saving on normal GUI/application closure under [E07](../../docs/architecture/experiment.md#e07).
This does not rewrite backend TOMLs. Restored configuration still requires normal
validation and device/asset preparation.

These files describe reusable settings; their control timing/timeout values are
the only editable source for those policies. They are not by themselves a record
of what a particular experiment actually used. [E07](../../docs/architecture/experiment.md#e07)
defines controller-owned assembly and distribution, backend validation and returned
resolved values, and blocking Setup on required default-file errors. Startup settings
needed before controller coordination may be read locally from the same owning files.
File errors for inactive, unneeded backends warn without blocking Setup; correct them
before enabling those backends.
The owning lightweight modules load and validate these pairs; device acceptance
and actual rig behavior remain separate from successful file loading.

Backend-owned lightweight Python configuration modules supply the types and pure
validators used by both controller and backend. The controller validates edits
locally without loading device runtimes; backend processes perform device, capability
and asset checks during Setup. Check module/backend compatibility before Ready.
Unavailable, incompatible or timed-out edit validation rejects the edit with a warning
and preserves current settings/revision. Rejected candidates are not stored for later
application; no automatic rollback. A stopped backend alone does not prevent pure
validation. Results bind the request, expected revision and module version; late results
cannot commit after expiry or against changed authority/state.
The shared local validation deadline remains `configuration_validation.timeout_s`.

Keep the accepted [JSON logging scheme](../../docs/architecture/supervisor.md#e04): record effective
setup settings for active backends only, at the existing session/trial boundaries.
Do not copy every TOML file into each session log or add scientific histories.
Runtime files remain JSON/JSONL; TOML only supplies human-edited defaults.

When changing repository baseline defaults, keep them consistent with the governing
policy. Encoding tuning values belong in the per-camera FFmpeg argument lists and
their comments; revise architecture only when its rules or guarantees change. Normal operator customization of an already
configurable setting follows the accepted policy and does not require a new
architecture decision for every experiment. Control timing/timeout customization
requires editing the owning TOML and rerunning Setup. Unanswered recommendations stay unset.
