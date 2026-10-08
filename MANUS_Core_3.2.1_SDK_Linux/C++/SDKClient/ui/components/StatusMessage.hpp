// SDKClient ui/ component - the ONE way action results are shown to the user.
// Screens report outcomes here instead of inventing their own message styles.
#pragma once

#include <ftxui/dom/elements.hpp>

#include <string>

namespace ui
{
	namespace Status
	{
		/// @brief Neutral information, e.g. instructions for a multi-step action.
		void Info(const std::string& p_Text);

		/// @brief A completed action, shown in green.
		void Success(const std::string& p_Text);

		/// @brief A failed action, shown in red. Pass SdkResult::Description()
		/// for SDK failures so the user sees the name and hint, not a number.
		void Error(const std::string& p_Text);

		/// @brief An action in progress, shown with a spinner until the next update.
		void Busy(const std::string& p_Text);

		void Clear();

		/// @brief The status line element; empty text when there is no status.
		ftxui::Element Render();
	}
}
