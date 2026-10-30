"""AN01 session compiler: synthetic E04 session with known pulse/host relationships."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from cephvr.analysis.session_compiler import Settings, compile_session  # noqa: E402
from cephvr.analysis.session_compiler.jsonl import JsonlFile  # noqa: E402

RATE = 10_000.0  # OneBox samples/s
IMEC_RATE = 5_000.0
H0 = 1_269_045_667_008_400  # trial T in host ns (real-scale int64)
OBX_AT_T = 2.0  # OneBox seconds at host T
TRIAL_S = 10.0
CAMERA_LATENCY_S = 0.020
DISPLAY_LATENCY_S = 0.030
MISSED_PULSE = 150  # a trigger the camera never delivered
IMEC_SLOPE, IMEC_OFFSET = 1 + 2e-5, 0.003


def host_to_obx(host_ns: float) -> float:
    return (host_ns - H0) / 1e9 + OBX_AT_T


def obx_to_host(obx_s: float) -> int:
    return int(round(H0 + (obx_s - OBX_AT_T) * 1e9))


def _lines(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _square(n: int, starts: np.ndarray, width: int) -> np.ndarray:
    state = np.zeros(n, bool)
    for s in starts:
        state[s : s + width] = True
    return state


def make_session(root: Path, *, paired: bool = True) -> Path:
    session = root / "SP0001-120000"
    protocol = session / "protocol-data"
    protocol.mkdir(parents=True)
    prefix = "0001_120002"
    pulses_obx = np.arange(0.5, 19.5, 1 / 29.978)  # rig MCU rate
    t_stop = H0 + int(TRIAL_S * 1e9)
    on, off = (
        (H0 + 5_000_000, H0 + 15_000_000),
        (t_stop + 5_000_000, t_stop + 15_000_000),
    )

    # Camera: exposure on each pulse except one missed trigger; admitted by host receipt.
    frames, video = [], []
    for k, t in enumerate(pulses_obx):
        receipt = obx_to_host(t) + int(CAMERA_LATENCY_S * 1e9)
        if k == MISSED_PULSE or not H0 <= receipt < t_stop:
            continue
        frame_id = len(frames)
        frames.append(
            {
                "type": "frame",
                "frame_id": frame_id,
                "host_receipt_ns": receipt,
                "dropped": False,
                "video_frame": frame_id,
                "video_disposition": "real",
                "camera_frame_counter": 1000 + frame_id,
                # Alternating 60 us quantization: the median interval sits on one mode.
                "camera_timestamp_ns": int(7e12 + t * 1e9 * (1 + 5e-5))
                + (k % 2) * 60_000,
                "invalid_code": None,
                "_pulse": k,
            }
        )
        video.append(
            {
                "type": "video_frame",
                "encoded_frame_index": frame_id,
                "source_frame_id": frame_id,
                "source_host_receipt_ns": receipt,
                "disposition": "real",
            }
        )
    expected_pulses = [f.pop("_pulse") for f in frames]
    header = {
        "type": "header",
        "schema_version": 6,
        "identity": {
            "trial_number": 1,
            "camera_role": "behavioral",
            "capture_generation": "gen-1",
        },
        "clocks": {
            "host_clock": "cephvr.host.perf_counter_ns.v1",
            "trial_start_monotonic_ns": H0,
        },
        "video": {"enabled": True, "nominal_frame_rate_hz": 30.0},
    }
    completion = {
        "type": "completion",
        "outcome": "completed",
        "pulses": {
            "on_dispatched_monotonic_ns": on[0],
            "on_acknowledged_monotonic_ns": on[1],
            "off_dispatched_monotonic_ns": off[0],
            "off_acknowledged_monotonic_ns": off[1],
        },
    }
    _lines(
        protocol / f"{prefix}_behavioral_cam_frames.jsonl",
        [header, *frames, *video, completion],
    )

    # Stimulus: 60 Hz render groups alternating the photodiode marker (every_frame).
    groups, display_edges = [], []
    for g in range(int(TRIAL_S * 60) - 2):
        host = H0 + 5_000_000 + int(g * 1e9 / 60)
        high = g % 2 == 0
        groups.append(
            {
                "payload": {
                    "kind": "render_group",
                    "group_id": g,
                    "state": {
                        "epoch_occurrence": 0,
                        "scene_id": "s",
                        "evaluation_host_ns": host - 1000,
                        "images": [],
                    },
                    "submissions": [
                        {
                            "output_id": "right",
                            "attempt_index": g,
                            "phase": "returned",
                            "entry_host_ns": host - 500,
                            "return_host_ns": host,
                            "swap_interval": 1,
                            "marker_index": g,
                            "marker_high": high,
                            "failure_code": None,
                        },
                        {
                            "output_id": "front",
                            "attempt_index": g,
                            "phase": "returned",
                            "entry_host_ns": host - 500,
                            "return_host_ns": host,
                            "swap_interval": 1,
                            "marker_index": None,
                            "marker_high": None,
                            "failure_code": None,
                        },
                    ],
                    "captures": [],
                }
            }
        )
        display_edges.append(host_to_obx(host) + DISPLAY_LATENCY_S)
    stim_header = {
        "payload": {"kind": "header", "format_version": 6, "trial_start_host_ns": H0}
    }
    stim_done = {
        "payload": {
            "kind": "completion",
            "cutoff_host_ns": t_stop,
            "outcome": "completed",
        }
    }
    _lines(
        protocol / f"{prefix}_stimulus_frames.jsonl", [stim_header, *groups, stim_done]
    )
    pose = {
        "kind": "pose",
        "observation_id": "p0",
        "reset_generation": "1",
        "source": {"frame_id": 3, "host_receipt_ns": H0 + 1},
        "completion_host_ns": H0 + 2,
        "method": "m",
        "validity": "valid",
        "landmarks": {
            "tip": {"x_px": 1.5, "y_px": 2.0},
            "left_base": {"x_px": 0.0, "y_px": 0.0},
            "right_base": {"x_px": 3.0, "y_px": 0.0},
        },
        "selected_score": 0.9,
        "disposition": "published",
    }
    _lines(
        protocol / f"{prefix}_tracking.jsonl",
        [
            {
                "record": {
                    "kind": "header",
                    "schema_version": 3,
                    "stream_kind": "tracking",
                }
            },
            {"record": pose},
            {
                "record": {
                    "kind": "completion",
                    "cutoff_host_ns": t_stop,
                    "outcome": "completed",
                }
            },
        ],
    )
    (protocol / f"{prefix}_stimulus_LOG.json").write_text(
        json.dumps(
            {
                "display": {
                    "photodiode_enabled": True,
                    "photodiode_patches": {"right": {}},
                }
            }
        )
    )

    recorded = "C:\\Data\\elsewhere\\protocol-data\\"
    (protocol / f"{prefix}_LOG.json").write_text(
        json.dumps(
            {
                "trial_number": 1,
                "complete": True,
                "outcome": "completed",
                "outputs": [
                    {
                        "path": recorded + f"{prefix}_behavioral_cam_frames.jsonl",
                        "output_tag": "behavioral_cam_frames",
                        "closure": "OUTPUT_CLOSURE_CLOSED",
                        "counts": {
                            "source_frames": len(frames),
                            "video_frames": len(video),
                        },
                    },
                    {
                        "path": recorded + f"{prefix}_stimulus_frames.jsonl",
                        "output_tag": "stimulus_frames",
                        "closure": "OUTPUT_CLOSURE_CLOSED",
                        "counts": {"render_groups": len(groups)},
                    },
                ],
            }
        )
    )
    _lines(
        protocol / "SESSION_LOG.jsonl",
        [
            {"monotonic_ns": H0, "event_type": "trial_started", "trial_number": 1},
            {
                "monotonic_ns": t_stop,
                "event_type": "trial_finished",
                "trial_number": 1,
                "outcome": "completed",
            },
        ],
    )
    config: dict = {"session_id": "s-1", "session_setup_monotonic_ns": H0 - 10**10}
    if paired:
        config["spikeglx"] = {
            "run_name": session.name,
            "pulse_channels": [
                {"role": "PULSE_ROLE_TRIAL_STATE", "family": "STREAM_FAMILY_ONEBOX"},
                {
                    "role": "PULSE_ROLE_PHOTODIODE",
                    "family": "STREAM_FAMILY_ONEBOX",
                    "channel_index": 1,
                },
                {
                    "role": "PULSE_ROLE_BEHAVIORAL_CAMERA",
                    "family": "STREAM_FAMILY_ONEBOX",
                    "channel_index": 2,
                },
            ],
        }
    (protocol / "SESSION_CONFIG.json").write_text(json.dumps(config))

    # OneBox: 12 analog + DW + SY; Trial-state HIGH between the command dispatch and ACK.
    run = session / "spikeglx-data" / f"{session.name}_g0"
    run.mkdir(parents=True)
    n = int(20 * RATE)
    data = np.zeros((n, 14), np.int16)
    t = np.arange(n) / RATE
    rise, fall = host_to_obx(H0 + 10_000_000), host_to_obx(t_stop + 10_000_000)
    data[:, 0] = np.where((t >= rise) & (t < fall), 30000, 0)
    level = np.zeros(n, bool)
    for i, edge in enumerate(display_edges):
        level[int(round(edge * RATE)) :] = i % 2 == 0
    ripple = 1 + 0.3 * np.sign(
        np.sin(2 * np.pi * 3000 * t)
    )  # projector sub-frame flicker
    data[:, 1] = np.where(level, 18000 * ripple, 400).astype(np.int16)
    data[:, 2] = np.where(
        _square(n, np.rint(pulses_obx * RATE).astype(int), 20), 30000, 200
    )
    sy = np.floor(t) % 2 == 0
    data[:, 13] = np.where(sy, 64, 0)
    data.tofile(run / f"{session.name}_g0_t0.obx0.obx.bin")
    chan_map = (
        "(12,1,1)"
        + "".join(f"(XA{i};{i}:{i})" for i in range(12))
        + "(XD0;12:12)(SY0;13:13)"
    )
    (run / f"{session.name}_g0_t0.obx0.obx.meta").write_text(
        f"nSavedChans=14\nobSampRate={RATE}\nsnsSaveChanSubset=all\nfirstSample=0\n"
        f"syncSourceIdx=3\n~snsChanMap={chan_map}\n"
    )
    probe = run / f"{session.name}_g0_imec0"
    probe.mkdir()
    ti = np.arange(int(20 * IMEC_RATE)) / IMEC_RATE
    obx_equiv = (ti - IMEC_OFFSET) / IMEC_SLOPE
    imec = np.zeros((ti.size, 3), np.int16)
    imec[:, 2] = np.where(np.floor(obx_equiv) % 2 == 0, 64, 0)
    imec.tofile(probe / f"{session.name}_g0_t0.imec0.ap.bin")
    (probe / f"{session.name}_g0_t0.imec0.ap.meta").write_text(
        f"nSavedChans=3\nimSampRate={IMEC_RATE}\nfirstSample=0\nsyncSourceIdx=3\n"
        "~snsChanMap=(2,0,1)(AP0;0:0)(AP1;1:1)(SY0;2:2)\n"
    )
    (session / "expected.json").write_text(
        json.dumps(
            {
                "pulses": expected_pulses,
                "pulse_times": pulses_obx.tolist(),
                "display": display_edges,
            }
        )
    )
    return session


def test_compiles_and_aligns_session(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    expected = json.loads((session / "expected.json").read_text())
    report = compile_session(session, Settings(camera_latency_s=(0.010, 0.030)))
    assert report.status == "written", report.error
    assert not list(session.glob("*.partial"))
    with h5py.File(report.output, "r") as h5:
        trial = h5["trials/0001"]
        np.testing.assert_allclose(
            trial.attrs["trial_state_obx_s"], [2.010, 12.010], atol=2e-3
        )
        frames = trial["cameras/behavioral/frames"]
        assert frames["host_receipt_ns"].dtype == np.int64
        assert (
            frames["host_receipt_ns"][0]
            == obx_to_host(expected["pulse_times"][expected["pulses"][0]]) + 20_000_000
        )
        assert (
            frames["pulse_index"][:].tolist() == expected["pulses"]
        )  # missed trigger kept as a gap
        assert set(frames["timing_status"][:]) == {2}
        np.testing.assert_allclose(
            frames["time_obx_s"][:],
            np.array(expected["pulse_times"])[expected["pulses"]],
            atol=1e-3,
        )
        fit = json.loads(trial["cameras/behavioral/alignment"][()])
        assert fit["status"] == "inferred" and fit["margin_ms"] > 2
        subs = trial["stimulus/submissions"]
        right = subs["output_id"][:].astype(str) == "right"
        times = subs["time_obx_s"][:][right]
        measured = subs["timing_status"][:][right] == 1
        assert measured.mean() > 0.98
        np.testing.assert_allclose(
            times[measured], np.array(expected["display"])[measured], atol=1e-3
        )
        assert np.isnan(subs["time_obx_s"][:][~right]).all()  # no patch on this output
        probe = json.loads(h5["spikeglx/probes/imec0/obx_to_probe"][()])
        assert probe["status"] == "fitted"
        assert probe["slope"] == pytest.approx(IMEC_SLOPE, abs=1e-5)
        assert probe["intercept_s"] == pytest.approx(IMEC_OFFSET, abs=1e-3)
        assert "time_imec0_s" in frames
        assert list(trial["integrity/counts_match"][:]) == [1, 1]
        assert (
            h5["session/cameras/behavioral/frames/frame_id"].shape
            == frames["frame_id"].shape
        )
        poses = trial["tracking/poses"]
        assert poses["source_frame_id"][:].tolist() == [3]
        assert poses["tip_x_px"][0] == 1.5 and not trial["tracking"].attrs["partial"]


def test_camera_offset_unresolved_without_latency_window(tmp_path: Path) -> None:
    report = compile_session(make_session(tmp_path), Settings(probe_sync=False))
    with h5py.File(report.output, "r") as h5:
        frames = h5["trials/0001/cameras/behavioral/frames"]
        assert np.isnan(frames["time_obx_s"][:]).all()
        assert set(frames["timing_status"][:]) == {0}
        fit = json.loads(h5["trials/0001/cameras/behavioral/alignment"][()])
        assert fit["status"] == "no_latency_window"
        latencies = [c["median_latency_ms"] for c in fit["candidates"]]
        assert min(abs(v - 20) for v in latencies) < 1


def test_unpaired_session_keeps_host_times(tmp_path: Path) -> None:
    report = compile_session(make_session(tmp_path, paired=False))
    assert report.status == "written" and not report.has_onebox
    with h5py.File(report.output, "r") as h5:
        assert "spikeglx" not in h5
        assert np.isnan(h5["trials/0001/stimulus/render_groups/time_obx_s"][:]).all()
    assert any("Unpaired" in w for w in report.warnings)


def test_jsonl_discards_incomplete_final_line(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_bytes(b'{"a": 9223372036854775807}\n{"a": 2')
    lines = JsonlFile(path)
    assert list(lines) == [{"a": 9223372036854775807}]
    assert lines.truncated
