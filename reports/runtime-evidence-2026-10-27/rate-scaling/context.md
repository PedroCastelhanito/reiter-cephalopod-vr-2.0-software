# Pixel scaling width check — 2026-10-27

Command: `.venv/Scripts/python.exe reports/runtime-evidence-2026-10-27/rate-scaling/benchmark.py`.
The raw [result](result.json) records UTC time, source revision, source hashes,
interpreter/NumPy/platform identity, all samples and equality digests. The
benchmark exhaustively compared every value in each accepted source container
for 8/10/12/16-bit source depths and 8/10/16-bit target depths: 12 byte-equal
cases.

The largest rounded numerator is `65535 * 65535 + 32767 = 4294868992`, below
the uint32 maximum `4294967295`; division and the final MSB shift also fit.
This bound depends on the current 16-bit source/target ceiling. Revisit it if
formats wider than 16 bits are supported.

| Synthetic image | Conversion | uint64 median | uint32 median | Reduction | Scratch bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| 1920x1080 gray | 16 to 8 | 2.141 ms | 1.764 ms | 17.6% | 16,588,800 to 8,294,400 |
| 1920x1080 gray | 12 to 10 | 2.510 ms | 2.142 ms | 14.6% | 16,588,800 to 8,294,400 |
| 1280x1024 RGB | 12 to 16 | 4.674 ms | 3.369 ms | 27.9% | 31,457,280 to 15,728,640 |
| 640x480 gray | 8 to 16 | 0.310 ms | 0.257 ms | 17.1% | 2,457,600 to 1,228,800 |

Four warmups, then ten alternating rounds of sixteen calls per dtype. These are
synthetic CPU measurements on this machine, not camera throughput or rig evidence.
The run covers scaler equality and timing only; it does not exercise the SDK,
camera capture, GUI, GPU, recording/encoding or full workload.
