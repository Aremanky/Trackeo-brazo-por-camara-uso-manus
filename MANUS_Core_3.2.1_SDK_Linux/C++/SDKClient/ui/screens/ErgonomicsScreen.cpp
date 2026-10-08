#include "ui/screens/ErgonomicsScreen.hpp"

#include "sdk/LandscapeCache.hpp"
#include "sdk/Streams.hpp"

#include "ui/components/AssignmentHint.hpp"
#include "ui/components/DeviceSelector.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/SkeletonSketch.hpp" // FingerColor

#include <ftxui/component/component.hpp>
#include <ftxui/dom/elements.hpp>

#include <algorithm>
#include <cstdio>
#include <string>

using namespace ftxui;

namespace ui
{
	namespace
	{
		// Ergonomics values are joint angles in degrees, indexed by
		// ErgonomicsDataType: per hand 5 fingers x 4 values, left hand first.
		// The thumb uses CMC/MCP/IP joints, the other fingers MCP/PIP/DIP.
		Element RenderJointBar(const char* p_Label, float p_Degrees, bool p_IsSpread, ftxui::Color p_Color)
		{
			// Display ranges (deg): spread is signed, stretch mostly positive.
			const float t_Min = p_IsSpread ? -60.0f : -30.0f;
			const float t_Max = p_IsSpread ? 60.0f : 110.0f;
			const float t_Normalized = std::clamp((p_Degrees - t_Min) / (t_Max - t_Min), 0.0f, 1.0f);

			char t_Value[16];
			std::snprintf(t_Value, sizeof(t_Value), "%7.1f", p_Degrees);
			return hbox({
				text(p_Label) | size(WIDTH, EQUAL, 13),
				gauge(t_Normalized) | color(p_Color) | size(WIDTH, EQUAL, 32),
				text(t_Value),
				text("°"),
				});
		}

		Element RenderErgonomics(uint32_t p_GloveId)
		{
			ErgonomicsData t_Data{};
			if (!manus::Ergonomics::LatestForGlove(p_GloveId, t_Data))
				return vbox({
					text("No ergonomics data for glove " + Id(p_GloveId) + " yet.") | dim,
					text("Data flows while the glove is on and streaming.") | dim,
					RenderAssignmentHint(p_GloveId),
					}) | center;

			// Which half of the value table applies depends on the hand side.
			Side t_Side = Side_Left;
			for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
				if (t_Glove.id == p_GloveId) { t_Side = t_Glove.side; break; }
			const int t_Base = t_Side == Side_Right ? ErgonomicsDataType_RightFingerThumbCMCSpread : 0;

			static const char* const s_Fingers[5] = { "Thumb", "Index", "Middle", "Ring", "Pinky" };
			static const char* const s_ThumbJoints[4] = { "CMC Spread", "CMC Stretch", "MCP Stretch", "IP Stretch" };
			static const char* const s_FingerJoints[4] = { "MCP Spread", "MCP Stretch", "PIP Stretch", "DIP Stretch" };

			Elements t_Lines = { text("Joint angles in degrees") | dim };
			for (int t_Finger = 0; t_Finger < 5; ++t_Finger)
			{
				t_Lines.push_back(text(s_Fingers[t_Finger]) | bold | color(FingerColor(t_Finger)));
				for (int t_Joint = 0; t_Joint < 4; ++t_Joint)
				{
					const char* const t_Label = t_Finger == 0 ? s_ThumbJoints[t_Joint] : s_FingerJoints[t_Joint];
					const float t_Degrees = t_Data.data[t_Base + t_Finger * 4 + t_Joint];
					t_Lines.push_back(RenderJointBar(t_Label, t_Degrees, t_Joint == 0, FingerColor(t_Finger)));
				}
			}
			return vbox(std::move(t_Lines)) | frame | flex;
		}
	}

	Component MakeErgonomicsScreen()
	{
		auto t_Gloves = MakeDeviceSelectorState(DeviceKind::Gloves);
		Component t_GloveSelector = MakeDeviceSelector(t_Gloves);

		return Renderer(t_GloveSelector, [t_Gloves, t_GloveSelector] {
			Element t_Right = HasSelection(*t_Gloves)
				? RenderErgonomics(SelectedId(*t_Gloves))
				: text("Select a glove on the left.") | dim | center;

			return hbox({
				window(text(" Gloves "), t_GloveSelector->Render()) | flex,
				window(text(" Ergonomics "), t_Right) | flex,
				}) | flex;
			});
	}
}
