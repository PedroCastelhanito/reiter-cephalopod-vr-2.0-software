#include <Arduino.h>
#include "projector_clock.h"
#include <stdlib.h>
#include <string.h>

// Serial commands:
//   CONFIGURE <cam1_pin> <cam1_fps> [cam2_pin cam2_fps]
//   CONFIGURE CAM1 <pin> <fps>
//   CONFIGURE CAM2 <pin> <fps>
//   ON
//   OFF
//   STARTPIN <pin>  -- override the trial-active gate pin at runtime
//   PLOT ON [period_ms]
//   PLOT OFF
//   STATUS
//   PING
//
// The trial-active GATE defaults to pin kDefaultGatePin (9) on boot and is
// configured as OUTPUT LOW immediately in setup(). ON drives it HIGH (the
// rising edge is t-zero) and OFF drives it LOW (the falling edge marks trial
// end), so the level is HIGH for exactly the duration of the trial. STARTPIN
// <pin> overrides the gate pin at runtime if the default wiring is unsuitable.
// This lets every recorded stream be aligned to the Neuropixels master clock
// post-hoc (improvement-plan item 4.1). Driving a level on ON/OFF is a single
// digitalWrite and never stalls loop().
//
// Connect the projector frame-change TTL to Arduino pin 2. On an Uno/Nano this
// pin supports attachInterrupt(), which gives cleaner timing than polling.
//
// Learn the projector period and phase over 120 intervals (~2 s), then run an
// independent oscillator at that fixed frequency. Recheck phase every 5 minutes
// and apply phase corrections gradually; never re-estimate the frequency.
// 60 fps uses every oscillator cycle; 30 fps uses every other cycle. Calibration
// runs while stopped too. ON waits for initial calibration if necessary; once
// locked, loss of sync does not interrupt the learned pulse train.
//
// The camera trigger delay is 6000 us; TTL pulse width is 3000 us.

