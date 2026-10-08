// SDKClient ui/ screen - trackers & tracking systems: live tracker poses
// (position AND rotation), user/role assignment, offsets, timeouts, a test
// tracker, and the per-system settings editor.
// The SDK side lives in sdk/Trackers.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeTrackersScreen();
}
