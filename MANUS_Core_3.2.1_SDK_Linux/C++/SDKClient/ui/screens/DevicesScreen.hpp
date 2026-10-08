// SDKClient ui/ screen - gloves & dongles: live device list with detail,
// haptics test, pairing (including pairing to a specific dongle) and firmware
// updates with explicit device selection.
// The SDK side lives in sdk/Devices.hpp and sdk/Firmware.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeDevicesScreen();
}
