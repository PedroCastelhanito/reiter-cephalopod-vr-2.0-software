# Owner-selected default linear interpretation — 2026-10-28

Base e4dd8f2694aa075380fe6711a884fe5894763c6f plus existing concurrent dirty tree.
Owner requested: assume images always linear. Scope implemented: missing PNG/TIFF
colour declarations default to linear; explicit overrides/supported PNG metadata
still win. No guessed handling for unsupported declared metadata. V04rev44,
E14rev217, Visual Stimulus fixed policy/config25 and strict loader digest agree.
Policy SHA256d2420960f28a8935db32cd7ca8650dadb20431681d1737f24e99bde9ac391fa8.

Executed repository Python3.11:

- `python -m pytest tests/visual_stimulus/test_resources.py tests/visual_stimulus/test_configuration.py -q -m "not windows and not rig" --timeout=30 --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/01a1804f-9d68-7a41-90ee-46fe910ee280/untagged-linear-tests`:
  154 passed,5 subtests in2.48s. First repository-local basetemp attempt had151 passes/
  three errors because demo generator forbids output inside repo; corrected location
  fixes fixture setup. Assertions unchanged to bypass no restrictions.
- After adding chromaticity-only metadata rejection coverage:
  `python -m pytest tests/visual_stimulus/test_resources.py -q -k png_declared_transfer_still_precedes_linear_default --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/01a1804f-9d68-7a41-90ee-46fe910ee280/untagged-linear-metadata`:
  four passed,136 deselected in0.53s. Initial patch did not match formatted context;
  reread and applied correctly. No source changes after broad pass.
- `python -m pytest tests/controller/test_configuration.py -q -m "not windows and not rig" --timeout=30 --basetemp=.tmp-linear-controller-policy`:
  24 passed in0.80s, approved native execution supplies Windows asyncio loopback;
  no hardware operations. Owning policy loader confirms version25 binding and
  retained500ms serial ACK configuration.
- Scoped Ruff check/format on resources/media.py, configuration.py and owning
  test_resources.py pass; Win32 mypy on both source files passes. Backend boundaries
  checks792 modules/zero violations; decoder remains a focused owner.
  Whitespace passes. Existing size advisories concern other unchanged responsibilities.

Read-only actual metamer check: parse first asset from Desktop/Alsu/protocols/
texture-presentation-1hr_protocol.json, read its imported file bytes and decode once
with an in-memory color_override=None copy and once with the saved linear override.
Both transfers linear and float-RGBA SHA256 values equal. No external file changed.
Fixture checks also verify8/16-bit source pixels and normalized linear values.

No native Setup, GPU workload, app restart or optical/calibration acceptance. No
need to rewrite existing linear overrides or tagged source files for this default.
