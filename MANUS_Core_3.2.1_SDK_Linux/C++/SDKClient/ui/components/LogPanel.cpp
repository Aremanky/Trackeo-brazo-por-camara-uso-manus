#include "ui/components/LogPanel.hpp"

#include "sdk/Streams.hpp"

#include <ftxui/component/event.hpp>
#include <ftxui/component/mouse.hpp>
#include <ftxui/dom/elements.hpp>

#include <algorithm>

using namespace ftxui;

namespace ui
{
	namespace
	{
		constexpr int SCROLL_STEP = 3;
		constexpr int COLUMN_STEP = 10;

		struct LogPanelState
		{
			int linesBack = 0;    // 0 = showing the most recent lines
			int columnOffset = 0; // characters scrolled right
		};

		// App.cpp only ever forwards wheel events here (it swallows every other
		// mouse event before any component sees it), so there is no need to check
		// where the cursor is - any event that arrives is meant for this panel.
		bool HandleScrollMouse(Event p_Event, LogPanelState& p_State)
		{
			if (!p_Event.is_mouse()) return false;
			switch (p_Event.mouse().button)
			{
			case Mouse::WheelUp: p_State.linesBack += SCROLL_STEP; return true;
			case Mouse::WheelDown: p_State.linesBack = std::max(0, p_State.linesBack - SCROLL_STEP); return true;
			// Horizontal wheel events are only reported by some terminals.
			case Mouse::WheelRight: p_State.columnOffset += COLUMN_STEP; return true;
			case Mouse::WheelLeft:
				p_State.columnOffset = std::max(0, p_State.columnOffset - COLUMN_STEP);
				return true;
			default: return false;
			}
		}

		Element Render(const LogPanelState& p_State, int p_Lines)
		{
			// Logs::Tail caps at its own retained history (currently 500 lines);
			// asking for more than that just returns everything available.
			const std::vector<std::string> t_All = manus::Logs::Tail(100000);
			const int t_Total = (int)t_All.size();
			const int t_LinesBack = std::min(p_State.linesBack, std::max(0, t_Total - p_Lines));
			const int t_End = t_Total - t_LinesBack;
			const int t_Start = std::max(0, t_End - p_Lines);

			Elements t_LogElements;
			for (int i = t_Start; i < t_End; ++i)
			{
				const std::string& t_Full = t_All[i];
				const std::string t_Visible = (size_t)p_State.columnOffset < t_Full.size()
					? t_Full.substr(p_State.columnOffset) : "";
				t_LogElements.push_back(text(t_Visible) | dim);
			}

			std::string t_Title = " SDK log ";
			if (t_LinesBack > 0) t_Title += "(scrolled back " + std::to_string(t_LinesBack) + " lines) ";
			if (p_State.columnOffset > 0) t_Title += "(scrolled right " + std::to_string(p_State.columnOffset) + " cols) ";

			return window(text(t_Title),
				t_LogElements.empty()
					? text("(no log messages yet)") | dim
					: vbox(std::move(t_LogElements)))
				| size(HEIGHT, EQUAL, p_Lines + 2);
		}
	}

	Component MakeLogPanel(int p_Lines)
	{
		auto t_State = std::make_shared<LogPanelState>();

		Component t_Renderer = Renderer([t_State, p_Lines] {
			return Render(*t_State, p_Lines);
			});

		return CatchEvent(t_Renderer, [t_State](Event p_Event) {
			return HandleScrollMouse(p_Event, *t_State);
			});
	}
}
