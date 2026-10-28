"""Measure grating carrier phase in approximate rectified rig-video regions."""

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
VIDEO = Path("C:/Users/ReiterU_PC/Downloads/IMG_1435.MOV")
# Hand-picked image corners at1s, ordered in each declared local screen basis.
QUADS = {
    "Front": ((553, 241), (99, 239), (124, 623), (541, 618)),
    "Left": ((99, 239), (-80, 315), (-40, 1005), (124, 623)),
    "Right": ((720, 319), (553, 241), (541, 618), (670, 1008)),
    "Bottom": ((140, 640), (4, 1008), (634, 1003), (526, 636)),
}
SIZES = {"Front": (94, 85), "Left": (126, 85), "Right": (126, 85), "Bottom": (126, 94)}
SIZE = (512, 384)
DEST = np.float32(((0, 0), (512, 0), (512, 384), (0, 384)))
MATRICES = {k: cv2.getPerspectiveTransform(np.float32(v), DEST) for k, v in QUADS.items()}


def patch(frame, name):
    warped = cv2.warpPerspective(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), MATRICES[name], SIZE)
    return warped[65:319, 90:422].astype(float)


def main():
    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    result = {"source": str(VIDEO), "fps": fps, "frames": len(frames),
              "method": "Fixed approximate manual quads; no camera stabilization or optical calibration",
              "screens": {}}
    reference = frames[round(fps)]
    for name in QUADS:
        first = patch(reference, name)
        h, w = first.shape
        window = np.outer(np.hanning(h), np.hanning(w))
        spectrum = np.fft.fftshift(np.fft.fft2((first - np.mean(first)) * window))
        yy, xx = np.mgrid[:h, :w]
        allowed = (xx > w // 2 + 2) & (np.hypot(xx - w // 2, yy - h // 2) > 5)
        power = np.where(allowed, abs(spectrum), 0)
        py, px = np.unravel_index(np.argmax(power), power.shape)
        fy, fx = (py - h // 2) / h, (px - w // 2) / w
        carrier = np.exp(-2j * np.pi * (fx * xx + fy * yy)) * window
        coefficients = np.array([np.sum((p - p.mean()) * carrier) for p in (patch(f, name) for f in frames)])
        phase = np.unwrap(np.angle(coefficients))
        time = np.arange(len(frames)) / fps
        mask = (time >= 0.5) & (time <= 8.5)
        slope, intercept = np.polyfit(time[mask], phase[mask] / (2 * np.pi), 1)
        residual = phase[mask] / (2 * np.pi) - slope * time[mask] - intercept
        mm_x, mm_y = SIZES[name]
        nx, ny = fx * 512 / mm_x, -fy * 384 / mm_y
        record = dict(carrier_cycles_per_pixel=(float(fx), float(fy)),
                      local_normal_degrees=float(np.degrees(np.arctan2(ny, nx))),
                      phase_cycles_per_second=float(slope), residual_cycles_rms=float(np.sqrt(np.mean(residual**2))))
        result["screens"][name] = record
    (ROOT / "rig-video-phase.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
