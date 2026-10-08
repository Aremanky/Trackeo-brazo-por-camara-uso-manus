// SDKClient ui/ component - bottom panel with the most recent SDK log lines.
// Scrolled with the mouse wheel (vertical; horizontal via Shift+wheel on
// terminals that report it) no matter where the cursor is: app/App.cpp
// forwards every wheel event to this component regardless of focus, since
// the app otherwise ignores the mouse entirely (see app/App.cpp).
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	/// @brief p_Lines is the number of visible lines. Add the returned
	/// component to the app's component tree (not just its Render() output)
	/// so it actually receives the wheel events forwarded to it.
	ftxui::Component MakeLogPanel(int p_Lines = 6);
}
