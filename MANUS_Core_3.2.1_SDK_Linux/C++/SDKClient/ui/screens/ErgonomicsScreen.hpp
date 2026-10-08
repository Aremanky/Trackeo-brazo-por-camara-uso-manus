// SDKClient ui/ screen - live ergonomics per glove: every joint angle from
// the ergonomics stream as a bar (spread and stretch per finger joint).
// The SDK side lives in sdk/Streams.hpp (Ergonomics).
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component MakeErgonomicsScreen();
}