namespace {

void serviceTiming();

// Serial.print can block once the UART TX ring fills. Service camera edges
// between bytes and while waiting for buffer space; never write into a full ring.
class TimingSerial : public Print {
 public:
  using Print::write;
  size_t write(uint8_t value) override {
    serviceTiming();
    while (Serial.availableForWrite() <= 0) {
      serviceTiming();
    }
    return Serial.write(value);
  }
};
TimingSerial reply;

constexpr float kProjectorFrameRateHz = 60.0f;
constexpr uint8_t kSyncInputPin = 2;
constexpr unsigned long kTriggerDelayUs = 6000UL;
constexpr unsigned long kPulseWidthUs = 3000UL;
constexpr unsigned long kMinProjectorPulseGapUs = 8000UL;
constexpr unsigned long kSyncVisibleTimeoutUs = 100000UL;
constexpr uint8_t kPlotPin = 2;
constexpr unsigned long kDefaultPlotPeriodUs = 1000UL;
constexpr bool kPlotPin2OnBoot = false;
// Default trial-active gate pin. Held HIGH from ON to OFF so the rising edge
// is t-zero and the falling edge marks trial end. Can be overridden at runtime
// with STARTPIN <pin>. Must not conflict with kSyncInputPin (2) or the default
// camera pins (11, 10).
constexpr uint8_t kDefaultGatePin = 9U;

struct CameraChannel {
  bool active;
  uint8_t pin;
  float fps;
  unsigned int divider;
  unsigned int phase;
  unsigned long freeRunPeriodUs;
  unsigned long nextFreeRunTriggerUs;
  bool pendingHigh;
  bool outputHigh;
  unsigned long triggerDueUs;
  unsigned long highUntilUs;
  unsigned long triggerCount;
};

CameraChannel cameras[2] = {
    {true, 11, 60.0f, 1, 0, 16667UL, 0UL, false, false, 0UL, 0UL, 0UL},
    {true, 10, 30.0f, 2, 0, 33333UL, 0UL, false, false, 0UL, 0UL, 0UL},
};

int syncInterruptNumber = NOT_AN_INTERRUPT;
bool syncUsingInterrupt = false;
bool syncInputWasHigh = false;
bool syncSchedulingActive = false;
bool plotPin2Running = kPlotPin2OnBoot;
unsigned long plotPeriodUs = kDefaultPlotPeriodUs;
unsigned long nextPlotAtUs = 0UL;
bool acquisitionRunning = false;
unsigned long handledProjectorPulseCount = 0UL;
// CAM-13(a/b) / C1+C2: count projector edges that were processed LATE, i.e. a
// pass found multiple unhandled edges. Older edges have no stored timestamp
// and are skipped, never reconstructed or burst-fired. Surfaced in STATUS.
unsigned long backloggedProjectorPulseCount = 0UL;
char commandBuffer[160];
size_t commandLength = 0U;
bool discardCommand = false;
unsigned long expiredCameraTriggerCount = 0UL;

ProjectorClock projectorClock;
volatile unsigned long projectorPulseCount = 0UL;
volatile unsigned long lastProjectorPulseUs = 0UL;

// Item 4.1 (revised): trial-active GATE output on its own OneBox line. ON
// drives it HIGH (the rising edge is the trial-start t-zero) and OFF drives it
// LOW, so the level is HIGH for exactly the duration of the trial. Defaults to
// kDefaultGatePin on boot; can be overridden with STARTPIN <pin> at runtime.
constexpr uint8_t kGatePinUnset = 255U;
uint8_t gatePin = kDefaultGatePin;
bool gateHigh = false;
unsigned long gateAssertCount = 0UL;

void recordProjectorPulse(unsigned long nowUs) {
  if (projectorPulseCount > 0UL &&
      (long)(nowUs - lastProjectorPulseUs) < (long)kMinProjectorPulseGapUs) {
    return;
  }
  projectorPulseCount++;
  lastProjectorPulseUs = nowUs;
}

float absFloat(float value) {
  return value < 0.0f ? -value : value;
}

void projectorFrameIsr() {
  recordProjectorPulse(micros());
}

void driveCameraLow(CameraChannel &camera) {
  digitalWrite(camera.pin, LOW);
  camera.pendingHigh = false;
  camera.outputHigh = false;
}

void resetCameraTiming(CameraChannel &camera) {
  camera.pendingHigh = false;
  camera.outputHigh = false;
  camera.triggerDueUs = 0UL;
  camera.highUntilUs = 0UL;
  camera.nextFreeRunTriggerUs = 0UL;
  camera.triggerCount = 0UL;
}

bool activeConfigUsesPin(bool cam1Active,
                         uint8_t cam1Pin,
                         bool cam2Active,
                         uint8_t cam2Pin,
                         uint8_t pin) {
  return (cam1Active && cam1Pin == pin) || (cam2Active && cam2Pin == pin);
}

void releaseOldCameraPinIfUnused(uint8_t oldPin,
                                 bool cam1Active,
                                 uint8_t cam1Pin,
                                 bool cam2Active,
                                 uint8_t cam2Pin) {
  if (!activeConfigUsesPin(cam1Active, cam1Pin, cam2Active, cam2Pin, oldPin)) {
    pinMode(oldPin, INPUT);
  }
}

void configureCameraChannels(bool cam1Active,
                             uint8_t cam1Pin,
                             float cam1Fps,
                             unsigned int cam1Divider,
                             unsigned long cam1FreeRunPeriodUs,
                             bool cam2Active,
                             uint8_t cam2Pin,
                             float cam2Fps,
                             unsigned int cam2Divider,
                             unsigned long cam2FreeRunPeriodUs) {
  digitalWrite(cameras[0].pin, LOW);
  digitalWrite(cameras[1].pin, LOW);

  const uint8_t oldCam1Pin = cameras[0].pin;
  const uint8_t oldCam2Pin = cameras[1].pin;
  releaseOldCameraPinIfUnused(
      oldCam1Pin, cam1Active, cam1Pin, cam2Active, cam2Pin);
  if (oldCam2Pin != oldCam1Pin) {
    releaseOldCameraPinIfUnused(
        oldCam2Pin, cam1Active, cam1Pin, cam2Active, cam2Pin);
  }

  cameras[0].active = cam1Active;
  cameras[0].pin = cam1Pin;
  cameras[0].fps = cam1Fps;
  cameras[0].divider = cam1Divider;
  cameras[0].freeRunPeriodUs = cam1FreeRunPeriodUs;
  cameras[0].phase = 0U;
  resetCameraTiming(cameras[0]);

  cameras[1].active = cam2Active;
  if (cam2Active) {
    cameras[1].pin = cam2Pin;
    cameras[1].fps = cam2Fps;
    cameras[1].divider = cam2Divider;
    cameras[1].freeRunPeriodUs = cam2FreeRunPeriodUs;
  } else {
    cameras[1].fps = 0.0f;
    cameras[1].divider = 0U;
    cameras[1].freeRunPeriodUs = 0UL;
  }
  cameras[1].phase = 0U;
  resetCameraTiming(cameras[1]);

  if (cameras[0].active) {
    pinMode(cameras[0].pin, OUTPUT);
    driveCameraLow(cameras[0]);
  }
  if (cameras[1].active) {
    pinMode(cameras[1].pin, OUTPUT);
    driveCameraLow(cameras[1]);
  }
}

bool fpsToDivider(float fps, unsigned int &divider) {
  if (fps <= 0.0f || fps > kProjectorFrameRateHz) {
    return false;
  }

  const float exactDivider = kProjectorFrameRateHz / fps;
  const unsigned int roundedDivider = (unsigned int)(exactDivider + 0.5f);
  if (roundedDivider < 1U) {
    return false;
  }

  const float effectiveFps = kProjectorFrameRateHz / (float)roundedDivider;
  if (absFloat(effectiveFps - fps) > 0.001f) {
    return false;
  }

  divider = roundedDivider;
  return true;
}

bool fpsToPeriodUs(float fps, unsigned long &periodUs) {
  if (fps <= 0.0f) {
    return false;
  }

  const unsigned long requestedPeriodUs =
      (unsigned long)(1000000.0f / fps + 0.5f);
  if (requestedPeriodUs == 0UL || requestedPeriodUs <= kPulseWidthUs) {
    return false;
  }

  periodUs = requestedPeriodUs;
  return true;
}

bool isValidPin(long pin) {
  return pin >= 0L && pin <= 255L;
}

bool isHardwareSerialPin(long pin) {
  return pin == 0L || pin == 1L;
}

bool isSerialCommandByte(char value) {
  const uint8_t byteValue = (uint8_t)value;
  return value == '\t' || (byteValue >= 32U && byteValue <= 126U);
}

bool isAsciiLetter(char value) {
  const uint8_t byteValue = (uint8_t)value;
  return (byteValue >= (uint8_t)'A' && byteValue <= (uint8_t)'Z') ||
         (byteValue >= (uint8_t)'a' && byteValue <= (uint8_t)'z');
}

char *findCommandStart(char *line) {
  while (*line != '\0' && !isAsciiLetter(*line)) {
    line++;
  }
  return line;
}

bool canUseSyncInterrupt(uint8_t pin) {
  return digitalPinToInterrupt(pin) != NOT_AN_INTERRUPT;
}

void detachSyncInterrupt() {
  if (syncInterruptNumber != NOT_AN_INTERRUPT) {
    detachInterrupt(syncInterruptNumber);
    syncInterruptNumber = NOT_AN_INTERRUPT;
  }
}

void resetProjectorCounters() {
  noInterrupts();
  projectorPulseCount = 0UL;
  lastProjectorPulseUs = 0UL;
  interrupts();
  handledProjectorPulseCount = 0UL;
  backloggedProjectorPulseCount = 0UL;
  expiredCameraTriggerCount = 0UL;
  syncSchedulingActive = false;
  projectorClock = ProjectorClock();
}

bool hasVisibleProjectorSync(unsigned long nowUs) {
  unsigned long pulseCountSnapshot;
  unsigned long pulseTimeSnapshot;
  noInterrupts();
  pulseCountSnapshot = projectorPulseCount;
  pulseTimeSnapshot = lastProjectorPulseUs;
  interrupts();

  return pulseCountSnapshot > 0UL &&
         (long)(nowUs - pulseTimeSnapshot) <= (long)kSyncVisibleTimeoutUs;
}

void driveGate(bool high) {
  if (gatePin == kGatePinUnset) {
    return;
  }
  digitalWrite(gatePin, high ? HIGH : LOW);
  if (high && !gateHigh) {
    gateAssertCount++;
  }
  gateHigh = high;
}

void stopAcquisition() {
  acquisitionRunning = false;
  for (uint8_t index = 0; index < 2U; index++) {
    if (cameras[index].active) {
      driveCameraLow(cameras[index]);
    } else {
      resetCameraTiming(cameras[index]);
    }
  }
  // Trial gate falls with OFF / any acquisition teardown (improvement-plan 4.1).
  driveGate(false);
}

void startAcquisition() {
  stopAcquisition();
  expiredCameraTriggerCount = 0UL;
  for (uint8_t index = 0; index < 2U; index++) {
    cameras[index].triggerCount = 0UL;
  }
  acquisitionRunning = true;
  driveGate(true);
}

void startSyncMonitor() {
  pinMode(kSyncInputPin, INPUT);
  syncInputWasHigh = digitalRead(kSyncInputPin) == HIGH;
  syncInterruptNumber = digitalPinToInterrupt(kSyncInputPin);
  syncUsingInterrupt = syncInterruptNumber != NOT_AN_INTERRUPT;
  if (syncUsingInterrupt) {
    attachInterrupt(syncInterruptNumber, projectorFrameIsr, RISING);
  }
}

void pollProjectorSyncInput() {
  if (syncUsingInterrupt) {
    return;
  }

  const bool syncInputHigh = digitalRead(kSyncInputPin) == HIGH;
  if (syncInputHigh && !syncInputWasHigh) {
    noInterrupts();
    recordProjectorPulse(micros());
    interrupts();
  }
  syncInputWasHigh = syncInputHigh;
}

void scheduleCameraTriggerAt(CameraChannel &camera, unsigned long triggerDueUs) {
  camera.pendingHigh = true;
  camera.triggerDueUs = triggerDueUs;
}

void processProjectorSync() {
  unsigned long count, edge;
  noInterrupts();
  count = projectorPulseCount;
  edge = lastProjectorPulseUs;
  interrupts();
  if (count != handledProjectorPulseCount) {
    backloggedProjectorPulseCount += count - handledProjectorPulseCount - 1UL;
    handledProjectorPulseCount = count;
    projectorClock.observe(uint32_t(count), uint32_t(edge));
  }
  syncSchedulingActive = projectorClock.locked;
}

void updateLearnedClockTriggers() {
  uint32_t edge, frame;
  if (!projectorClock.tick(uint32_t(micros()), edge, frame)) return;
  if (!acquisitionRunning) return;
  for (uint8_t index = 0; index < 2U; index++) {
    CameraChannel &camera = cameras[index];
    if (camera.active && frame % camera.divider == camera.phase) {
      scheduleCameraTriggerAt(camera, (unsigned long)edge + kTriggerDelayUs);
    }
  }
}

void updateCameraOutput(CameraChannel &camera) {
  if (!camera.active) {
    resetCameraTiming(camera);
    return;
  }

  const unsigned long nowUs = micros();

  if (camera.outputHigh && (long)(nowUs - camera.highUntilUs) >= 0L) {
    digitalWrite(camera.pin, LOW);
    camera.outputHigh = false;
  }

  if (camera.pendingHigh && (long)(nowUs - camera.triggerDueUs) >= 0L) {
    camera.pendingHigh = false;
    if (camera.outputHigh || nowUs - camera.triggerDueUs >= kPulseWidthUs) {
      expiredCameraTriggerCount++;
      return;
    }
    digitalWrite(camera.pin, HIGH);
    camera.outputHigh = true;
    camera.highUntilUs = nowUs + kPulseWidthUs;
    camera.triggerCount++;
  }
}

void updateCameraOutputs() {
  updateCameraOutput(cameras[0]);
  updateCameraOutput(cameras[1]);
}

void updatePin2Plotter() {
  if (!plotPin2Running) {
    return;
  }
  // CAM-13(a): never stream the per-period pin2 plot samples while acquisition
  // is running; the continuous Serial output would block loop() and perturb the
  // camera trigger timing. Plotting is a bench-diagnostic tool, used with
  // acquisition stopped.
  if (acquisitionRunning) {
    return;
  }

  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextPlotAtUs) < 0L) {
    return;
  }
  nextPlotAtUs = nowUs + plotPeriodUs;

  reply.print(F("pin2:"));
  reply.println(digitalRead(kPlotPin) == HIGH ? 1 : 0);
}

