// SDKClient ui/ component - the ONE way a device is picked in any screen.
// Shows ID, side, family and pairing/link info so a user always knows which
// physical device an action will hit.
#pragma once

#include <ftxui/component/component.hpp>

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace ui
{
	enum class DeviceKind { Gloves, Dongles, GlovesAndDongles };

	struct DeviceSelectorState
	{
		DeviceKind kind = DeviceKind::GlovesAndDongles;
		int selected = 0;

		// Rebuilt from the landscape every frame; parallel arrays.
		std::vector<std::string> labels;
		std::vector<uint32_t> ids;
		std::vector<bool> isGlove;
	};

	std::shared_ptr<DeviceSelectorState> MakeDeviceSelectorState(DeviceKind p_Kind);
	ftxui::Component MakeDeviceSelector(std::shared_ptr<DeviceSelectorState> p_State);

	bool HasSelection(const DeviceSelectorState& p_State);
	uint32_t SelectedId(const DeviceSelectorState& p_State);
	bool SelectedIsGlove(const DeviceSelectorState& p_State);
}
