// SDKClient ui/ component - the "assign this glove to a user" hint.
//
// Core only produces skeleton, ergonomics and gesture data for gloves that
// are assigned to a user. In Core Integrated that normally happens
// automatically (unless auto-assignment is disabled); connected to a
// separate Core (Local/Remote) it is a manual step. Screens that show
// per-glove data include this hint so "the glove is on but nothing
// arrives" points to the likely cause.
#pragma once

#include <ftxui/dom/elements.hpp>

#include <cstdint>

namespace ui
{
	/// @brief A short dim note for a glove without a user; an empty
	/// element when the glove IS assigned (safe to always include).
	ftxui::Element RenderAssignmentHint(uint32_t p_GloveId);
}
