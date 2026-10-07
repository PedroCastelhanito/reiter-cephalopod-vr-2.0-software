#include <Arduino.h>
#include <avr/interrupt.h>
#include <stdlib.h>
#include <string.h>

// A11 protocol v3 for the COM8 Arduino Uno. Installation is manual.
// Timer1 owns camera edges; serial parsing and diagnostics stay in loop().
namespace {

constexpr uint32_t kTickHz = 10000;
constexpr uint16_t kTickTop = 199;  // 16 MHz / 8 / (199 + 1) = 10 kHz.
constexpr size_t kLineLimit = 512;
constexpr uint16_t kDiagnosticMs = 2000;

struct Output {
  uint8_t pin;
  uint32_t step;
  volatile uint32_t phase;
  volatile bool running;
  volatile bool high;
  bool enabled;
  float requestedHz;
  float appliedHz;
};

Output outputs[2] = {{0, 0, 0, false, false, false, 0, 0},
                     {0, 0, 0, false, false, false, 0, 0}};
char line[kLineLimit];
size_t lineLength = 0;
bool discarding = false;
bool trailingCr = false;
bool configured = false;
bool watchdogStopped = false;
uint32_t watchdogMs = 0;
uint32_t lastRequestMs = 0;
volatile bool diagnosticActive = false;
char diagnosticKind[20] = "";
volatile uint8_t diagnosticPin = 0;
uint32_t diagnosticStartMs = 0;
volatile uint32_t diagnosticEdges = 0;

void countDiagnosticRise() {
  if (diagnosticEdges != UINT32_MAX) ++diagnosticEdges;
}

ISR(TIMER1_COMPA_vect) {
  for (uint8_t i = 0; i < 2; ++i) {
    Output &out = outputs[i];
    if (!out.running) continue;
    out.phase += out.step;
    const bool high = out.phase < 0x80000000UL;
    if (high != out.high) {
      out.high = high;
      digitalWrite(out.pin, high ? HIGH : LOW);
      if (high && diagnosticActive && diagnosticPin == out.pin)
        countDiagnosticRise();
    }
  }
}

void stopOutput(uint8_t i) {
  noInterrupts();
  outputs[i].running = false;
  outputs[i].high = false;
  interrupts();
  if (outputs[i].pin) digitalWrite(outputs[i].pin, LOW);
}

void startOutput(uint8_t i) {
  noInterrupts();
  outputs[i].phase = 0;
  outputs[i].high = true;
  digitalWrite(outputs[i].pin, HIGH);
  if (diagnosticActive && diagnosticPin == outputs[i].pin)
    countDiagnosticRise();
  outputs[i].running = true;
  interrupts();
}

void stopDiagnostic() {
  if (!diagnosticActive) return;
  if (strcmp(diagnosticKind, "behavioral") == 0) stopOutput(0);
  if (strcmp(diagnosticKind, "tracking") == 0) stopOutput(1);
  if (strcmp(diagnosticKind, "trial_state") == 0) digitalWrite(diagnosticPin, LOW);
  if (strcmp(diagnosticKind, "projector_flip") == 0)
    detachInterrupt(digitalPinToInterrupt(diagnosticPin));
  diagnosticActive = false;
}

void serviceDiagnostic() {
  if (!diagnosticActive) return;
  if (uint32_t(millis() - diagnosticStartMs) >= kDiagnosticMs) stopDiagnostic();
}

void stopAll() {
  stopOutput(0);
  stopOutput(1);
  stopDiagnostic();
}

bool parsePin(const char *text, uint8_t &pin) {
  if (!text || text[0] != 'D') return false;
  const size_t length = strlen(text);
  if (length != 2 && length != 3) return false;
  if (text[1] < '0' || text[1] > '9') return false;
  if (length == 3 && (text[2] < '0' || text[2] > '9')) return false;
  const unsigned value = unsigned(text[1] - '0') * (length == 3 ? 10 : 1) +
                         (length == 3 ? unsigned(text[2] - '0') : 0);
  if (value < 2 || value > 13 || (length == 3 && value < 10)) return false;
  pin = uint8_t(value);
  return true;
}

bool parseUnsigned(const char *text, uint32_t &value) {
  if (!text || !*text) return false;
  for (const char *p = text; *p; ++p) if (*p < '0' || *p > '9') return false;
  const unsigned long parsed = strtoul(text, nullptr, 10);
  value = uint32_t(parsed);
  return true;
}

bool parseRate(const char *text, float &rate, uint32_t &step) {
  if (!text || !*text) return false;
  uint16_t whole = 0;
  const char *cursor = text;
  while (*cursor >= '0' && *cursor <= '9') {
    whole = whole * 10 + uint16_t(*cursor - '0');
    if (whole > 100) return false;
    ++cursor;
  }
  if (*cursor++ != '.' || *cursor < '0' || *cursor > '9' || cursor[1]) return false;
  const uint16_t tenths = whole * 10 + uint16_t(*cursor - '0');
  if (tenths == 0 || tenths > 1000) return false;
  rate = float(tenths) / 10.0f;
  step = uint32_t(double(tenths) * (4294967296.0 / (kTickHz * 10.0)) + 0.5);
  return step != 0;
}

const char *field(char *const *keys, char *const *values, uint8_t count,
                  const char *name) {
  for (uint8_t i = 0; i < count; ++i)
    if (strcmp(keys[i], name) == 0) return values[i];
  return nullptr;
}

void error(const char *id, const __FlashStringHelper *code) {
  Serial.print(F("ERR"));
  if (id) { Serial.print(F(" id=")); Serial.print(id); }
  Serial.print(F(" code=")); Serial.println(code);
}

void prefix(const char *id) { Serial.print(F("OK id=")); Serial.print(id); }

void compact(const char *id) {
  prefix(id);
  Serial.print(F(" behavioral_running=")); Serial.print(outputs[0].running ? 1 : 0);
  Serial.print(F(" tracking_running=")); Serial.print(outputs[1].running ? 1 : 0);
  Serial.print(F(" watchdog_stopped=")); Serial.println(watchdogStopped ? 1 : 0);
}

void status(const char *id) {
  prefix(id);
  Serial.print(F(" valid=")); Serial.print(configured ? 1 : 0);
  Serial.print(F(" watchdog_stopped=")); Serial.print(watchdogStopped ? 1 : 0);
  Serial.print(F(" watchdog_ms=")); Serial.print(configured ? watchdogMs : 0);
  for (uint8_t i = 0; i < 2; ++i) {
    Serial.print(i ? F(" tracking_enabled=") : F(" behavioral_enabled="));
    Serial.print(outputs[i].enabled ? 1 : 0);
    Serial.print(i ? F(" tracking_running=") : F(" behavioral_running="));
    Serial.print(outputs[i].running ? 1 : 0);
    if (outputs[i].enabled) {
      Serial.print(i ? F(" tracking_pin=D") : F(" behavioral_pin=D"));
      Serial.print(outputs[i].pin);
      Serial.print(i ? F(" tracking_applied_hz=") : F(" behavioral_applied_hz="));
      Serial.print(outputs[i].appliedHz, 9);
    }
  }
  Serial.println();
}

void diagnosticReply(const char *id) {
  noInterrupts();
  const uint32_t edges = diagnosticEdges;
  interrupts();
  prefix(id);
  Serial.print(F(" active=")); Serial.print(diagnosticActive ? 1 : 0);
  Serial.print(F(" kind=")); Serial.print(diagnosticKind);
  Serial.print(F(" pin=D")); Serial.print(diagnosticPin);
  Serial.print(F(" edges=")); Serial.println(edges);
}

bool knownFields(char *const *keys, uint8_t count, const char *const *allowed,
                 uint8_t allowedCount) {
  for (uint8_t i = 0; i < count; ++i) {
    bool known = false;
    for (uint8_t j = 0; j < allowedCount; ++j)
      if (strcmp(keys[i], allowed[j]) == 0) known = true;
    if (!known) return false;
  }
  return true;
}

void command(char *buffer) {
  char *verb = strtok(buffer, " ");
  char *keys[16], *values[16];
  uint8_t count = 0;
  if (!verb) return;
  for (char *token = strtok(nullptr, " "); token; token = strtok(nullptr, " ")) {
    if (count == 16) { error(nullptr, F("BAD_VALUE")); return; }
    char *equals = strchr(token, '=');
    if (!equals || equals == token || !equals[1]) { error(nullptr, F("BAD_VALUE")); return; }
    *equals = '\0';
    for (uint8_t i = 0; i < count; ++i)
      if (strcmp(keys[i], token) == 0) { error(nullptr, F("DUPLICATE_FIELD")); return; }
    keys[count] = token; values[count] = equals + 1; ++count;
  }
  const char *id = field(keys, values, count, "id");
  if (!id) { error(nullptr, F("MISSING_FIELD")); return; }
  if (strlen(id) > 240) { error(nullptr, F("REPLY_TOO_LONG")); return; }
  if (strcmp(verb, "CAPS") == 0) {
    const char *allowed[] = {"id"};
    if (!knownFields(keys, count, allowed, 1)) { error(id, F("UNKNOWN_FIELD")); return; }
    lastRequestMs = millis(); prefix(id);
    Serial.println(F(" protocol=3 firmware=cephvr2_uno_2 pins=D2,D3,D4,D5,D6,D7,D8,D9,D10,D11,D12,D13 input_pins=D2,D3 min_hz=0.1 max_hz=100.0 watchdog_min_ms=500 watchdog_max_ms=10000"));
    return;
  }
  if (strcmp(verb, "STATUS") == 0 || strcmp(verb, "PING") == 0) {
    const char *allowed[] = {"id"};
    if (!knownFields(keys, count, allowed, 1)) { error(id, F("UNKNOWN_FIELD")); return; }
    lastRequestMs = millis();
    if (strcmp(verb, "STATUS") == 0) status(id); else compact(id);
    return;
  }
  if (strcmp(verb, "CONFIGURE") == 0) {
    const char *allowed[] = {"id", "watchdog_ms", "behavioral_enabled",
      "behavioral_pin", "behavioral_hz", "tracking_enabled", "tracking_pin",
      "tracking_hz"};
    if (!knownFields(keys, count, allowed, 8) || diagnosticActive) {
      error(id, F("UNKNOWN_FIELD")); return;
    }
    const char *watchdog = field(keys, values, count, "watchdog_ms");
    uint32_t requestedWatchdog = 0;
    if (!parseUnsigned(watchdog, requestedWatchdog) ||
        requestedWatchdog < 500 || requestedWatchdog > 10000) {
      error(id, F("INVALID_WATCHDOG")); return;
    }
    uint8_t requestedPin[2] = {0, 0};
    uint32_t requestedStep[2] = {0, 0};
    float requestedRate[2] = {0, 0};
    bool requestedEnabled[2] = {false, false};
    for (uint8_t i = 0; i < 2; ++i) {
      const char *enabledName = i ? "tracking_enabled" : "behavioral_enabled";
      const char *pinName = i ? "tracking_pin" : "behavioral_pin";
      const char *rateName = i ? "tracking_hz" : "behavioral_hz";
      const char *enabled = field(keys, values, count, enabledName);
      const char *pinText = field(keys, values, count, pinName);
      const char *rateText = field(keys, values, count, rateName);
      if (!enabled || (strcmp(enabled, "0") && strcmp(enabled, "1"))) {
        error(id, F("BAD_VALUE")); return;
      }
      requestedEnabled[i] = strcmp(enabled, "1") == 0;
      if (requestedEnabled[i]) {
        if (!parsePin(pinText, requestedPin[i]) ||
            !parseRate(rateText, requestedRate[i], requestedStep[i])) {
          error(id, F("INVALID_PIN")); return;
        }
      } else if (pinText || rateText) { error(id, F("BAD_VALUE")); return; }
    }
    if (requestedEnabled[0] && requestedEnabled[1] &&
        requestedPin[0] == requestedPin[1]) { error(id, F("TIMER_CONFLICT")); return; }
    const bool resume[2] = {outputs[0].running && requestedEnabled[0],
                            outputs[1].running && requestedEnabled[1]};
    stopAll();
    for (uint8_t i = 0; i < 2; ++i) {
      outputs[i].enabled = requestedEnabled[i];
      outputs[i].pin = requestedPin[i];
      outputs[i].step = requestedStep[i];
      outputs[i].requestedHz = requestedRate[i];
      outputs[i].appliedHz = float(double(requestedStep[i]) * kTickHz / 4294967296.0);
      if (requestedEnabled[i]) {
        pinMode(requestedPin[i], OUTPUT);
        digitalWrite(requestedPin[i], LOW);
      }
    }
    watchdogMs = requestedWatchdog; configured = true; watchdogStopped = false;
    lastRequestMs = millis();
    for (uint8_t i = 0; i < 2; ++i) if (resume[i]) startOutput(i);
    status(id); return;
  }
  if (strcmp(verb, "DIAG_STATUS") == 0 || strcmp(verb, "DIAG_STOP") == 0) {
    const char *allowed[] = {"id"};
    if (!knownFields(keys, count, allowed, 1)) { error(id, F("UNKNOWN_FIELD")); return; }
    if (!*diagnosticKind) { error(id, F("NOT_CONFIGURED")); return; }
    lastRequestMs = millis();
    if (strcmp(verb, "DIAG_STOP") == 0) stopDiagnostic();
    else serviceDiagnostic();
    diagnosticReply(id);
    return;
  }
  if (strcmp(verb, "DIAG_START") == 0) {
    const char *allowed[] = {"id", "kind", "pin", "duration_ms", "hz"};
    if (!knownFields(keys, count, allowed, 5)) {
      error(id, F("UNKNOWN_FIELD")); return;
    }
    const char *kind = field(keys, values, count, "kind");
    const char *pinText = field(keys, values, count, "pin");
    const char *duration = field(keys, values, count, "duration_ms");
    const char *hz = field(keys, values, count, "hz");
    uint8_t pin = 0;
    if (!kind || !parsePin(pinText, pin) || !duration || strcmp(duration, "2000") ||
        diagnosticActive || outputs[0].running || outputs[1].running) {
      error(id, F("BAD_VALUE")); return;
    }
    const int role = strcmp(kind, "behavioral") == 0 ? 0 :
                     strcmp(kind, "tracking") == 0 ? 1 : -1;
    float rate = 0; uint32_t step = 0;
    if ((role >= 0 && !parseRate(hz, rate, step)) || (role < 0 && hz)) {
      error(id, F("BAD_VALUE")); return;
    }
    if (role >= 0 && (!configured || !outputs[role].enabled ||
        outputs[role].pin != pin)) { error(id, F("NOT_CONFIGURED")); return; }
    if (role >= 0 && rate != outputs[role].requestedHz) {
      error(id, F("BAD_VALUE")); return;
    }
    if (role < 0 && strcmp(kind, "trial_state") && strcmp(kind, "projector_flip")) {
      error(id, F("BAD_VALUE")); return;
    }
    if (strcmp(kind, "projector_flip") == 0 && pin != 2 && pin != 3) {
      error(id, F("INVALID_PIN")); return;
    }
    for (uint8_t i = 0; i < 2; ++i)
      if (outputs[i].enabled && outputs[i].pin == pin && role != i) {
        error(id, F("INVALID_PIN")); return;
      }
    strncpy(diagnosticKind, kind, sizeof(diagnosticKind) - 1);
    diagnosticKind[sizeof(diagnosticKind) - 1] = '\0';
    diagnosticPin = pin;
    noInterrupts(); diagnosticEdges = 0; diagnosticActive = true; interrupts();
    diagnosticStartMs = millis();
    pinMode(pin, role >= 0 || strcmp(kind, "trial_state") == 0 ? OUTPUT : INPUT);
    if (role >= 0 || strcmp(kind, "trial_state") == 0) digitalWrite(pin, LOW);
    if (role >= 0) {
      startOutput(uint8_t(role));
    } else if (strcmp(kind, "trial_state") == 0) {
      noInterrupts();
      digitalWrite(pin, HIGH);
      countDiagnosticRise();
      interrupts();
    } else attachInterrupt(digitalPinToInterrupt(pin), countDiagnosticRise, RISING);
    lastRequestMs = millis();
    diagnosticReply(id);
    return;
  }
  if (strcmp(verb, "OFF") == 0) {
    const char *allowed[] = {"id", "behavioral_selected", "tracking_selected"};
    if (!knownFields(keys, count, allowed, 3)) { error(id, F("UNKNOWN_FIELD")); return; }
    const char *b = field(keys, values, count, "behavioral_selected");
    const char *t = field(keys, values, count, "tracking_selected");
    if (!b || !t || (strcmp(b, "0") && strcmp(b, "1")) ||
        (strcmp(t, "0") && strcmp(t, "1")) || (!strcmp(b, "0") && !strcmp(t, "0"))) {
      error(id, F("BAD_VALUE")); return;
    }
    if (!strcmp(b, "1")) stopOutput(0);
    if (!strcmp(t, "1")) stopOutput(1);
    lastRequestMs = millis(); compact(id); return;
  }
  if (strcmp(verb, "ON") == 0) {
    const char *allowed[] = {"id", "behavioral_selected", "tracking_selected"};
    if (!knownFields(keys, count, allowed, 3)) { error(id, F("UNKNOWN_FIELD")); return; }
    const char *b = field(keys, values, count, "behavioral_selected");
    const char *t = field(keys, values, count, "tracking_selected");
    if (!configured || watchdogStopped || diagnosticActive || !b || !t ||
        (strcmp(b, "0") && strcmp(b, "1")) ||
        (strcmp(t, "0") && strcmp(t, "1")) ||
        (!strcmp(b, "0") && !strcmp(t, "0")) ||
        (!strcmp(b, "1") && !outputs[0].enabled) ||
        (!strcmp(t, "1") && !outputs[1].enabled)) {
      error(id, F("NOT_CONFIGURED")); return;
    }
    if (!strcmp(b, "1") && outputs[0].enabled && !outputs[0].running) startOutput(0);
    if (!strcmp(t, "1") && outputs[1].enabled && !outputs[1].running) startOutput(1);
    lastRequestMs = millis(); compact(id); return;
  }
  error(id, F("BAD_COMMAND"));
}

}  // namespace

