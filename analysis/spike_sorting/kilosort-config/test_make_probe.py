import make_probe


def test_reuses_probe_with_matching_imro(tmp_path, monkeypatch):
    monkeypatch.setattr(make_probe, "PROBES", tmp_path)
    (tmp_path / "other.prb").write_text("# ~imroTbl=(2003,384)(0 1 0 1)\n")
    (tmp_path / "mine.prb").write_text("# ~imroTbl=(2003,384)(0 1 0 0)\n")
    meta = tmp_path / "run.ap.meta"
    meta.write_text("imSampRate=30000\n~imroTbl=(2003,384)(0 1 0 0)\n")

    assert make_probe.ensure_probe(meta) == (tmp_path / "mine.prb", False)
