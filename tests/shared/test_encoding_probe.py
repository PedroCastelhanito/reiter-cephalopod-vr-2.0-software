"""Offline rig-tool checks; no devices, FFmpeg process or runtime mutation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.encoding_probe import command, frame_log


def test_synthetic_command_keeps_exact_geometry_gpu_and_no_realtime_throttle(tmp_path):
    argv = command(
        {"width": 1280, "height": 1000, "fps": 60, "input_pixel_format": "rgba"},
        ["-c:v", "h264_nvenc", "-cq", "23"],
        1,
        3600,
        tmp_path / "probe.mp4",
    )
    assert "testsrc2=size=1280x1000:rate=60,format=rgba" in argv
    assert argv[argv.index("-gpu") + 1] == "1"
    assert argv[argv.index("-frames:v") + 1] == "3600"
    assert "-re" not in argv and "-y" not in argv
    with pytest.raises(ValueError, match="8-bit"):
        command(
            {
                "width": 1280,
                "height": 1000,
                "fps": 60,
                "input_pixel_format": "gray10le",
            },
            [],
            1,
            3600,
            tmp_path / "bad.mp4",
        )


def test_collect_distinguishes_camera_loss_padding_and_missing_completion(
    tmp_path: Path,
):
    path = tmp_path / "camera_frames.jsonl"
    rows = [
        {
            "type": "frame",
            "host_receipt_ns": 10,
            "video_disposition": "capacity_drop",
            "dropped": True,
            "invalid_code": None,
        },
        {
            "type": "frame",
            "host_receipt_ns": 20,
            "video_disposition": "invalid_image",
            "dropped": False,
            "invalid_code": "incomplete",
        },
        {"type": "video_frame", "disposition": "leading_duplicate"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    result = frame_log(path)
    assert result["source_dispositions"] == {"capacity_drop": 1, "invalid_image": 1}
    assert result["video_dispositions"] == {"leading_duplicate": 1}
    assert result["invalid_images"] == result["source_dropped_flags"] == 1
    assert not result["completion_present"]
    with path.open("a") as stream:
        stream.write('{"truncated":')
    with pytest.raises(ValueError):
        frame_log(path)


def test_stimulus_final_counters_not_double_counted_with_updates(tmp_path: Path):
    path = tmp_path / "stimulus_frames.jsonl"
    rows = [
        {
            "kind": "render_group",
            "state": {"evaluation_host_ns": 10},
            "captures": [{"disposition": "admitted"}],
        },
        {"kind": "group_update", "captures": [{"disposition": "input_submitted"}]},
        {
            "kind": "encoder_outcome",
            "capacity_drop_count": 2,
            "duplicate_frame_count": 3,
        },
        {"kind": "completion", "unresolved_attempt_count": 0},
    ]
    path.write_text("\n".join(json.dumps({"payload": r}) for r in rows) + "\n")
    result = frame_log(path)
    assert result["render_groups"] == 1
    assert result["initial_capture_dispositions"] == {"admitted": 1}
    assert result["final_records"]["encoder_outcome"]["capacity_drop_count"] == 2
    assert result["completion_present"]


@pytest.mark.parametrize("failure", [None, "timeout", "launch", "decode", "probe"])
def test_concurrent_probe_retains_results_and_reports_failed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
):
    import argparse
    import subprocess
    import threading
    from types import SimpleNamespace

    from tools import encoding_probe

    profiles = tmp_path / "profiles.json"
    profiles.write_text(
        json.dumps(
            {
                name: {"width": 8, "height": 8, "fps": 2, "input_pixel_format": "gray"}
                for name in ("tracking", "eye_tracking")
            }
        )
    )
    barrier = threading.Barrier(2)

    def run(argv, **_kwargs):
        barrier.wait(timeout=2)
        if Path(argv[-1]).stem == "eye_tracking":
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, 1)
            if failure == "launch":
                raise OSError("launch failure")
        Path(argv[-1]).write_bytes(b"test-only")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(encoding_probe.subprocess, "run", run)
    monkeypatch.setattr(
        encoding_probe.subprocess, "check_output", lambda *_a, **_k: "test version"
    )

    def probe(path, _timeout):
        if path.stem == "eye_tracking" and failure == "probe":
            raise ValueError("invalid probe JSON")
        return {
            "decode_exit": 0,
            "decode_error": "corrupt frame"
            if path.stem == "eye_tracking" and failure == "decode"
            else "",
            "ffprobe_exit": 0,
            "ffprobe": {"streams": [{"codec_type": "video", "nb_read_frames": "2"}]},
        }

    monkeypatch.setattr(encoding_probe, "probe_video", probe)
    output = tmp_path / "run"
    ns = argparse.Namespace(
        profiles=profiles,
        sources="tracking,eye_tracking",
        cq=16,
        gpu=1,
        seconds=1,
        output=output,
        timeout=1,
    )
    if failure:
        with pytest.raises(SystemExit):
            encoding_probe.benchmark(ns)
    else:
        encoding_probe.benchmark(ns)
    results = json.loads((output / "summary.json").read_text())
    assert len(results) == 2
    assert results[0]["frame_count_matches"]
    assert (results[1]["exit_code"] is None) == (failure in {"timeout", "launch"})
    if failure:
        assert results[1]["requested_frames_per_elapsed_s"] is None
    for name in ("tracking", "eye_tracking"):
        argv = json.loads((output / f"{name}-command.json").read_text())
        assert argv[argv.index("-cq") + 1] == "16"


@pytest.mark.parametrize(
    "bad_row",
    [
        "null",
        '{"payload": []}',
        '{"type": "render_group", "state": null}',
        '{"truncated":',
    ],
)
def test_collection_retains_other_evidence_when_one_log_is_invalid(tmp_path, bad_row):
    import argparse

    from tools.encoding_probe import collect

    (tmp_path / "bad_frames.jsonl").write_text(bad_row + "\n")
    (tmp_path / "good_frames.jsonl").write_text('{"type": "completion"}\n')
    output = tmp_path / "summary.json"
    with pytest.raises(SystemExit):
        collect(
            argparse.Namespace(
                directory=tmp_path,
                output=output,
                diagnostics=tmp_path / "missing.log",
                timeout=1,
            )
        )
    result = json.loads(output.read_text())
    assert result["frame_logs"]["good_frames.jsonl"]["completion_present"]
    assert len(result["errors"]) == 2


def test_empty_collection_is_not_success(tmp_path):
    import argparse

    from tools.encoding_probe import collect

    output = tmp_path / "summary.json"
    with pytest.raises(SystemExit):
        collect(
            argparse.Namespace(
                directory=tmp_path, output=output, diagnostics=None, timeout=1
            )
        )
    assert "no video" in json.loads(output.read_text())["errors"][0]


@pytest.mark.parametrize("failure", ["timeout", "decode"])
def test_collection_records_video_validation_failure(tmp_path, monkeypatch, failure):
    import argparse
    import subprocess

    from tools import encoding_probe

    (tmp_path / "video.mp4").write_bytes(b"test-only")

    def probe(*_args):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("ffprobe", 1)
        return {"ffprobe_exit": 0, "decode_exit": 0, "decode_error": "corrupt frame"}

    monkeypatch.setattr(encoding_probe, "probe_video", probe)
    output = tmp_path / "summary.json"
    with pytest.raises(SystemExit):
        encoding_probe.collect(
            argparse.Namespace(
                directory=tmp_path, output=output, diagnostics=None, timeout=1
            )
        )
    assert json.loads(output.read_text())["errors"]
