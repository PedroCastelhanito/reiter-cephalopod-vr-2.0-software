"""Apply the authorized focused fix to the installed editable camera dependency."""

from pathlib import Path

root = Path(r"C:\Dev\projects\reiter-cephalopod-vr\basler-vision-software")
source = root / "src/basler_vision/core/controller.py"
raw = source.read_bytes()
old = b"            self.camera.start(self.fps)"
new = (
    b"            # Readback FPS is not an operator request to enable frame-rate control.\r\n"
    b"            self.camera.start(self.config.get('fps'))"
)
if raw.count(old) != 1:
    raise RuntimeError("Unexpected camera startup source; no changes applied")
source.write_bytes(raw.replace(old, new))

tests = root / "tests/test_controller_chunk_data.py"
raw = tests.read_bytes()
addition = '''


def test_stream_start_preserves_loaded_frame_rate_enablement():
    for initially_enabled in (False, True):
        controller, camera = _make({})
        camera.rate_enabled = initially_enabled
        camera.start_requests = []

        def start(fps=None):
            camera.start_requests.append(fps)
            if fps:
                camera.rate_enabled = True

        def grab(timeout_ms=250):
            controller.stop_event.set()
            return None, None, None

        camera.start = start
        camera.grab = grab
        # Opening/refreshing discovers FPS, but must not turn it into an override.
        controller.open_camera()
        assert controller.fps == 30
        for _ in range(2):
            controller.stop_event.clear()
            controller.refresh_camera_config()
            controller._publisher_loop()
            assert not controller.publisher_error
            assert camera.rate_enabled is initially_enabled
        assert camera.start_requests == [None, None]


def test_stream_start_retains_explicit_frame_rate_override():
    controller, camera = _make({"fps": 60})
    requests = []

    def start(fps=None):
        requests.append(fps)

    def grab(timeout_ms=250):
        controller.stop_event.set()
        return None, None, None

    camera.start = start
    camera.grab = grab
    controller.open_camera()
    controller._publisher_loop()
    assert not controller.publisher_error
    assert requests == [60]
'''
tests.write_bytes(raw + addition.replace("\n", "\r\n").encode())
print("Patched stream startup and existing camera-controller regressions")
