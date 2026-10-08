#pragma once
#include <stdint.h>

// A learned projector clock. uint32_t timestamp subtraction tolerates micros()
// rollover; Q16 periods retain sub-microsecond frequency estimates on AVR.
struct ProjectorClock {
  static constexpr uint32_t checkIntervalUs = 300000000UL;
  static constexpr uint32_t measurementIntervals = 120;
  bool locked = false;
  bool measuring = true;
  uint32_t periodQ16 = 0;
  uint32_t nextEdgeUs = 0, lastEdgeUs = 0, frame = 0, fraction = 0;
  uint32_t lastCheckUs = 0, checks = 0, skippedTicks = 0;
  int32_t phaseErrorUs = 0, remainingCorrectionUs = 0;
  uint32_t seenCount = 0, previousInputUs = 0, firstInputUs = 0;
  uint32_t intervals = 0;

  void observe(uint32_t count, uint32_t edgeUs) {
    if (count == seenCount) return;
    const uint32_t countStep = count - seenCount;
    const uint32_t gap = edgeUs - previousInputUs;
    const bool first = seenCount == 0;
    seenCount = count;
    previousInputUs = edgeUs;
    if (!measuring && uint32_t(edgeUs - lastCheckUs) >= checkIntervalUs) {
      measuring = true;
      intervals = 0;
      firstInputUs = edgeUs;
      return;
    }
    if (!measuring) return;
    // Require a contiguous, approximately 60 Hz measurement window. Missed
    // edges or unstable sync restart it rather than accepting a broken window.
    if (first || countStep != 1 || gap < 15000 || gap > 18500) {
      intervals = 0;
      firstInputUs = edgeUs;
      return;
    }
    if (++intervals < measurementIntervals) return;
    if (!locked) {
      // Learn frequency only once. Later windows measure phase exclusively.
      periodQ16 = uint32_t((uint64_t(uint32_t(edgeUs - firstInputUs)) << 16) /
                           measurementIntervals);
      nextEdgeUs = lastEdgeUs = edgeUs;
      frame = fraction = 0;
      locked = true;
    } else {
      // Use the fixed initial frequency to compare the captured edge with the
      // nearest edge of our oscillator. Identical pulses carry phase modulo one
      // projector period, not an absolute frame identity after a long dropout.
      const int32_t periodUs = int32_t((periodQ16 + 32768UL) >> 16);
      int32_t error = int32_t(edgeUs - lastEdgeUs) % periodUs;
      if (error > periodUs / 2) error -= periodUs;
      if (error < -periodUs / 2) error += periodUs;
      phaseErrorUs = error;
      remainingCorrectionUs = error > 50 || error < -50 ? error : 0;
    }
    lastCheckUs = edgeUs;
    checks++;
    measuring = false;
  }

  bool tick(uint32_t nowUs, uint32_t &edgeUs, uint32_t &frameIndex) {
    if (!locked || int32_t(nowUs - nextEdgeUs) < 0) return false;
    // Skip overdue oscillator cycles in constant time; never burst-fire them.
    const uint32_t skipped = uint32_t((uint64_t(uint32_t(nowUs - nextEdgeUs)) << 16) /
                                      periodQ16);
    if (skipped) {
      const uint64_t advance = uint64_t(skipped) * periodQ16 + fraction;
      nextEdgeUs += uint32_t(advance >> 16);
      fraction = uint32_t(advance & 65535);
      frame += skipped;
      skippedTicks += skipped;
    }
    edgeUs = lastEdgeUs = nextEdgeUs;
    frameIndex = frame++;

    // Rechecks never move an already scheduled edge or change the learned
    // period. Temporarily adjust intervals by up to 3 us to remove phase error, then
    // resume exactly the original period (including its fractional remainder).
    const int32_t correction = remainingCorrectionUs > 3 ? 3 :
                              remainingCorrectionUs < -3 ? -3 : remainingCorrectionUs;
    remainingCorrectionUs -= correction;
    const uint32_t step = uint32_t(int32_t(periodQ16) + correction * 65536) + fraction;
    nextEdgeUs += step >> 16;
    fraction = step & 65535;
    return true;
  }
};
