#include "ui/screens/LandscapeBrowser.hpp"

#include "sdk/LandscapeCache.hpp"

#include "ui/components/Format.hpp"

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
		Element MakeTable(std::vector<std::vector<std::string>> p_Rows)
		{
			if (p_Rows.size() <= 1) return text("  (none)") | dim;
			Table t_Table(std::move(p_Rows));
			t_Table.SelectAll().Border(LIGHT);
			t_Table.SelectRow(0).Decorate(bold);
			t_Table.SelectRow(0).SeparatorVertical(LIGHT);
			t_Table.SelectRow(0).Border(LIGHT);
			return t_Table.Render();
		}

		std::string YesNo(bool p_Value) { return p_Value ? "yes" : "no"; }

		Element RenderDevices()
		{
			std::vector<std::vector<std::string>> t_GloveRows = {
				{ "ID", "Side", "Battery", "Signal", "Paired", "Dongle" } };
			for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
			{
				t_GloveRows.push_back({
					Id(t_Glove.id),
					t_Glove.side == Side_Left ? "Left" : t_Glove.side == Side_Right ? "Right" : "-",
					std::to_string(t_Glove.batteryPercentage) + "%",
					std::to_string(t_Glove.transmissionStrength) + "%",
					YesNo(t_Glove.pairedState == DevicePairedState_Paired),
					Id(t_Glove.dongleID),
					});
			}

			std::vector<std::vector<std::string>> t_DongleRows = {
				{ "ID", "License", "Channel", "Left glove", "Right glove" } };
			for (const DongleLandscapeData& t_Dongle : manus::LandscapeCache::DonglesSortedById())
			{
				t_DongleRows.push_back({
					Id(t_Dongle.id),
					std::string(t_Dongle.licenseType),
					std::to_string(t_Dongle.channel),
					Id(t_Dongle.leftGloveID),
					Id(t_Dongle.rightGloveID),
					});
			}

			return vbox({
				text("Gloves") | bold,
				MakeTable(std::move(t_GloveRows)),
				text("Dongles") | bold,
				MakeTable(std::move(t_DongleRows)),
				});
		}

		Element RenderUsers(const Landscape& p_Landscape)
		{
			std::vector<std::vector<std::string>> t_Rows = {
				{ "ID", "Name", "Dongle", "Left glove", "Right glove" } };
			for (uint32_t i = 0; i < p_Landscape.users.userCount; ++i)
			{
				const UserLandscapeData& t_User = p_Landscape.users.users[i];
				t_Rows.push_back({
					Id(t_User.id),
					t_User.name[0] != '\0' ? std::string(t_User.name) : "(unnamed)",
					Id(t_User.dongleID),
					Id(t_User.leftGloveID),
					Id(t_User.rightGloveID),
					});
			}
			return vbox({ text("Users") | bold, MakeTable(std::move(t_Rows)) });
		}

		Element RenderTrackers(const Landscape& p_Landscape)
		{
			std::vector<std::vector<std::string>> t_Rows = {
				{ "ID", "User", "HMD", "Manufacturer", "Product" } };
			for (uint32_t i = 0; i < p_Landscape.trackers.trackerCount; ++i)
			{
				const TrackerLandscapeData& t_Tracker = p_Landscape.trackers.trackers[i];
				t_Rows.push_back({
					std::string(t_Tracker.id),
					Id(t_Tracker.user),
					YesNo(t_Tracker.isHMD),
					std::string(t_Tracker.manufacturer),
					std::string(t_Tracker.productName),
					});
			}
			return vbox({ text("Trackers") | bold, MakeTable(std::move(t_Rows)) });
		}

		Element RenderTimecode(const Landscape& p_Landscape)
		{
			// Terminology matches the MANUS Core Dashboard: "Genlock" and
			// "keep interface alive" (the SDK struct fields are named
			// useSyncPulse and deviceKeepAlive).
			const TimeLandscape& t_Time = p_Landscape.time;
			Elements t_Lines = {
				text("Timecode") | bold,
				text("Interfaces: " + std::to_string(t_Time.interfaceCount)),
				text("Current interface: " + std::string(t_Time.currentInterface.name)
					+ " (" + std::string(t_Time.currentInterface.api) + ")"),
				text("Timecode signal detected: " + YesNo(t_Time.timecodeStatus)),
				text("Genlock: " + YesNo(t_Time.useSyncPulse)
					+ "   Genlock status: " + YesNo(t_Time.syncStatus)),
				text("Keep interface alive: " + YesNo(t_Time.deviceKeepAlive)),
			};
			// Only worth calling out when the signal is NOT real - that's the
			// noteworthy state; "real" is the expected default.
			if (t_Time.fakeTimecode)
				t_Lines.push_back(text("Signal source: simulated (fake timecode)") | dim);
			return vbox(std::move(t_Lines));
		}

		Element RenderGestures()
		{
			std::vector<std::vector<std::string>> t_Rows = { { "ID", "Name" } };
			for (const GestureLandscapeData& t_Gesture : manus::LandscapeCache::Gestures())
				t_Rows.push_back({ Id(t_Gesture.id), std::string(t_Gesture.name) });
			return vbox({ text("Known gestures") | bold, MakeTable(std::move(t_Rows)) });
		}

		Element RenderSkeletons(const Landscape& p_Landscape)
		{
			auto t_TypeName = [](SkeletonType p_Type) {
				switch (p_Type)
				{
				case SkeletonType_Hand: return "Hand";
				case SkeletonType_Body: return "Body";
				case SkeletonType_Both: return "Both";
				default: return "Invalid";
				}
				};
			std::vector<std::vector<std::string>> t_Rows = {
				{ "ID", "Session", "User", "Type", "Root bone", "Scaled" } };
			for (uint32_t i = 0; i < p_Landscape.skeletons.skeletonCount; ++i)
			{
				const SkeletonLandscapeData& t_Skeleton = p_Landscape.skeletons.skeletons[i];
				t_Rows.push_back({
					Id(t_Skeleton.id),
					std::string(t_Skeleton.session),
					Id(t_Skeleton.userId),
					t_TypeName(t_Skeleton.type),
					std::string(t_Skeleton.rootBoneName),
					YesNo(t_Skeleton.scaled),
					});
			}
			return vbox({ text("Loaded skeletons (all sessions)") | bold, MakeTable(std::move(t_Rows)) });
		}

		Element RenderNetDevices(const Landscape& p_Landscape)
		{
			std::vector<std::vector<std::string>> t_Rows = { { "ID", "Hostname", "IP" } };
			for (uint32_t i = 0; i < p_Landscape.netDevices.numberOfNetDevices; ++i)
			{
				const NetDeviceLandscapeData& t_Device = p_Landscape.netDevices.netDevices[i];
				t_Rows.push_back({
					Id(t_Device.netDeviceID),
					std::string(t_Device.hostname),
					std::string(t_Device.ip),
					});
			}
			return vbox({
				text("Net devices (other Core instances feeding this one)") | bold,
				MakeTable(std::move(t_Rows)),
				});
		}

		Element RenderSettings(const Landscape& p_Landscape)
		{
			const SettingsLandscape& t_Settings = p_Landscape.settings;
			return vbox({
				text("Core settings") | bold,
				text("Core version:              " + std::to_string(t_Settings.manusCoreVersion.major)
					+ "." + std::to_string(t_Settings.manusCoreVersion.minor)
					+ "." + std::to_string(t_Settings.manusCoreVersion.patch)),
				text("Playback mode:             " + YesNo(t_Settings.playbackMode)),
				text("Recording mode:            " + YesNo(t_Settings.recordingMode)),
				text("Ignore session timeouts:   " + YesNo(t_Settings.ignoreSessionTimeOuts)),
				text("Is net device:             " + YesNo(t_Settings.isNetDevice)),
				text("Connected as net device:   " + YesNo(t_Settings.isConnectedAsNetDevice)),
				separator(),
				text("License max glove pairs:   " + std::to_string(t_Settings.license.maxGlovePairs)),
				text("(full license features are on the License screen)") | dim,
				});
		}
	}

	Component MakeLandscapeBrowser()
	{
		struct State
		{
			std::vector<std::string> categories = {
				"Devices", "Users", "Skeletons", "Trackers", "Gestures",
				"Timecode", "Net devices", "Settings" };
			int selected = 0;
		};
		auto t_State = std::make_shared<State>();

		Component t_CategoryMenu = Menu(&t_State->categories, &t_State->selected);

		return Renderer(t_CategoryMenu, [t_State, t_CategoryMenu] {
			if (!manus::LandscapeCache::HasLandscape())
				return text("Waiting for the first landscape from Core...") | dim | center | flex;

			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();

			Element t_Detail;
			switch (t_State->selected)
			{
			case 0: t_Detail = RenderDevices(); break;
			case 1: t_Detail = RenderUsers(t_Landscape); break;
			case 2: t_Detail = RenderSkeletons(t_Landscape); break;
			case 3: t_Detail = RenderTrackers(t_Landscape); break;
			case 4: t_Detail = RenderGestures(); break;
			case 5: t_Detail = RenderTimecode(t_Landscape); break;
			case 6: t_Detail = RenderNetDevices(t_Landscape); break;
			default: t_Detail = RenderSettings(t_Landscape); break;
			}

			return hbox({
				t_CategoryMenu->Render() | size(WIDTH, EQUAL, 14) | frame,
				separator(),
				t_Detail | flex | frame,
				}) | flex;
			});
	}
}
