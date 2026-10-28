# Newly imported full ALDER protocol — 2026-10-28

Base e4dd8f2694aa075380fe6711a884fe5894763c6f plus concurrent dirty tree. Owner
Setup57873edf failure names variation_249042d669a84f6de6f61e76,
import-nt_fq95n/0001_1_metamer1.png, missing colour transfer/primaries,0/600.
Saved texture-presentation-1hr_protocol.json now contains600 untagged assets,
replacing the previously repaired ten-asset revision. This is a new import/file
revision, not evidence that previously saved overrides were rejected or discarded
by the loader. No import-mechanism defect is established by this report.

apply_linear_600.py verifies every imported file against its original in
Desktop/Alsu/Cuttlebase_3840x2000_1to1_ALDER/stimuli by SHA256. All600 match;
generator save_img uses identical direct normalized grayscale export for metamers
and noise. Reuse owner-selected interpretation under V04rev43/GOV-001, limited
to these verified outputs. No untagged-media default or unrelated encoding inferred.

Prepared proposal validates through GUI envelope loader; original backed up as
before.protocol.json. Approved external write atomically applies linear.protocol.json
with concurrent-edit guard. Only600 per-asset overrides differ (semantic equality
verified after stripping them), with linear/full/RGB/Rec709 D65/no chroma and
explicit owner/provenance reason. Source PNGs unchanged. hashes in provenance.json.

Validation command: repository Python3.11 validate_all.py, which uses actual native
ProtectedWindowsSource, hashlib, BoundedBudget and validate_image_source sequentially
with CPU2GiB/GPU4GiB and a240s diagnostic deadline. Each source is verified against
provenance before decode/conversion/output validation; temporary reservations must
return tozero and handles close in finally. Per-image evidence in
validation-events.jsonl; final summary validation-results.json and stdout
validation-output.txt. These are source-preparation checks, not GPU/runtime Setup,
optical luminance, all-image residency or throughput acceptance.

The two accepted MCU defaults were separately changed to500ms ACK/1050ms Stopped
under A11rev55/E05rev101. Owning loaders confirm exact units/budget compatibility;
59 controller/acquisition configuration tests pass (5.93s), scoped test Ruff/format
and whitespace pass. Command: python -m pytest tests/controller/test_configuration.py
tests/acquisition/test_configuration.py -q -m "not windows and not rig" --timeout=30
--basetemp=.tmp-mcu-500ms-config, approved native execution for asyncio loopback.
No fixed policy/version changes, firmware operation, live restart or hot-swap.

Remaining: running GUI draft/controller must load/apply the revised600-image file;
full restart is needed for retained MCU timing. No new live Setup/Start was issued
for this request; earlier ten-image native results remain separately scoped.

Final source validation:600/600 pass,130.6s wall time; maximum CPU reservation
1,499,265,784bytes under2,147,483,648. Each file completes linear float-RGBA
conversion/output validation, with no retained validation reservation and its
protected handle closed. Final source/protocol hashes and exact per-image results
are in validation-results.json. Full-set native Setup, GPU residency/throughput,
optical brightness and500ms MCU timing acceptance remain unverified.
