// SDKClient ui/ screen - the user system: add/remove/rename users (with real
// text input), reorder, assign/unassign dongles and gloves with explicit
// selection, and the auto-assignment toggle.
// The SDK side lives in sdk/Users.hpp.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeUsersScreen();
}
