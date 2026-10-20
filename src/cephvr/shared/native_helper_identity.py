"""E08 controller-owned one-shot native child roles."""

FIRMWARE_UPLOAD_ROLE = "controller_firmware_upload"
PROJECTOR_BRIGHTNESS_ROLE = "controller_projector_brightness"
CONTROLLER_NATIVE_HELPER_ROLES = frozenset(
    (FIRMWARE_UPLOAD_ROLE, PROJECTOR_BRIGHTNESS_ROLE)
)
