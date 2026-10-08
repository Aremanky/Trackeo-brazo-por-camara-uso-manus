// SDKClient ui/ screen - dongle licensing: view license features, apply a
// .lic file via the file picker, or retrieve the newest license from the
// MANUS license service.
// The SDK side lives in sdk/License.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeLicenseScreen();
}
