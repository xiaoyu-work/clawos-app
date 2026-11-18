cmake_minimum_required(VERSION 3.25)
project(claw-desktop-shell LANGUAGES NONE)

include(ExternalProject)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Native build type" FORCE)
endif()

set(GIT_REVISION "source" CACHE STRING "Desktop Shell source revision")
set(CLAW_QT_CACHE "${CMAKE_CURRENT_BINARY_DIR}/qt-cache" CACHE PATH "Native Qt source/build cache")
set(CLAW_QT_JOBS "2" CACHE STRING "Qt build jobs")
set(qt_prefix_file "${CMAKE_CURRENT_BINARY_DIR}/qt-prefix")
set(qt_builder "${CMAKE_CURRENT_SOURCE_DIR}/build-qt.py")
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${qt_builder}" build "${CLAW_QT_CACHE}" "${CLAW_QT_JOBS}"
        --prefix-file "${qt_prefix_file}"
    COMMAND_ERROR_IS_FATAL ANY
)
file(READ "${qt_prefix_file}" qt_prefix)
set(shapes_payload "${CMAKE_CURRENT_BINARY_DIR}/payload-shapes")
set(presentation_payload "${CMAKE_CURRENT_BINARY_DIR}/payload-presentation")
set(qml_directory "share/claw-desktop-shell/qml")
set(common_args
    "-DQt6_DIR=${qt_prefix}/lib/cmake/Qt6"
    "-DCMAKE_PREFIX_PATH=${qt_prefix}"
    "-DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}"
    "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON"
    "-DCMAKE_INSTALL_RPATH=$ORIGIN"
    "-DCMAKE_INSTALL_RPATH_USE_LINK_PATH=OFF"
    "-DCMAKE_INSTALL_SO_NO_EXE=ON"
)

ExternalProject_Add(desktop-shapes
    SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/m3shapes"
    BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/m3shapes"
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    CMAKE_ARGS ${common_args}
        "-DCMAKE_INSTALL_PREFIX=${shapes_payload}/usr"
        "-DINSTALL_QMLDIR=${qml_directory}"
        -DM3SHAPES_BUILD_EXAMPLES=OFF
    BUILD_COMMAND "${CMAKE_COMMAND}" --build <BINARY_DIR> --parallel 2
    BUILD_ALWAYS ON
    INSTALL_COMMAND "${CMAKE_COMMAND}" -E rm -rf "${shapes_payload}"
        COMMAND "${CMAKE_COMMAND}" --install <BINARY_DIR>
)

ExternalProject_Add(desktop-presentation
    SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/caelestia"
    BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/caelestia"
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    LIST_SEPARATOR |
    CMAKE_ARGS ${common_args}
        "-DCMAKE_INSTALL_PREFIX=${presentation_payload}/usr"
        -DVERSION=1.0.0
        "-DGIT_REVISION=${GIT_REVISION}"
        -DDISTRIBUTOR=Claw
        "-DENABLE_MODULES=plugin|shell"
        "-DINSTALL_QMLDIR=${qml_directory}"
        -DINSTALL_QSCONFDIR=share/claw-desktop-shell
    BUILD_COMMAND "${CMAKE_COMMAND}" --build <BINARY_DIR> --parallel 2
    BUILD_ALWAYS ON
    INSTALL_COMMAND "${CMAKE_COMMAND}" -E rm -rf "${presentation_payload}"
        COMMAND "${CMAKE_COMMAND}" --install <BINARY_DIR>
)

ExternalProject_Add(desktop-engine
    SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/quickshell"
    BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/quickshell"
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    CMAKE_ARGS ${common_args}
        -DCMAKE_INSTALL_PREFIX=/usr
        -DDISTRIBUTOR=Claw
        -DX11=OFF
        -DI3=OFF
        -DHYPRLAND_IPC=OFF
        -DSERVICE_POLKIT=OFF
        -DBUILD_TESTING=OFF
        -DVENDOR_CPPTRACE=ON
        -DCPPTRACE_USE_EXTERNAL_ZSTD=ON
    BUILD_COMMAND "${CMAKE_COMMAND}" --build <BINARY_DIR> --parallel 2 --target quickshell
    BUILD_BYPRODUCTS "${CMAKE_CURRENT_BINARY_DIR}/quickshell/src/quickshell"
    BUILD_ALWAYS ON
    INSTALL_COMMAND ""
)

install(PROGRAMS "${CMAKE_CURRENT_BINARY_DIR}/quickshell/src/quickshell"
    DESTINATION bin RENAME claw-desktop-shell)
install(DIRECTORY "${shapes_payload}/usr/share/" DESTINATION share USE_SOURCE_PERMISSIONS)
install(DIRECTORY "${presentation_payload}/usr/share/" DESTINATION share USE_SOURCE_PERMISSIONS)

set(license_directory "share/claw-desktop-shell/licenses")
install(FILES quickshell/LICENSE quickshell/LICENSE-GPL DESTINATION "${license_directory}/quickshell")
install(FILES m3shapes/LICENSE DESTINATION "${license_directory}/material-shapes")
install(FILES caelestia/plugin/3rdparty/libcava/LICENSE DESTINATION "${license_directory}/libcava")
install(FILES caelestia/plugin/3rdparty/rgbcx/LICENSE DESTINATION "${license_directory}/rgbcx")
install(CODE "
    if(NOT IS_ABSOLUTE \"\$ENV{DESTDIR}\" OR \"\$ENV{DESTDIR}\" STREQUAL \"/\")
        message(FATAL_ERROR \"Desktop Shell requires a private absolute DESTDIR\")
    endif()
    execute_process(COMMAND \"${Python3_EXECUTABLE}\" \"${qt_builder}\" stage
        \"${qt_prefix}\" \"\$ENV{DESTDIR}\"
        COMMAND_ERROR_IS_FATAL ANY)
")
