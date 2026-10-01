cmake_minimum_required(VERSION 3.24)
project(cephvr_atomics LANGUAGES CXX)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "CephVR shared-ring atomics require 64-bit Windows")
endif()

add_library(cephvr_atomics SHARED atomics.cpp)
target_compile_features(cephvr_atomics PRIVATE cxx_std_17)
install(TARGETS cephvr_atomics RUNTIME DESTINATION cephvr/platform/windows)
