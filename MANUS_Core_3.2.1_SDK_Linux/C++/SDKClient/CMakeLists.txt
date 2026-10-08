cmake_minimum_required(VERSION 3.16)

# MANUS SDKClient - an interactive terminal client demonstrating the MANUS SDK.
# See README.md for the source layout and build instructions.
project(SDKClient LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- MANUS SDK (prebuilt) ----------------------------------------------------
# The SDK headers and binaries are taken from the platform SDK folders;
# override with -DMANUS_SDK_DIR=<dir> to use a different SDK drop.
if(WIN32)
	# A shipped source package bundles the Windows SDK drop inside this folder;
	# in the repo it lives in the sibling platform client. Probe for the DLL
	# (not just include/) so a Linux drop copied here by CI is never picked up.
	if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/ManusSDK/lib/ManusSDK.dll")
		set(MANUS_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/ManusSDK"
			CACHE PATH "Directory containing the MANUS SDK include/ and lib/ folders")
	else()
		set(MANUS_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../SDKClient_Windows/ManusSDK"
			CACHE PATH "Directory containing the MANUS SDK include/ and lib/ folders")
	endif()
else()
	# Self-contained (not a sibling folder): a Linux remote-build sync copies
	# only this project's own directory tree, so the SDK headers/libs must
	# live inside it rather than in ../SDKClient_Linux.
	set(MANUS_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/ManusSDK"
		CACHE PATH "Directory containing the MANUS SDK include/ and lib/ folders")
endif()

add_library(ManusSDK SHARED IMPORTED)
if(WIN32)
	set_target_properties(ManusSDK PROPERTIES
		IMPORTED_LOCATION "${MANUS_SDK_DIR}/lib/ManusSDK.dll"
		IMPORTED_IMPLIB   "${MANUS_SDK_DIR}/lib/ManusSDK.lib")
else()
	# Pick the SDK library for the target architecture:
	# lib/<arch>/libManusSDK-<arch>.so. The per-arch variants are
	# self-contained (protobuf/gRPC/ZeroMQ linked in); the bare
	# lib/libManusSDK.so has undefined externals and does not link.
	# libManusSDK-integrated-<arch>.so is the integrated variant (later option).
	if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
		set(MANUS_SDK_ARCH "aarch64")
	else()
		set(MANUS_SDK_ARCH "amd64")
	endif()
	set(MANUS_SDK_LIBRARY "${MANUS_SDK_DIR}/lib/${MANUS_SDK_ARCH}/libManusSDK-${MANUS_SDK_ARCH}.so")
	if(NOT EXISTS "${MANUS_SDK_LIBRARY}")
		message(FATAL_ERROR "No MANUS SDK library for ${MANUS_SDK_ARCH} at ${MANUS_SDK_LIBRARY} - "
			"this SDK drop does not include ${MANUS_SDK_ARCH} binaries.")
	endif()
	set_target_properties(ManusSDK PROPERTIES IMPORTED_LOCATION "${MANUS_SDK_LIBRARY}")
	find_package(Threads REQUIRED)
endif()
target_include_directories(ManusSDK INTERFACE "${MANUS_SDK_DIR}/include")

# --- FTXUI (vendored at v6.1.9) -----------------------------------------------
# To update: replace third_party/ftxui with a fresh release checkout (delete
# .git/.github) and record the new tag here and in the README.
set(FTXUI_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(FTXUI_BUILD_DOCS     OFF CACHE BOOL "" FORCE)
set(FTXUI_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
add_subdirectory(third_party/ftxui)

# --- Application --------------------------------------------------------------
# Source layering (enforced by cmake/CheckLayers.cmake):
#   sdk/  - SDK feature modules, UI-free, copy-pasteable. The files to read to
#           learn how to use the MANUS SDK.
#   ui/   - FTXUI screens and components; call into sdk/, never CoreSdk_ directly.
#   app/  - application shell (navigation, startup flow).
add_executable(SDKClient
	app/Main.cpp
	app/App.cpp
	app/SelfTests.cpp
	sdk/Calibration.cpp
	sdk/Connection.cpp
	sdk/Devices.cpp
	sdk/ErrorCodes.cpp
	sdk/Firmware.cpp
	sdk/LandscapeCache.cpp
	sdk/License.cpp
	sdk/Paths.cpp
	sdk/SkeletonsRaw.cpp
	sdk/SkeletonsRetargeted.cpp
	sdk/SkeletonsTemporary.cpp
	sdk/Streams.cpp
	sdk/Timecode.cpp
	sdk/Trackers.cpp
	sdk/Users.cpp
	ui/components/AssignmentHint.cpp
	ui/components/DeviceSelector.cpp
	ui/components/FilePicker.cpp
	ui/components/Focusable.cpp
	ui/components/Format.cpp
	ui/components/KeyboardCapture.cpp
	ui/components/LogPanel.cpp
	ui/components/RotationGizmo.cpp
	ui/components/SkeletonSketch.cpp
	ui/components/StatusMessage.cpp
	ui/screens/CalibrationScreen.cpp
	ui/screens/DevicesScreen.cpp
	ui/screens/ErgonomicsScreen.cpp
	ui/screens/GesturesScreen.cpp
	ui/screens/LandscapeBrowser.cpp
	ui/screens/LicenseScreen.cpp
	ui/screens/SkeletonsScreen.cpp
	ui/screens/TimecodeScreen.cpp
	ui/screens/TrackersScreen.cpp
	ui/screens/UsersScreen.cpp
)
target_include_directories(SDKClient PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")

target_link_libraries(SDKClient PRIVATE
	ManusSDK
	ftxui::component
	ftxui::dom
	ftxui::screen
	$<$<NOT:$<BOOL:${WIN32}>>:Threads::Threads>
)

add_custom_target(check_layers
	COMMAND ${CMAKE_COMMAND}
		-DCLIENT_ROOT=${CMAKE_CURRENT_SOURCE_DIR}
		-P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/CheckLayers.cmake
	COMMENT "Checking sdk/ui/app layer rules")
add_dependencies(SDKClient check_layers)

if(WIN32)
	add_custom_command(TARGET SDKClient POST_BUILD
		COMMAND ${CMAKE_COMMAND} -E copy_if_different
			"${MANUS_SDK_DIR}/lib/ManusSDK.dll"
			"$<TARGET_FILE_DIR:SDKClient>")
endif()
