// SDKClient ui/ screen - live gesture recognition per glove: every known
// gesture with its confidence, for an explicitly selected glove.
// The SDK side lives in sdk/Streams.hpp (GestureStream) and
// sdk/LandscapeCache.hpp (gesture names).
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeGesturesScreen();
}
