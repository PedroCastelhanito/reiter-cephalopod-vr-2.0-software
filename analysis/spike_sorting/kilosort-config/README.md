# kilosort-config

Shared Kilosort4 config for SpikeGLX (Neuropixels OneBox) recordings. Run everything
from the `SpikeSorting` conda env (kilosort, CUDA torch, spikeinterface, probeinterface, phy) —
never the CephVR env.

| File | What |
|---|---|
| `probes/<name>.prb` | Probe channel map for the Kilosort GUI. One per probe model + IMRO table, reused across sessions. First line is the `~imroTbl` it was built from. |
| `make_probe.py` | Finds the matching `.prb` for a run, or creates it if missing. |
| `ks4_settings.json` | Kilosort4 settings in use (GUI now, SpikeInterface `run_sorter` kwargs later). |

## Probes

| Probe | Use for |
|---|---|
| `NP2004_bank0.prb` | NP2.0 single shank (NP2004), bank 0, sites 0–383 in order. |

Before sorting each run, find its probe file:

```bash
python make_probe.py "F:\cephvr-data\spikeglx-data\<run>_g0"
```

```
<run>_t0.imec0.ap.meta -> probes/NP2004_bank0.prb (existing)
```

It matches each `.ap.meta`'s `~imroTbl` against the first line of every `probes/*.prb`
(same model + same site selection = same channel map). No match → creates
`probes/<model>_<imro hash>.prb`; rename it to something readable (e.g.
`NP2004_bank1.prb`) and add it to the table above, or pass the name up front:
`python make_probe.py <run or .ap.meta> NP2004_bank1`.

Never pick a probe file by eye: wrong channel map = silently bad sort.

## Kilosort GUI

```bash
conda activate SpikeSorting
python -m kilosort
```

- Binary file: `<run>_imec0\<run>_t0.imec0.ap.bin`
- Probe: `probes/<name>.prb`
- `dtype` int16, `n_chan_bin` 385 (384 AP + sync; probe map skips sync)
- `fs`: the run's `imSampRate` from `.ap.meta` (e.g. 30000.303361344537)
- Rest from `ks4_settings.json`; update that file when GUI settings change.
