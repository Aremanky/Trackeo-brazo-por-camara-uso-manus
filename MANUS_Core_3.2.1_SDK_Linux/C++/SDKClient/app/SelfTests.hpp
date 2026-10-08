// Non-interactive self-tests, reachable through command-line flags (see
// app/Main.cpp). Both run headless and print PASS/FAIL lines, so they double
// as CI/toolchain checks; neither needs a running MANUS Core.
#pragma once

namespace app
{
	/// @brief --smoke: renders one frame, initializes and shuts down the SDK,
	/// and prints SMOKE PASS/FAIL. Returns the process exit code.
	int RunSmokeTest();

	/// @brief --probe: drives the skeletons screen with synthetic key events,
	/// headless, and prints a PASS/FAIL line per check. Returns the process
	/// exit code.
	int RunEventProbe();
}
