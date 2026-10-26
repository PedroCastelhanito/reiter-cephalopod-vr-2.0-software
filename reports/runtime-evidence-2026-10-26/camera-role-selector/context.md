# Camera role selector investigation — 2026-10-26

Source: e6210a3d545c490e10dffa4f7b5bbd0f9a474fa9 plus concurrent working-tree changes.
Owner clarified that the dropdown does not open (not a duplicate-role rejection).
No production source change made by this investigation. Existing role uniqueness,
controller ownership and camera settings remain unchanged under G01/E03.

Original managed process had exited before inspection. Reopen-GUI failed with
OpenEventW error2; normal scripts/start_runtime_gui.py launch succeeded. Computer-use
inspection of actual managed Devices/Cameras verified the dropdown opens with all
four roles in Retro and Amber. Selecting the existing Behavior role closed it;
Behavior40065509 and Tracking40747103 assignments remained unchanged. No camera
capture, Setup or recording action was requested. Runtime left open on Cameras in
Amber. Earlier isolated screenshot/transient popup clipping was not reproduced in
the settled managed window and is not established as the original cause.

Added coverage to the existing GUI behavior module (ARCH-002; no dependencies).
Final commands use .venv/Scripts/python.exe:
- pytest tests/gui/test_dashboard.py -q -k camera_role_dropdown_opens with
  QT_QPA_PLATFORM=windows:3 passed (native-final.txt).
- pytest tests/gui/test_dashboard.py -q -k
  "camera_role_dropdown_opens or camera_role_uniqueness":4 passed
  (offscreen-final.txt).
- Ruff check and format check for tests/gui/test_dashboard.py; git diff --check.

Test development limits: first broader selection timed out in Windows asyncio
socketpair creation under restricted loopback, not camera behavior. Initial mouse
selection attempts needed hover delivery; native synthetic hover still failed
(native-tests.txt), so final coverage explicitly uses mouse opening and keyboard
selection. Early restricted native runs emitted COM0x8001010d diagnostics; final
permitted native run passed. These are not hardware/full-session acceptance.
Original user-observed cause remains unproven; keep follow-up open if it recurs.
