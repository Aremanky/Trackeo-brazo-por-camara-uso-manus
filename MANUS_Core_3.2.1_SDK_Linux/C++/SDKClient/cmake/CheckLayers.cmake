# Enforces the source layering of this client (see README.md):
#   - only sdk/ modules may call the MANUS SDK (CoreSdk_*)
#   - sdk/ modules must be UI-free (no FTXUI)
# Run as: cmake -DCLIENT_ROOT=<SDKClient dir> -P CheckLayers.cmake

file(GLOB_RECURSE t_UiAppFiles
	"${CLIENT_ROOT}/ui/*.cpp" "${CLIENT_ROOT}/ui/*.hpp"
	"${CLIENT_ROOT}/app/*.cpp" "${CLIENT_ROOT}/app/*.hpp")
foreach(t_File IN LISTS t_UiAppFiles)
	file(READ "${t_File}" t_Content)
	if(t_Content MATCHES "CoreSdk_")
		message(FATAL_ERROR
			"Layer rule violation: ${t_File} uses CoreSdk_ directly.\n"
			"Only sdk/ modules may call the MANUS SDK.")
	endif()
endforeach()

file(GLOB_RECURSE t_SdkFiles "${CLIENT_ROOT}/sdk/*.cpp" "${CLIENT_ROOT}/sdk/*.hpp")
foreach(t_File IN LISTS t_SdkFiles)
	file(READ "${t_File}" t_Content)
	if(t_Content MATCHES "ftxui")
		message(FATAL_ERROR
			"Layer rule violation: ${t_File} references FTXUI.\n"
			"sdk/ modules must be UI-free and copy-pasteable.")
	endif()
endforeach()

message(STATUS "Layer rules OK: no CoreSdk_ outside sdk/, no FTXUI inside sdk/.")
