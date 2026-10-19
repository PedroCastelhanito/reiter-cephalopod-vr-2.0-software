// Minimal native adapter for executing the actual Uno sketch's command/ISR logic.
#pragma once
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

struct __FlashStringHelper;
#define F(value) reinterpret_cast<const __FlashStringHelper *>(value)
constexpr int LOW = 0, HIGH = 1, INPUT = 0, OUTPUT = 1;
inline uint32_t testMillis = 0;
inline std::vector<std::pair<uint8_t, int>> writes;
inline uint8_t TCCR1A, TCCR1B, TIMSK1;
inline uint16_t TCNT1, OCR1A;
constexpr int WGM12 = 3, CS11 = 1, OCIE1A = 1;
#define _BV(bit) (1 << (bit))
inline void noInterrupts() {}
inline void interrupts() {}
inline void pinMode(uint8_t, int) {}
inline void digitalWrite(uint8_t pin, int value) { writes.emplace_back(pin, value); }
inline uint32_t millis() { return testMillis; }

class Print {
 public:
  virtual ~Print() = default;
  virtual size_t write(uint8_t) = 0;
  void print(const char *value) { while (*value) write(uint8_t(*value++)); }
  void print(const __FlashStringHelper *value) { print(reinterpret_cast<const char *>(value)); }
  void print(char value) { write(uint8_t(value)); }
  void print(uint8_t value) { print(unsigned(value)); }
  template <typename T> void print(T value) {
    std::ostringstream out; out << value; print(out.str().c_str());
  }
  void print(float value, int precision) {
    std::ostringstream out; out << std::fixed << std::setprecision(precision) << value;
    print(out.str().c_str());
  }
  void println() { print("\r\n"); }
  template <typename T> void println(T value) { print(value); println(); }
};

class TestSerial : public Print {
 public:
  std::string reply;
  size_t write(uint8_t value) override { reply += char(value); return 1; }
  void begin(int) {}
  int available() { return 0; }
  int read() { return -1; }
};
inline TestSerial Serial;
