// SDKClient ui/ component - text-input capture flag.
// While a screen has an active text field it sets this flag; the app shell
// then leaves ALL keys (including Q/R/Esc) to the screen, so typing "q" into
// a username doesn't navigate away.
#pragma once

namespace ui
{
	void SetKeyboardCapture(bool p_Captured);
	bool IsKeyboardCaptured();
}
