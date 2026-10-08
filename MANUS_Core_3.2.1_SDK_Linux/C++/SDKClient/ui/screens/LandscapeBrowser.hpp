// SDKClient ui/ screen - read-only browser over the MANUS Core landscape:
// "what does Core currently see". The SDK side of this lives in
// sdk/LandscapeCache.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeLandscapeBrowser();
}
