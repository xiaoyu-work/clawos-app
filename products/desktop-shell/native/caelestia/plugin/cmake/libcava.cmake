enable_language(C)
pkg_check_modules(FFTW3 REQUIRED IMPORTED_TARGET fftw3)

set(libcava_source "${CMAKE_CURRENT_SOURCE_DIR}/3rdparty/libcava")
add_library(caelestia-cava STATIC "${libcava_source}/cavacore.c")
set_target_properties(caelestia-cava PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(caelestia-cava SYSTEM PUBLIC "${libcava_source}/include")
target_link_libraries(caelestia-cava PUBLIC PkgConfig::FFTW3 m)