void printCameraStatus(const __FlashStringHelper *label,
                       const CameraChannel &camera) {
  reply.print(F(" "));
  reply.print(label);
  reply.print(F("_enabled="));
  reply.print(camera.active ? 1 : 0);
  reply.print(F(" "));
  reply.print(label);
  reply.print(F("_pin="));
  reply.print(camera.pin);
  reply.print(F(" "));
  reply.print(label);
  reply.print(F("_fps="));
  reply.print(camera.fps, 6);
  reply.print(F(" "));
  reply.print(label);
  reply.print(F("_divider="));
  reply.print(camera.divider);
  reply.print(F(" "));
  reply.print(label);
  reply.print(F("_triggers="));
  reply.print(camera.triggerCount);
}

void printClockStatus() {
  reply.print(F(" clock_locked="));
  reply.print(projectorClock.locked ? 1 : 0);
  reply.print(F(" learned_period_us="));
  reply.print((float)projectorClock.periodQ16 / 65536.0f, 4);
  reply.print(F(" clock_checks="));
  reply.print(projectorClock.checks);
  reply.print(F(" phase_error_us="));
  reply.print(projectorClock.phaseErrorUs);
  reply.print(F(" correction_remaining_us="));
  reply.print(projectorClock.remainingCorrectionUs);
  reply.print(F(" skipped_clock_ticks="));
  reply.print(projectorClock.skippedTicks);
}

