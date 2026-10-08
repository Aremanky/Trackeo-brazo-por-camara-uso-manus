// SDKClient ui/ screen - the three skeleton types in one place:
//   [1] Retargeted - build & load the example hand, watch the animated result
//   [2] Temporary  - DevTools round-trip and .mskl files
//   [3] Raw        - per-glove hand data on the standardized MANUS hand
// The SDK side lives in sdk/SkeletonsRetargeted.hpp, sdk/SkeletonsTemporary.hpp
// and sdk/SkeletonsRaw.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeSkeletonsScreen();
}
