# Image CPU capacity — 2026-10-28

Base e4dd8f2694aa075380fe6711a884fe5894763c6f plus dirty tree. Inputs: owner
Setup2aeec5d1 report and Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json.
Initial protocol/source hashes are in [results-before-linear.json](results-before-linear.json).

`python check.py` using repository Python3.11 calls actual protected Windows source
reads, source hashing, BoundedBudget and validate_image_source. No graphics, camera,
serial, live controller or external writes. Source dimensions are3840×2000 for all
ten PNGs. Reproduced old1GiB rejection at1,494,407,186 bytes for source1; the
reported integrated1,494,464,310 includes additional owning-session allocations.
2GiB admission accepts all ten, largest source reservation1,494,414,146 bytes.
Decoder then rejects all ten because explicit colour transfer/primaries are absent.
The initial run stopped at the first such error. Final [output](validation.txt)
and JSON explicitly retain blocked status; no conversion/upload or full validation
pass claimed. Reservation counts return tozero; handles closed in finally.

Read-only GlobalMemoryStatusEx at inspection: total66,094,223,360 bytes and
available42,027,282,432 bytes; this is current RAM evidence, not a combined-load
capacity guarantee. No inferred machine specifications from historical benchmarks.

Final loader asserts CPU2,147,483,648/GPU4,294,967,296 bytes.
`python -m pytest tests/visual_stimulus/test_configuration.py -q --basetemp=.tmp-image-cpu-config`:
15 passed,5 subtests. TOML parses through owning loader; V04rev41/register agree;
`git diff --check` passes. Fixed policy/version unchanged (operator setting only).

Open: owner must identify source encoding before an explicit override is authored.
Do not choose sRGB or linear from appearance, filename or missing PNG metadata.
No external protocol/image edits, native Setup, renderer allocation or playback.

## Source provenance follow-up

Owner answered that the encoding is unknown. Read the ALDER source note and
`Desktop/Alsu/Cuttlebase_3840x2000_1to1_ALDER/generation_code/ps_3840x2000_task.m`.
SHA2569ae5458130158d1c8584b75ca23313b6d54ecb1aac0dafeb249668ad9345ec34.
All ten imported files exactly match `stimuli/` originals by streamed SHA256;
[comparison](provenance.json). Lines51–55 normalize synthesized grayscale samples
to numerical mean0.5/std0.2, clip0..1, round to8-bit and replicate RGB before
imwrite; no explicit sRGB/gamma transfer is applied in save_img. Exemplars are
read with im2double/imread, converted with rgb2gray if needed. The note describes
normalization and measured sample statistics, not a calibrated luminance transfer.

This supports recommending linear interpretation to preserve authored numerical
intensities in the renderer; it does not prove intended physical luminance or an
accepted source declaration by itself. The owner subsequently selected linear.
No generation code executed or metadata inferred from image appearance.

## Accepted linear interpretation and applied validation

V04rev42/register record owner-selected linear interpretation. apply_linear.py
validates a proposal, preserves original bytes, checks concurrent edits and applies
atomically with approved external-file access. Fresh original protocol SHA256
ffe23f6fab971de90b31d40186b604a63b3612d427b839d93801cdf13a35ab11;
applied6932c6b0cd92001282b8593872a4f8d1f7f6d54ba568f50d4a91ac9b3387649a.
Use this inspected revision, not an older input from another investigation.

Only ten colour declarations differ: linear/full/Rec709 D65/RGB/no chroma,
reason identifies owner selection and normalized MATLAB export. Before/after
semantic equality verified after stripping those overrides; GUI envelope validates.
Original backup: texture-presentation-before-linear.protocol.json. Applied proposal:
texture-presentation-linear.protocol.json. PNG files unchanged.

Reran python check.py against the updated external protocol. All ten pass full
validation including linear float-RGBA conversion/output validation; largest source
reservation1,494,414,146bytes, all reservations/handles released. Final output:
[results.json](results.json), [validation.txt](validation.txt). Earlier failures:
results-before-linear.json and validation-before-linear.txt. Initial descriptions
above apply to those historical results. No runtime source change, dependencies or
new default; reused explicit overrides/validation under ARCH-002. Whitespace passes.
GUI draft/controller configuration untouched: reload saved protocol and Apply before
fresh Setup. No live Setup, GPU upload, optical or full-load acceptance claimed.
