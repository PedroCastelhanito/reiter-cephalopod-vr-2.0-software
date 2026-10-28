# Linear PNG metadata in selected stimuli folders — 2026-10-28

Owner requested Desktop/Alsu/media and then explicitly narrowed scope to images
inside /stimuli only. Selected600 PNGs under each of
Cuttlebase_3840x2000_1to1_ALDER/stimuli and Primate_3840x2000_1to1_POPLAR/stimuli.
Excluded80 exemplar PNGs,20 root-level duplicate PNGs and6 source/document files.
No protocol file or already-imported media outside these folders is a target.

Both included generation scripts have SHA256
9ae5458130158d1c8584b75ca23313b6d54ecb1aac0dafeb249668ad9345ec34 and use the same
direct normalized grayscale export. All600 ALDER PNGs also match the previously
retained original/source hashes. POPLAR has its canonical source generator and
complete600-file metamer/noise naming inventory; no prior independent all-POPLAR
hash collection was available. The original generation folders have been moved
under media: an initial preflight expecting their old sibling paths failed before
any edit. Revised preflight uses retained ALDER hashes and current generator/
filename provenance rather than claiming nonexistent independent copies.

Method: tag_linear.py --plan validates signatures/chunk lengths/CRCs, dimensions
3840×2000/8-bit RGB, exact target paths and absence of conflicting colour chunks
for all1200. A synthetic image checks decoded-pixel equality and corrupt/truncated
input rejection. Plan.json retains before/after whole-file hashes, IDAT hashes,
exact inserted metadata bytes and hashes of106 excluded files. It is a reversible
metadata-only manifest, not a full duplicate12GB image backup: removing the newly
inserted chunks must reproduce every original byte/SHA256 exactly.

Metadata follows[W3C PNG colour chunks](https://www.w3.org/TR/png/#11gAMA): gAMA
100000 (gamma1.0) and cHRM Rec709/sRGB-primary chromaticities with D65 white point,
inserted after IHDR and before image data. No sRGB nonlinear-transfer declaration
is added. The compressed IDAT chunks and all pre-existing chunks are copied exactly,
without decode/re-encode or sample-value conversion. Scope is the owner's accepted
linear-intensity interpretation, not a physical luminance calibration.

Approved external write: repository Python3.11 tag_linear.py --apply. Each file
checks concurrent edits, writes a same-directory temporary file, fsyncs/closes and
atomically replaces its exact target; logs applied.jsonl. No recursive delete/move,
protocol changes, source-generator execution, runtime source change or dependency.
Partial interruption is resumable against exact before/after hashes.

Verification command: tag_linear.py --verify. Every target must match its planned
after hash, pass PNG CRCs and loader _png_transfer='linear', retain exact IDAT hash
and reconstruct original full-file hash. All106 excluded files must retain their
hashes. Four representative files (first/last of each family) additionally compare
decoded arrays and pass actual protected-source/float-RGBA validation with
color_override=None under current2GiB CPU budget. Per-file pixel equality is also
guaranteed by identical encoded IDAT/IHDR; decoded-array sampling is not described
as1200 separate full conversions. No runtime Setup/GPU/optical acceptance.

Final verification passed:1,200 tagged PNGs,106 unchanged non-target files,
all1,200 IDAT hashes unchanged and original whole-file bytes recoverable. Four
representative before/after decoded-array comparisons and full native protected
source validations pass without colour overrides. Result: verification.json.
No Setup/GPU/optical acceptance inferred. Existing imports elsewhere are unchanged;
new imports/copies from these tagged stimuli files carry the metadata.
