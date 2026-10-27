# Pixel scaling alternative — 2026-10-26

Source revision: `a28ed14492a5fa9ef1c0c75e6c2c2687846aa19d`. Source hashes,
interpreter/NumPy/platform identity, individual timings and equality digests are in
[result.json](result.json). This is an isolated CPU benchmark, not rig evidence.

Command: `.venv/Scripts/python.exe reports/runtime-evidence-2026-10-26/hierarchy-audit/pixel-benchmark/benchmark.py`.
The reproducible [benchmark](benchmark.py) calls the existing production scaler
with the reference uint64 and proposed uint32 scratch buffers. Production code
is unchanged. The run passes all assertions and exits successfully.

## Code to review / implement

Consider uint32 instead of uint64 for `PixelPreparer._scale_scratch` in
`src/cephvr/shared/pixels/preparer.py`. This halves that fixed scratch allocation.
Also update the uint64-specific explanatory comment in `scaling.py` if accepted.
No algorithm, coefficient, rounding, SDK provider, representation, threading,
source identity, output ownership, deadline or policy changes are proposed.
This follows A01/A10/T01 and ARCH-002; the pixel-processing contract requires
wide arithmetic without overflow, rather than a particular scratch dtype.

Current validation accepts source depths 8/10/12/16 in 8/16-bit containers,
preview output depths 8/16, and explicit recording output depths 8/10. The largest
multiply-plus-rounding numerator is `65535 * 65535 + 32767 = 4294868992`, below
uint32's `4294967295`. Subsequent division and MSB shift also fit uint32; the
existing final output cast is unchanged. This proof is limited to those formats;
new greater-than-16-bit formats require another review.

The benchmark compares every possible source-container value for each of the
four accepted source depths against each output depth 8/10/16: 12 exhaustive
byte-equality cases. This includes low storage bits outside the usual MSB code
points, retaining current interpolation/rounding behavior. Four synthetic image
cases also compare all output bytes after timing. No mismatch occurs.

| Synthetic image | Conversion | uint64 median | uint32 median | Time reduction | Scratch bytes |
| --- | --- | --- | --- | --- | --- |
| 1920x1080 gray | 16 to 8 | 2.429 ms | 1.891 ms | 22.1% | 16588800 to 8294400 |
| 1920x1080 gray | 12 to 10 | 2.846 ms | 2.254 ms | 20.8% | 16588800 to 8294400 |
| 1280x1024 RGB | 12 to 16 | 4.817 ms | 3.659 ms | 24.0% | 31457280 to 15728640 |
| 640x480 gray | 8 to 16 | 0.312 ms | 0.268 ms | 14.1% | 2457600 to 1228800 |

Each dtype has four warm-up calls, then ten rounds of sixteen calls; reference
and alternative order alternate by round. These are samples on the current
machine with unmonitored concurrent activity, not camera FPS or performance
guarantees. Allocation counts other than scratch are unchanged. The existing
8-to-8 identity preview path bypasses scaling and would gain no scaling-time
benefit.

If implemented later, extend existing
`tests/acquisition/test_manual_preview.py::test_preview_pixel_copy_matches_full_range_conversion`
with boundary values/depths and preserve the explicit no-rescaling identity
check. Recheck the recording converter path in its owning recording tests;
retain the exhaustive integer equality check. Run affected acquisition/shared
tests and static checks before acceptance. The benchmark itself did not run
SDK conversion, camera capture, GUI, GPU, recording/encoding, load tests or
scientific/rig acceptance. Ruff reports no Python files here because the root
configuration intentionally excludes reports; no Ruff coverage is claimed for
this evidence script.
