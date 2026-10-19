#include <cassert>
#include <string>
#include <vector>
#include "../../../firmware/uno/cephvr2_mcu/cephvr2_mcu.ino"

std::string send(const std::string &request) {
  std::vector<char> buffer(request.begin(), request.end());
  buffer.push_back('\0');
  Serial.reply.clear();
  command(buffer.data());
  return Serial.reply;
}

std::string configure(const std::string &tracking, const std::string &eye = "eye_tracking_enabled=0",
                      const std::string &behavior = "behavioral_enabled=1 behavioral_pin=D10 behavioral_hz=30.0") {
  return send("CONFIGURE id=cfg watchdog_ms=3000 " + behavior + " " + tracking + " " + eye);
}

void unchanged(const Output &before, uint8_t role) {
  const Output &after = outputs[role];
  assert(after.phase == before.phase && after.high == before.high);
  assert(after.running == before.running && after.step == before.step);
  assert(after.pin == before.pin && after.enabled == before.enabled);
  assert(after.requestedHz == before.requestedHz && after.appliedHz == before.appliedHz);
  for (const auto &write : writes) assert(write.first != before.pin);
}

int main() {
  setup();
  assert(send("CAPS id=caps").find("protocol=5") != std::string::npos);
  assert(configure("tracking_enabled=0").find("OK") == 0);
  assert(send("ON id=on behavioral_selected=1 tracking_selected=0 eye_tracking_selected=0").find("OK") == 0);
  // Cover joining during both halves of the existing pulse.
  for (bool high : {true, false}) {
    while (outputs[0].high != high) TIMER1_COMPA_vect();
    for (int tick = 0; tick < 7; ++tick) TIMER1_COMPA_vect();
    const Output before = outputs[0];
    writes.clear();
    const auto reply = configure("tracking_enabled=1 tracking_pin=D11 tracking_hz=60.0");
    assert(reply.find("behavioral_running=1") != std::string::npos);
    unchanged(before, 0);
    assert(outputs[1].enabled && !outputs[1].running);
    TIMER1_COMPA_vect();
    assert(outputs[0].phase == uint32_t(before.phase + before.step));
  }
  const Output beforeOn = outputs[0];
  writes.clear();
  assert(send("ON id=on2 behavioral_selected=0 tracking_selected=1 eye_tracking_selected=0").find("OK") == 0);
  unchanged(beforeOn, 0);
  for (int tick = 0; tick < 41; ++tick) TIMER1_COMPA_vect();
  const Output behavior = outputs[0], tracking = outputs[1];
  writes.clear();
  assert(configure("tracking_enabled=1 tracking_pin=D11 tracking_hz=60.0",
    "eye_tracking_enabled=1 eye_tracking_pin=D8 eye_tracking_hz=45.0").find("OK") == 0);
  unchanged(behavior, 0); unchanged(tracking, 1);
  assert(outputs[2].enabled && !outputs[2].running);

  // Rejected combined pin assignments leave every existing output untouched.
  writes.clear();
  assert(configure("tracking_enabled=1 tracking_pin=D10 tracking_hz=60.0").find("code=TIMER_CONFLICT") != std::string::npos);
  unchanged(behavior, 0); unchanged(tracking, 1);
  assert(writes.empty() && outputs[2].enabled);
  assert(configure("tracking_enabled=1 tracking_pin=D11 tracking_hz=0.0").find("ERR") == 0);
  unchanged(behavior, 0); unchanged(tracking, 1);
  assert(writes.empty());
  // Oversized reply rejection also precedes any application.
  const std::string longId(280, 'x');
  const auto boundedRequest = "CONFIGURE id=" + longId +
    " watchdog_ms=3000 behavioral_enabled=1 behavioral_pin=D10 behavioral_hz=30.0"
    " tracking_enabled=1 tracking_pin=D11 tracking_hz=60.0"
    " eye_tracking_enabled=1 eye_tracking_pin=D8 eye_tracking_hz=45.0";
  assert(boundedRequest.size() + 1 <= kLineLimit);
  assert(send(boundedRequest).find("REPLY_TOO_LONG") != std::string::npos);
  unchanged(behavior, 0); unchanged(tracking, 1);

  // Changing a rate still restarts only that changed running output.
  writes.clear();
  assert(configure("tracking_enabled=1 tracking_pin=D11 tracking_hz=50.0").find("OK") == 0);
  unchanged(behavior, 0);
  assert(outputs[1].running && outputs[1].phase == 0 && outputs[1].high);
  // Pin swaps release all old assignments before driving any new pin HIGH.
  writes.clear();
  assert(configure("tracking_enabled=1 tracking_pin=D10 tracking_hz=50.0", "eye_tracking_enabled=0",
    "behavioral_enabled=1 behavioral_pin=D11 behavioral_hz=30.0").find("OK") == 0);
  assert(writes.size() >= 4 && writes[0] == std::make_pair(uint8_t(10), LOW));
  assert(writes[1] == std::make_pair(uint8_t(11), LOW));

  testMillis = lastRequestMs + watchdogMs;
  loop();
  assert(watchdogStopped);
  for (const auto &out : outputs) assert(!out.running && !out.high);
  writes.clear();
  for (int tick = 0; tick < 1000; ++tick) TIMER1_COMPA_vect();
  assert(writes.empty());
}