void setup() {
  Serial.begin(115200);
  for (uint8_t pin = 2; pin <= 13; ++pin) { pinMode(pin, OUTPUT); digitalWrite(pin, LOW); }
  TCCR1A = 0; TCCR1B = 0; TCNT1 = 0; OCR1A = kTickTop;
  TCCR1B = _BV(WGM12) | _BV(CS11);
  TIMSK1 = _BV(OCIE1A);
  lastRequestMs = millis();
}

void loop() {
  while (Serial.available()) {
    const char ch = char(Serial.read());
    if (ch == '\r') {
      if (trailingCr) discarding = true;
      trailingCr = true;
      continue;
    }
    if (trailingCr && ch != '\n') discarding = true;
    trailingCr = false;
    if (ch == '\n') {
      if (discarding) { error(nullptr, F("LINE_TOO_LONG")); discarding = false; }
      else { line[lineLength] = '\0'; command(line); }
      lineLength = 0;
    } else if (!discarding) {
      if (ch < 32 || ch > 126 || lineLength >= kLineLimit - 1) discarding = true;
      else line[lineLength++] = ch;
    }
  }
  serviceDiagnostic();
  if (configured && uint32_t(millis() - lastRequestMs) >= watchdogMs) {
    stopAll(); watchdogStopped = true;
  }
}
