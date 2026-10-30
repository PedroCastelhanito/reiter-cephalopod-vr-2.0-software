"""Find or build the Kilosort probe file (.prb) for SpikeGLX recordings.

Usage (SpikeSorting env):
    python make_probe.py <run folder or .ap.meta> [name]

For each .ap.meta: reuses the probes/*.prb whose first line holds the same
~imroTbl (same probe model + site selection = same channel map), otherwise
creates probes/<name>.prb (default name: <model>_<imro hash>).
"""
import hashlib
import sys
from pathlib import Path

PROBES = Path(__file__).parent / "probes"


def imro_line(meta):
    return next(l for l in Path(meta).read_text().splitlines() if l.startswith("~imroTbl="))


def ensure_probe(meta, name=None):
    """Return (prb path, created?) for this meta's probe configuration."""
    imro = imro_line(meta)
    for prb in sorted(PROBES.glob("*.prb")):
        with prb.open() as f:
            if f.readline().rstrip("\n") == f"# {imro}":
                return prb, False

    import probeinterface as pi

    probe = pi.read_spikeglx(meta)
    name = name or f"{probe.model_name}_{hashlib.sha1(imro.encode()).hexdigest()[:8]}"
    out = PROBES / f"{name}.prb"
    if out.exists():
        raise SystemExit(f"{out.name} already exists for a different ~imroTbl; pick another name")
    pg = pi.ProbeGroup()
    pg.add_probe(probe)
    PROBES.mkdir(exist_ok=True)
    pi.write_prb(out, pg)
    out.write_text(f"# {imro}\n" + out.read_text())
    return out, True


if __name__ == "__main__":
    target = Path(sys.argv[1])
    name = sys.argv[2] if len(sys.argv) > 2 else None
    metas = [target] if target.is_file() else sorted(target.rglob("*.ap.meta"))
    if not metas:
        raise SystemExit(f"no .ap.meta under {target}")
    for meta in metas:
        prb, created = ensure_probe(meta, name)
        print(f"{meta.name} -> probes/{prb.name} ({'created' if created else 'existing'})")
