// SDKClient ui/ screen - timecode: Core's synchronization with an external
// LTC/Genlock signal.
// Read-only; a timecode generator is configured via the MANUS Core Dashboard.
// The SDK side lives in sdk/Timecode.hpp and sdk/LandscapeCache.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeTimecodeScreen();
}