void printStatus() {
  unsigned long pulseCountSnapshot;
  unsigned long pulseTimeSnapshot;
  noInterrupts();
  pulseCountSnapshot = projectorPulseCount;
  pulseTimeSnapshot = lastProjectorPulseUs;
  interrupts();

  // Keep heartbeat replies concise; TimingSerial services deadlines even if
  // the UART TX ring fills. OFF exposes the full diagnostic status.
  if (acquisitionRunning) {
    reply.print(F("OK STATUS running=1 trigger_mode="));
    reply.print(syncSchedulingActive ? F("learned_clock") : F("calibrating"));
    reply.print(F(" projector_pulses="));
    reply.print(pulseCountSnapshot);
    reply.print(F(" cam1_triggers="));
    reply.print(cameras[0].triggerCount);
    reply.print(F(" cam2_triggers="));
    reply.print(cameras[1].triggerCount);
    reply.print(F(" expired_camera_triggers="));
    reply.print(expiredCameraTriggerCount);
    reply.print(F(" gate_state="));
    reply.print(gateHigh ? 1 : 0);
    printClockStatus();
    reply.print(F(" sync_visible="));
    reply.print(hasVisibleProjectorSync(micros()) ? 1 : 0);
    reply.println(F(" detail=suppressed_during_acquisition"));
    return;
  }

  reply.print(F("OK STATUS running="));
  reply.print(acquisitionRunning ? 1 : 0);
  reply.print(F(" trigger_mode="));
  reply.print(syncSchedulingActive ? F("learned_clock") : F("calibrating"));
  reply.print(F(" sync_pin="));
  reply.print(kSyncInputPin);
  reply.print(F(" sync_mode="));
  reply.print(syncUsingInterrupt ? F("interrupt") : F("polling"));
  reply.print(F(" sync_interrupt_capable="));
  reply.print(canUseSyncInterrupt(kSyncInputPin) ? 1 : 0);
  reply.print(F(" projector_hz="));
  reply.print(kProjectorFrameRateHz, 6);
  reply.print(F(" projector_pulses="));
  reply.print(pulseCountSnapshot);
  reply.print(F(" expired_camera_triggers="));
  reply.print(expiredCameraTriggerCount);
  reply.print(F(" backlogged_projector_pulses="));
  reply.print(backloggedProjectorPulseCount);
  reply.print(F(" sync_seen="));
  reply.print(pulseCountSnapshot > 0UL ? 1 : 0);
  reply.print(F(" sync_visible="));
  reply.print(hasVisibleProjectorSync(micros()) ? 1 : 0);
  reply.print(F(" last_sync_age_ms="));
  if (pulseCountSnapshot > 0UL) {
    reply.print((micros() - pulseTimeSnapshot) / 1000UL);
  } else {
    reply.print(-1);
  }
  reply.print(F(" trigger_delay_us="));
  reply.print(kTriggerDelayUs);
  reply.print(F(" pulse_width_us="));
  reply.print(kPulseWidthUs);
  reply.print(F(" plot_pin2="));
  reply.print(plotPin2Running ? 1 : 0);
  reply.print(F(" plot_period_ms="));
  reply.print(plotPeriodUs / 1000UL);
  reply.print(F(" gate_pin="));
  reply.print(gatePin == kGatePinUnset ? -1 : (int)gatePin);
  reply.print(F(" gate_state="));
  reply.print(gateHigh ? 1 : 0);
  reply.print(F(" gate_asserts="));
  reply.print(gateAssertCount);
  printCameraStatus(F("cam1"), cameras[0]);
  printCameraStatus(F("cam2"), cameras[1]);
  printClockStatus();
  reply.println();
}

