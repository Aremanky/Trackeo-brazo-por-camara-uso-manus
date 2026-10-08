// SDKClient - entry point.
//
//   SDKClient           interactive client (see app/App.cpp)
//   SDKClient --smoke   non-interactive toolchain/terminal check: renders
//                       one frame, initializes and shuts down the SDK, and
//                       prints SMOKE PASS/FAIL. No MANUS Core required.
//   SDKClient --probe   non-interactive UI self-test: drives the skeletons
//                       screen with synthetic key events, headless, and
//                       prints PASS/FAIL per check. (See app/SelfTests.cpp.)

#include "app/App.hpp"
#include "app/SelfTests.hpp"

#include <cstring>

int main(int argc, char** argv)
{
	for (int i = 1; i < argc; ++i)
	{
		if (std::strcmp(argv[i], "--smoke") == 0) return app::RunSmokeTest();
		if (std::strcmp(argv[i], "--probe") == 0) return app::RunEventProbe();
	}
	return app::Run();
}
