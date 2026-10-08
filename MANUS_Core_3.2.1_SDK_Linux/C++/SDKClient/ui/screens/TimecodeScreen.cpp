#include "ui/screens/TimecodeScreen.hpp"

#include "sdk/Connection.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/Streams.hpp"
#include "sdk/Timecode.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/dom/elements.hpp>
#include <ftxui/dom/table.hpp>

#include <string>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		std::string OnOff(bool p_Value) { return p_Value ? "on" : "off"; }

		// 3x5 block font for the big timecode display: digits, ':' and '.'.
		const char* const* GlyphRows(char p_Char)
		{
			static const char* const t_0[] = { "███", "█ █", "█ █", "█ █", "███" };
			static const char* const t_1[] = { "  █", "  █", "  █", "  █", "  █" };
			static const char* const t_2[] = { "███", "  █", "███", "█  ", "███" };
			static const char* const t_3[] = { "███", "  █", "███", "  █", "███" };
			static const char* const t_4[] = { "█ █", "█ █", "███", "  █", "  █" };
			static const char* const t_5[] = { "███", "█  ", "███", "  █", "███" };
			static const char* const t_6[] = { "███", "█  ", "███", "█ █", "███" };
			static const char* const t_7[] = { "███", "  █", "  █", "  █", "  █" };
			static const char* const t_8[] = { "███", "█ █", "███", "█ █", "███" };
			static const char* const t_9[] = { "███", "█ █", "███", "  █", "███" };
			static const char* const t_Colon[] = { " ", "█", " ", "█", " " };
			static const char* const t_Dot[] = { " ", " ", " ", " ", "█" };
			static const char* const t_Space[] = { " ", " ", " ", " ", " " };
			switch (p_Char)
			{
			case '0': return t_0; case '1': return t_1; case '2': return t_2;
			case '3': return t_3; case '4': return t_4; case '5': return t_5;
			case '6': return t_6; case '7': return t_7; case '8': return t_8;
			case '9': return t_9; case ':': return t_Colon; case '.': return t_Dot;
			default: return t_Space;
			}
		}

		Element BigText(const std::string& p_Text)
		{
			Elements t_Rows;
			for (int t_Row = 0; t_Row < 5; ++t_Row)
			{
				std::string t_Line;
				for (const char t_Char : p_Text)
				{
					t_Line += GlyphRows(t_Char)[t_Row];
					t_Line += " ";
				}
				t_Rows.push_back(text(t_Line));
			}
			return vbox(std::move(t_Rows)) | bold;
		}

		Element RenderCurrentTime()
		{
			ManusTimestamp t_Timestamp{};
			if (!manus::StreamTime::Latest(t_Timestamp))
				return text("Waiting for stream data - the timecode display needs "
					"at least one active device streaming.") | dim | center;

			bool t_IsTimecode = false;
			const std::string t_Time = manus::Timecode::TimecodeString(t_Timestamp, t_IsTimecode);
			if (t_Time.empty())
				return text("Could not decode the stream timestamp.") | dim | center;

			return vbox({
				BigText(t_Time) | center,
				(t_IsTimecode
					? text("timecode HH:MM:SS:FF, from the latest data stream")
					: text("wall clock (UTC) - stream timestamps carry no timecode signal")) | dim | center,
				});
		}

		Element RenderTimecode()
		{
			const TimeLandscape t_Time = manus::LandscapeCache::Snapshot().time;

			// All detected audio interfaces; the row Core currently uses is marked.
			std::vector<std::vector<std::string>> t_Rows = { { "", "Interface", "API", "Index" } };
			for (uint32_t i = 0; i < t_Time.interfaceCount; ++i)
			{
				const TimecodeInterface& t_Interface = t_Time.interfaces[i];
				const bool t_IsCurrent = t_Interface.index == t_Time.currentInterface.index
					&& std::string(t_Interface.name) == t_Time.currentInterface.name;
				t_Rows.push_back({
					t_IsCurrent ? ">" : " ",
					std::string(t_Interface.name),
					std::string(t_Interface.api),
					std::to_string(t_Interface.index),
					});
			}
			Table t_Table(std::move(t_Rows));
			t_Table.SelectAll().Border(LIGHT);
			t_Table.SelectRow(0).Decorate(bold);

			Elements t_Lines = {
				text("Timecode interfaces: " + std::to_string(t_Time.interfaceCount)
					+ "   (index = position in Core's audio-interface list)") ,
				t_Time.interfaceCount > 0
					? t_Table.Render()
					: text("(no timecode interfaces detected)") | dim,
				separator(),
				text("Frame rate:            " + std::string(manus::Timecode::FPSName(t_Time.fps))),
				text("Timecode signal:       " + std::string(t_Time.timecodeStatus ? "detected" : "not detected")),
				text("Genlock:               " + OnOff(t_Time.useSyncPulse)),
				text("Genlock status:        " + std::string(t_Time.syncStatus ? "locked" : "not locked")),
				text("Keep interface alive:  " + OnOff(t_Time.deviceKeepAlive)),
				text("LTC channel:           " + (t_Time.ltcChannel >= 0 ? std::to_string(t_Time.ltcChannel) : std::string("-"))),
				separator(),
				text("Interface selection, Genlock, keep-alive and LTC channel can only be "
					"configured via the MANUS Core Dashboard - the SDK does not expose "
					"timecode configuration.") | dim,
			};

			// Only worth calling out when the signal is NOT real - that's the
			// noteworthy state; "real" is the expected default.
			if (t_Time.fakeTimecode)
				t_Lines.insert(t_Lines.begin() + 2, text("Signal source: simulated (fake timecode)") | dim);

			if (manus::Connection::Mode() == manus::ConnectionMode::Integrated)
			{
				t_Lines.insert(t_Lines.begin(),
					text("Core Integrated runs inside this process - no timecode hardware is attached, "
						"so this data is not meaningful here.") | color(ftxui::Color::Yellow));
				t_Lines.insert(t_Lines.begin() + 1, separator());
			}

			return vbox(std::move(t_Lines));
		}
	}

	Component MakeTimecodeScreen()
	{
		return Renderer([] {
			return vbox({
				window(text(" Current time "), RenderCurrentTime()),
				window(text(" Timecode "), RenderTimecode() | frame) | flex,
				}) | flex;
			});
	}
}