void handlePlotCommand(char *modeToken, char *periodToken) {
  if (modeToken == nullptr) {
    reply.println(F("ERR PLOT requires: ON [period_ms] or OFF"));
    return;
  }

  if (strcasecmp(modeToken, "OFF") == 0) {
    plotPin2Running = false;
    reply.println(F("OK PLOT OFF"));
    return;
  }

  if (strcasecmp(modeToken, "ON") != 0) {
    reply.println(F("ERR PLOT requires: ON [period_ms] or OFF"));
    return;
  }

  // CAM-13(a): the plotter streams a Serial sample every period; refuse to start
  // it during active acquisition so it cannot interfere with trigger timing.
  if (acquisitionRunning) {
    reply.println(F("ERR Cannot start pin2 plot during active acquisition; send OFF first"));
    return;
  }

  const long requestedPeriodMs =
      periodToken == nullptr ? (long)(kDefaultPlotPeriodUs / 1000UL)
                             : atol(periodToken);
  if (requestedPeriodMs <= 0L || requestedPeriodMs > 1000L) {
    reply.println(F("ERR plot period_ms must be between 1 and 1000"));
    return;
  }
  if ((cameras[0].active && cameras[0].pin == kPlotPin) ||
      (cameras[1].active && cameras[1].pin == kPlotPin)) {
    reply.println(F("ERR Cannot plot pin2 while pin2 is configured as a camera output"));
    return;
  }

  pinMode(kPlotPin, INPUT);
  plotPeriodUs = (unsigned long)requestedPeriodMs * 1000UL;
  nextPlotAtUs = micros();
  plotPin2Running = true;
  reply.print(F("OK PLOT ON pin=2 period_ms="));
  reply.println(requestedPeriodMs);
}

