#include <intrin.h>
#include <windows.h>

extern "C" __declspec(dllexport) __int64 WINAPI
cephvr_atomic_compare_exchange_64(volatile __int64* destination,
                                 __int64 exchange,
                                 __int64 comparand) noexcept {
    return _InterlockedCompareExchange64(destination, exchange, comparand);
}
