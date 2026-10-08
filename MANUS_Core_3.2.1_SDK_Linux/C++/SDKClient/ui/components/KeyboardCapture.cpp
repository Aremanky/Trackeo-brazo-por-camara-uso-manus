#include "ui/components/KeyboardCapture.hpp"

#include <atomic>

namespace ui
{
	namespace
	{
		std::atomic<bool> g_Captured{ false };
	}

	void SetKeyboardCapture(bool p_Captured) { g_Captured = p_Captured; }
	bool IsKeyboardCaptured() { return g_Captured; }
}