void handleStartPinCommand(char *pinToken) {
  if (pinToken == nullptr) {
    reply.println(F("ERR STARTPIN requires: STARTPIN <pin>"));
    return;
  }
  const long requestedPin = atol(pinToken);
  if (!isValidPin(requestedPin)) {
    reply.println(F("ERR Pins must be between 0 and 255"));
    return;
  }
  if (isHardwareSerialPin(requestedPin)) {
    reply.println(F("ERR Gate pin must not use hardware serial pins 0 or 1"));
    return;
  }
  if (requestedPin == kSyncInputPin) {
    reply.println(F("ERR Gate pin must not use projector sync pin 2"));
    return;
  }
  if ((cameras[0].active && cameras[0].pin == (uint8_t)requestedPin) ||
      (cameras[1].active && cameras[1].pin == (uint8_t)requestedPin)) {
    reply.println(F("ERR Gate pin must not use a camera output pin"));
    return;
  }

  const uint8_t newPin = (uint8_t)requestedPin;
  if (gatePin != newPin) {
    if (gatePin != kGatePinUnset) {
      digitalWrite(gatePin, LOW);
    }
    gatePin = newPin;
    pinMode(gatePin, OUTPUT);
    gateHigh = false;
  }
  // The gate is a level, not a pulse: reflect the current trial state now (HIGH
  // if a trial is already running, otherwise LOW) and let ON/OFF flip it.
  driveGate(acquisitionRunning);
  reply.print(F("OK STARTPIN pin="));
  reply.println(gatePin);
}

void printConfigureStatus() {
  reply.print(F("OK CONFIGURE sync_pin="));
  reply.print(kSyncInputPin);
  reply.print(F(" sync_interrupt_capable="));
  reply.print(canUseSyncInterrupt(kSyncInputPin) ? 1 : 0);
  reply.print(F(" trigger_delay_us="));
  reply.print(kTriggerDelayUs);
  reply.print(F(" pulse_width_us="));
  reply.print(kPulseWidthUs);
  printCameraStatus(F("cam1"), cameras[0]);
  printCameraStatus(F("cam2"), cameras[1]);
  reply.println();
}

bool computeCameraTiming(float requestedFps,
                         unsigned int &divider,
                         unsigned long &freeRunPeriodUs) {
  if (!fpsToDivider(requestedFps, divider)) {
    reply.println(F("ERR fps must divide the 60 Hz projector rate exactly, e.g. 60, 30, 20, 15, 12, 10, 6, 5, 4, 3, 2, 1"));
    return false;
  }
  if (!fpsToPeriodUs(requestedFps, freeRunPeriodUs)) {
    reply.println(F("ERR fps is too high for the fixed 3000 us pulse width"));
    return false;
  }
  return true;
}

bool validateCameraPinForSlot(uint8_t slot, long requestedPin) {
  if (!isValidPin(requestedPin)) {
    reply.println(F("ERR Pins must be between 0 and 255"));
    return false;
  }
  if (isHardwareSerialPin(requestedPin)) {
    reply.println(F("ERR Camera pins must not use hardware serial pins 0 or 1"));
    return false;
  }
  if (requestedPin == kSyncInputPin) {
    reply.println(F("ERR Camera pins must not use projector sync pin 2"));
    return false;
  }

  const uint8_t otherSlot = slot == 0U ? 1U : 0U;
  if (cameras[otherSlot].active && cameras[otherSlot].pin == requestedPin) {
    reply.println(F("ERR Camera pins must be different"));
    return false;
  }
  return true;
}

void configureSingleCameraSlot(uint8_t slot, long requestedPin, float requestedFps) {
  if (slot > 1U || !validateCameraPinForSlot(slot, requestedPin)) {
    return;
  }

  unsigned int divider = 1U;
  unsigned long freeRunPeriodUs = 0UL;
  if (!computeCameraTiming(requestedFps, divider, freeRunPeriodUs)) {
    return;
  }

  bool cam1Active = cameras[0].active;
  uint8_t cam1Pin = cameras[0].pin;
  float cam1Fps = cameras[0].fps;
  unsigned int cam1Divider = cameras[0].divider;
  unsigned long cam1FreeRunPeriodUs = cameras[0].freeRunPeriodUs;

  bool cam2Active = cameras[1].active;
  uint8_t cam2Pin = cameras[1].pin;
  float cam2Fps = cameras[1].fps;
  unsigned int cam2Divider = cameras[1].divider;
  unsigned long cam2FreeRunPeriodUs = cameras[1].freeRunPeriodUs;

  if (slot == 0U) {
    cam1Active = true;
    cam1Pin = (uint8_t)requestedPin;
    cam1Fps = requestedFps;
    cam1Divider = divider;
    cam1FreeRunPeriodUs = freeRunPeriodUs;
  } else {
    cam2Active = true;
    cam2Pin = (uint8_t)requestedPin;
    cam2Fps = requestedFps;
    cam2Divider = divider;
    cam2FreeRunPeriodUs = freeRunPeriodUs;
  }

  stopAcquisition();
  configureCameraChannels(
      cam1Active,
      cam1Pin,
      cam1Fps,
      cam1Divider,
      cam1FreeRunPeriodUs,
      cam2Active,
      cam2Pin,
      cam2Fps,
      cam2Divider,
      cam2FreeRunPeriodUs);
  pinMode(kSyncInputPin, INPUT);
  resetProjectorCounters();
  printConfigureStatus();
}

