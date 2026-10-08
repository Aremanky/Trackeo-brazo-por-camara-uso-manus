// SDKClient ui/ screen - glove calibration as an automatic wizard: pick a
// glove, start, and the steps run through by themselves with a get-ready
// countdown per step. Plus .mcal save/load.
// The SDK side lives in sdk/Calibration.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeCalibrationScreen();
}
