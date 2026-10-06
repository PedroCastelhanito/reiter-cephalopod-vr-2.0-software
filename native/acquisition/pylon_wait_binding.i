%module(package="cephvr.acquisition.camera") pylon_wait_binding
%{
#include <cstdint>
#include <stdexcept>
#include <pylon/WaitObject.h>
%}
%import "wait_type.i"
%include <exception.i>
%exception {
    try { $action }
    catch (const std::exception& error) {
        SWIG_exception(SWIG_RuntimeError, error.what());
    }
}
%newobject from_handle;
%inline %{
Pylon::WaitObject* from_handle(unsigned long long handle) {
    if (!handle) throw std::invalid_argument("control event handle is null");
    // The SDK owns a duplicate; the worker retains its original Win32 event.
    return new Pylon::WaitObject(
        reinterpret_cast<HANDLE>(static_cast<uintptr_t>(handle)), true);
}
%}