int inferSingleCameraSlot(uint8_t requestedPin) {
  for (uint8_t index = 0; index < 2U; index++) {
    if (cameras[index].active && cameras[index].pin == requestedPin) {
      return index;
    }
  }
  for (uint8_t index = 0; index < 2U; index++) {
    if (!cameras[index].active) {
      return index;
    }
  }
  return 0;
}

void configureBothCameraSlots(long requestedCam1Pin,
                              float requestedCam1Fps,
                              long requestedCam2Pin,
                              float requestedCam2Fps) {
  if (!isValidPin(requestedCam1Pin) || !isValidPin(requestedCam2Pin)) {
    reply.println(F("ERR Pins must be between 0 and 255"));
    return;
  }
  if (isHardwareSerialPin(requestedCam1Pin) ||
      isHardwareSerialPin(requestedCam2Pin)) {
    reply.println(F("ERR Camera pins must not use hardware serial pins 0 or 1"));
    return;
  }
  if (requestedCam1Pin == kSyncInputPin || requestedCam2Pin == kSyncInputPin) {
    reply.println(F("ERR Camera pins must not use projector sync pin 2"));
    return;
  }
  if (requestedCam1Pin == requestedCam2Pin) {
    reply.println(F("ERR Camera pins must be different"));
    return;
  }

  unsigned int cam1Divider = 1U;
  unsigned int cam2Divider = 1U;
  unsigned long cam1FreeRunPeriodUs = 0UL;
  unsigned long cam2FreeRunPeriodUs = 0UL;
  if (!computeCameraTiming(
          requestedCam1Fps, cam1Divider, cam1FreeRunPeriodUs) ||
      !computeCameraTiming(
          requestedCam2Fps, cam2Divider, cam2FreeRunPeriodUs)) {
    return;
  }

  stopAcquisition();
  configureCameraChannels(
      true,
      (uint8_t)requestedCam1Pin,
      requestedCam1Fps,
      cam1Divider,
      cam1FreeRunPeriodUs,
      true,
      (uint8_t)requestedCam2Pin,
      requestedCam2Fps,
      cam2Divider,
      cam2FreeRunPeriodUs);
  pinMode(kSyncInputPin, INPUT);
  resetProjectorCounters();
  printConfigureStatus();
}

void handleConfigureCommand(char *cam1PinToken,
                            char *cam1FpsToken,
                            char *cam2PinToken,
                            char *cam2FpsToken,
                            char *extraToken) {
  if (cam1PinToken == nullptr) {
    reply.println(F("ERR CONFIGURE requires: [CAM1|CAM2] pin fps or pin fps [pin fps]"));
    return;
  }

  if (strcasecmp(cam1PinToken, "CAM1") == 0 ||
      strcasecmp(cam1PinToken, "CAM2") == 0) {
    if (cam1FpsToken == nullptr || cam2PinToken == nullptr ||
        cam2FpsToken != nullptr || extraToken != nullptr) {
      reply.println(F("ERR CONFIGURE CAM1/CAM2 requires: CONFIGURE CAM1 pin fps"));
      return;
    }
    const uint8_t slot = strcasecmp(cam1PinToken, "CAM1") == 0 ? 0U : 1U;
    configureSingleCameraSlot(slot, atol(cam1FpsToken), atof(cam2PinToken));
    return;
  }

  if (cam1FpsToken == nullptr) {
    reply.println(F("ERR CONFIGURE requires: pin fps [pin fps]"));
    return;
  }

  if ((cam2PinToken == nullptr) != (cam2FpsToken == nullptr) ||
      extraToken != nullptr) {
    reply.println(F("ERR CONFIGURE accepts either 2 or 4 values: cam1_pin cam1_fps [cam2_pin cam2_fps]"));
    return;
  }

  const bool configureSecondCamera = cam2PinToken != nullptr;
  const long requestedCam1Pin = atol(cam1PinToken);
  const float requestedCam1Fps = atof(cam1FpsToken);
  if (!configureSecondCamera) {
    if (!isValidPin(requestedCam1Pin)) {
      reply.println(F("ERR Pins must be between 0 and 255"));
      return;
    }
    configureSingleCameraSlot(
        (uint8_t)inferSingleCameraSlot((uint8_t)requestedCam1Pin),
        requestedCam1Pin,
        requestedCam1Fps);
    return;
  }

  configureBothCameraSlots(
      requestedCam1Pin,
      requestedCam1Fps,
      atol(cam2PinToken),
      atof(cam2FpsToken));
}

