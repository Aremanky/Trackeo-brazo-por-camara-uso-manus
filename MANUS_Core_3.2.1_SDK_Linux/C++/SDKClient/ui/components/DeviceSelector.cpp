#include "ui/components/DeviceSelector.hpp"

#include "sdk/Devices.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/Users.hpp"

#include "ui/components/Format.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/dom/elements.hpp>

using namespace ftxui;

namespace ui
{
	namespace
	{
		void Rebuild(DeviceSelectorState& p_State)
		{
			p_State.labels.clear();
			p_State.ids.clear();
			p_State.isGlove.clear();

			if (p_State.kind != DeviceKind::Dongles)
			{
				const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
				for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
				{
					std::string t_Label = "Glove " + Id(t_Glove.id)
						+ "  " + manus::Devices::SideName(t_Glove.side)
						+ "  " + manus::Devices::FamilyName(t_Glove.familyType)
						+ "  " + std::to_string(t_Glove.batteryPercentage) + "%";
					t_Label += t_Glove.pairedState == DevicePairedState_Paired
						? "  [paired to " + Id(t_Glove.dongleID) + "]"
						: "  [" + std::string(manus::Devices::PairedStateName(t_Glove.pairedState)) + "]";
					// Unassigned gloves stream no data - flag them in every list.
					UserLandscapeData t_User{};
					if (!manus::Users::TryFindUserForGlove(t_Landscape, t_Glove.id, t_User))
						t_Label += "  [no user]";
					p_State.labels.push_back(t_Label);
					p_State.ids.push_back(t_Glove.id);
					p_State.isGlove.push_back(true);
				}
			}

			if (p_State.kind != DeviceKind::Gloves)
			{
				for (const DongleLandscapeData& t_Dongle : manus::LandscapeCache::DonglesSortedById())
				{
					p_State.labels.push_back(
						"Dongle " + Id(t_Dongle.id)
						+ "  " + manus::Devices::FamilyName(t_Dongle.familyType)
						+ "  license: " + (t_Dongle.licenseType[0] != '\0' ? t_Dongle.licenseType : "none"));
					p_State.ids.push_back(t_Dongle.id);
					p_State.isGlove.push_back(false);
				}
			}

			if (p_State.selected >= (int)p_State.labels.size())
				p_State.selected = (int)p_State.labels.size() - 1;
			if (p_State.selected < 0) p_State.selected = 0;
		}
	}

	std::shared_ptr<DeviceSelectorState> MakeDeviceSelectorState(DeviceKind p_Kind)
	{
		auto t_State = std::make_shared<DeviceSelectorState>();
		t_State->kind = p_Kind;
		return t_State;
	}

	Component MakeDeviceSelector(std::shared_ptr<DeviceSelectorState> p_State)
	{
		Component t_Menu = Menu(&p_State->labels, &p_State->selected);
		return Renderer(t_Menu, [p_State, t_Menu] {
			// The landscape changes ~once per second; rebuilding per frame keeps
			// the list, ids and selection clamp in sync with no extra plumbing.
			Rebuild(*p_State);
			if (p_State->labels.empty())
				return text("(no devices in landscape)") | dim;
			return t_Menu->Render() | frame;
			});
	}

	bool HasSelection(const DeviceSelectorState& p_State)
	{
		return p_State.selected >= 0 && p_State.selected < (int)p_State.ids.size();
	}

	uint32_t SelectedId(const DeviceSelectorState& p_State)
	{
		return HasSelection(p_State) ? p_State.ids[p_State.selected] : 0;
	}

	bool SelectedIsGlove(const DeviceSelectorState& p_State)
	{
		return HasSelection(p_State) && p_State.isGlove[p_State.selected];
	}
}
