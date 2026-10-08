// SDKClient ui/ component - keeps a component reachable by keyboard events.
//
// FTXUI only routes key events into subtrees that report Focusable(), and a
// Tab delegates that to its active child. A screen whose active child is an
// empty Menu (no devices yet, no skeletons loaded yet, ...) would silently
// stop receiving ALL key events. Wrapping the screen in AlwaysFocusable keeps
// its hotkeys alive regardless of content.
#pragma once

#include <ftxui/component/component.hpp>

namespace ui
{
	ftxui::Component AlwaysFocusable(ftxui::Component p_Child);
}
