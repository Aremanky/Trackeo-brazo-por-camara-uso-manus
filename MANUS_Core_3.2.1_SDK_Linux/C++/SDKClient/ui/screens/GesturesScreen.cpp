#include "ui/screens/GesturesScreen.hpp"

#include "sdk/LandscapeCache.hpp"
#include "sdk/Streams.hpp"

#include "ui/components/AssignmentHint.hpp"
#include "ui/components/DeviceSelector.hpp"
#include "ui/components/Format.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/dom/elements.hpp>
#include <ftxui/dom/table.hpp>

#include <algorithm>
#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		Element RenderGestures(uint32_t p_GloveId)
		{
			// --8<-- [start:render-gestures]
			manus::GestureStream::GloveGestures t_Gestures;
			if (!manus::GestureStream::LatestForGlove(p_GloveId, t_Gestures))
				return vbox({
					text("No gesture data received for glove " + Id(p_GloveId) + " yet.") | dim,
					RenderAssignmentHint(p_GloveId),
					}) | center;

			// Gesture names come from the landscape.
			std::map<uint32_t, std::string> t_Names;
			for (const GestureLandscapeData& t_Gesture : manus::LandscapeCache::Gestures())
				t_Names[t_Gesture.id] = t_Gesture.name;

			// Highest confidence first.
			std::vector<GestureProbability> t_Sorted = t_Gestures.probabilities;
			std::sort(t_Sorted.begin(), t_Sorted.end(),
				[](const GestureProbability& a, const GestureProbability& b) { return a.percent > b.percent; });
				// --8<-- [end:render-gestures]

			std::vector<std::vector<std::string>> t_Rows = { { "Gesture", "ID", "Confidence" } };
			for (const GestureProbability& t_Probability : t_Sorted)
			{
				char t_Percent[16];
				std::snprintf(t_Percent, sizeof(t_Percent), "%5.1f%%", t_Probability.percent * 100.0f);
				const auto t_Name = t_Names.find(t_Probability.id);
				t_Rows.push_back({
					t_Name != t_Names.end() ? t_Name->second : "(unknown)",
					Id(t_Probability.id),
					t_Percent,
					});
			}

			Table t_Table(std::move(t_Rows));
			t_Table.SelectAll().Border(LIGHT);
			t_Table.SelectRow(0).Decorate(bold);
			t_Table.SelectColumn(2).DecorateCells(align_right);

			return vbox({
				text("Total gestures: " + std::to_string(t_Gestures.totalCount)),
				t_Table.Render() | frame | flex,
				});
		}
	}

	Component MakeGesturesScreen()
	{
		auto t_Gloves = MakeDeviceSelectorState(DeviceKind::Gloves);
		Component t_GloveSelector = MakeDeviceSelector(t_Gloves);

		return Renderer(t_GloveSelector, [t_Gloves, t_GloveSelector] {
			Element t_Right = HasSelection(*t_Gloves)
				? RenderGestures(SelectedId(*t_Gloves))
				: text("Select a glove on the left.") | dim | center;

			return hbox({
				window(text(" Gloves "), t_GloveSelector->Render()) | flex,
				window(text(" Gestures "), t_Right) | flex,
				}) | flex;
			});
	}
}