void handleCommand(char *line) {
  char *command = strtok(line, " \t");
  if (command == nullptr) {
    return;
  }

  if (strcasecmp(command, "PING") == 0) {
    reply.println(F("OK PONG"));
    return;
  }
  if (strcasecmp(command, "STATUS") == 0) {
    printStatus();
    return;
  }
  if (strcasecmp(command, "PLOT") == 0) {
    char *modeToken = strtok(nullptr, " \t");
    char *periodToken = strtok(nullptr, " \t");
    handlePlotCommand(modeToken, periodToken);
    return;
  }
  if (strcasecmp(command, "OFF") == 0) {
    stopAcquisition();
    reply.println(F("OK OFF"));
    return;
  }
  if (strcasecmp(command, "ON") == 0) {
    startAcquisition();
    reply.print(F("OK ON waiting_for_projector_sync="));
    reply.print(projectorClock.locked ? 0 : 1);
    reply.print(F(" sync_mode="));
    reply.println(syncUsingInterrupt ? F("interrupt") : F("polling"));
    return;
  }
  if (strcasecmp(command, "STARTPIN") == 0) {
    char *pinToken = strtok(nullptr, " \t");
    handleStartPinCommand(pinToken);
    return;
  }
  if (strcasecmp(command, "CONFIGURE") == 0) {
    char *cam1PinToken = strtok(nullptr, " \t");
    char *cam1FpsToken = strtok(nullptr, " \t");
    char *cam2PinToken = strtok(nullptr, " \t");
    char *cam2FpsToken = strtok(nullptr, " \t");
    char *extraToken = strtok(nullptr, " \t");
    handleConfigureCommand(
        cam1PinToken,
        cam1FpsToken,
        cam2PinToken,
        cam2FpsToken,
        extraToken);
    return;
  }

  reply.print(F("ERR Unknown command: "));
  reply.println(command);
}

void pollSerial() {
  for (uint8_t count = 0; count < 16U && Serial.available() > 0; count++) {
    const char incoming = (char)Serial.read();
    if (incoming == '\r') {
      continue;
    }
    if (incoming != '\n') {
      if (discardCommand || !isSerialCommandByte(incoming)) {
        continue;
      }
      if (commandLength + 1U >= sizeof(commandBuffer)) {
        discardCommand = true;
        continue;
      }
      commandBuffer[commandLength++] = incoming;
      continue;
    }

    if (discardCommand) {
      discardCommand = false;
      commandLength = 0U;
      reply.println(F("ERR Command too long"));
      return;
    }
    commandBuffer[commandLength] = '\0';
    commandLength = 0U;
    size_t trimmedLength = strlen(commandBuffer);
    while (trimmedLength > 0U &&
           (commandBuffer[trimmedLength - 1U] == ' ' ||
            commandBuffer[trimmedLength - 1U] == '\t')) {
      commandBuffer[trimmedLength - 1U] = '\0';
      trimmedLength--;
    }
    char *trimmedLine = commandBuffer;
    while (*trimmedLine == ' ' || *trimmedLine == '\t') {
      trimmedLine++;
    }
    trimmedLine = findCommandStart(trimmedLine);
    if (*trimmedLine == '\0') {
      continue;
    }
    handleCommand(trimmedLine);
    return;
  }
}

void serviceTiming() {
  pollProjectorSyncInput();
  processProjectorSync();
  updateLearnedClockTriggers();
  updateCameraOutputs();
}

}  // namespace

void setup() {
  pinMode(kSyncInputPin, INPUT);
  pinMode(kPlotPin, INPUT);
  for (uint8_t index = 0; index < 2U; index++) {
    if (cameras[index].active) {
      pinMode(cameras[index].pin, OUTPUT);
      driveCameraLow(cameras[index]);
    }
  }
  pinMode(kDefaultGatePin, OUTPUT);
  digitalWrite(kDefaultGatePin, LOW);
  nextPlotAtUs = micros();
  Serial.begin(115200);
  while (!Serial && millis() < 2000UL) {
    delay(10);
  }
  startSyncMonitor();
  reply.println(F("OK READY dual_camera_projector_sync"));
}

void loop() {
  serviceTiming();
  pollSerial();
  updatePin2Plotter();
}
