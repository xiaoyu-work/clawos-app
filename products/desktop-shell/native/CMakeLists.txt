cmake_minimum_required(VERSION 3.25)
project(claw-desktop-shell LANGUAGES NONE)

include(ExternalProject)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Native build type" FORCE)
endif()

set(GIT_REVISION "source" CACHE STRING "Desktop Shell source revision")
set(shapes_payload "${CMAKE_CURRENT_BINARY_DIR}/payload-shapes")
set(presentation_payload "${CMAKE_CURRENT_BINARY_DIR}/payload-presentation")
set(qml_directory "share/claw-desktop-shell/qml")
set(common_args
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
