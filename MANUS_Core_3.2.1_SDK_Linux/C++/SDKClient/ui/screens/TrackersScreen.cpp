#include "ui/screens/TrackersScreen.hpp"

#include "sdk/LandscapeCache.hpp"
#include "sdk/Trackers.hpp"

#include "ui/components/Format.hpp"
#include "ui/components/KeyboardCapture.hpp"
#include "ui/components/RotationGizmo.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/component_options.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct TrackersState
		{
			enum class Mode { Normal, Systems, SystemDetail, EditSetting, PickUser, PickRole, EnterOffset };
			enum class Pending { None, Assign, Offset };

			Mode mode = Mode::Normal;
			Pending pending = Pending::None;
			int tab = 0;

			// Normal view: tracker list.
			int selectedTracker = 0;
			std::vector<std::string> trackerLabels;
			std::vector<std::string> trackerIds;

			// Systems editor.
			std::vector<TrackerSystem> systems;
			std::vector<std::string> systemLabels;
			int selectedSystem = 0;
			std::vector<std::string> settingLabels;
			int selectedSetting = 0;
			std::string input;

			// Pick flows.
			std::vector<std::string> userLabels;
			std::vector<uint32_t> userIds;
			int selectedUser = 0;
			std::vector<std::string> roleLabels;
			std::vector<TrackerType> roles;
			int selectedRole = 0;
			std::string pendingTrackerId;
			uint32_t pendingOffsetUserId = 0;
			std::string offsetInput; // "x y z" in meters, or empty for the example offset

			// Test tracker.
			std::shared_ptr<std::atomic<bool>> testActive = std::make_shared<std::atomic<bool>>(false);
		};

		std::string Vec3String(const ManusVec3& p_Vector)
		{
			char t_Buffer[64];
			std::snprintf(t_Buffer, sizeof(t_Buffer), "%7.3f %7.3f %7.3f", p_Vector.x, p_Vector.y, p_Vector.z);
			return t_Buffer;
		}

		std::string QuatString(const ManusQuaternion& p_Quaternion)
		{
			char t_Buffer[80];
			std::snprintf(t_Buffer, sizeof(t_Buffer), "%6.3f %6.3f %6.3f %6.3f",
				p_Quaternion.x, p_Quaternion.y, p_Quaternion.z, p_Quaternion.w);
			return t_Buffer;
		}

		void RebuildTrackerList(TrackersState& p_State)
		{
			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
			p_State.trackerLabels.clear();
			p_State.trackerIds.clear();
			for (uint32_t i = 0; i < t_Landscape.trackers.trackerCount; ++i)
			{
				const TrackerLandscapeData& t_Tracker = t_Landscape.trackers.trackers[i];
				p_State.trackerIds.push_back(t_Tracker.id);
				p_State.trackerLabels.push_back(std::string(t_Tracker.id)
					+ "  " + manus::Trackers::SystemTypeName(t_Tracker.systemType)
					+ "  role: " + manus::Trackers::TypeName(t_Tracker.type)
					+ "  user: " + (t_Tracker.user != 0 ? Id(t_Tracker.user) : "-"));
			}
			if (p_State.selectedTracker >= (int)p_State.trackerIds.size())
				p_State.selectedTracker = (int)p_State.trackerIds.size() - 1;
			if (p_State.selectedTracker < 0) p_State.selectedTracker = 0;
		}

		void RebuildUserList(TrackersState& p_State)
		{
			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
			p_State.userLabels.clear();
			p_State.userIds.clear();
			for (uint32_t i = 0; i < t_Landscape.users.userCount; ++i)
			{
				const UserLandscapeData& t_User = t_Landscape.users.users[i];
				p_State.userIds.push_back(t_User.id);
				p_State.userLabels.push_back(
					(t_User.name[0] != '\0' ? std::string(t_User.name) : "(unnamed)")
					+ "  (id " + Id(t_User.id) + ")");
			}
			if (p_State.selectedUser >= (int)p_State.userIds.size()) p_State.selectedUser = 0;
		}

		void RefreshSystems(TrackersState& p_State)
		{
			const manus::SdkResult t_Result = manus::Trackers::GetSystems(p_State.systems);
			p_State.systemLabels.clear();
			if (!t_Result.Ok())
			{
				Status::Error("Failed to get tracking systems: " + t_Result.Description());
				return;
			}
			for (const TrackerSystem& t_System : p_State.systems)
			{
				p_State.systemLabels.push_back(std::string(t_System.active ? "[active]   " : "[inactive] ")
					+ t_System.id + "  (" + std::to_string(t_System.currentSettingsCount) + " settings)");
			}
			if (p_State.selectedSystem >= (int)p_State.systems.size()) p_State.selectedSystem = 0;
		}

		std::string SettingValueString(const TrackerSystemSetting& p_Setting)
		{
			switch (p_Setting.settingtype)
			{
			case TrackerSystemSettingType_SettingInt:
				return std::to_string(p_Setting.settingInt.value)
					+ "  (int, " + std::to_string(p_Setting.settingInt.min)
					+ ".." + std::to_string(p_Setting.settingInt.max) + ")";
			case TrackerSystemSettingType_SettingBool:
				return std::string(p_Setting.settingBool.value ? "Enabled" : "Disabled") + "  (bool)";
			case TrackerSystemSettingType_SettingFile:
				return std::string(p_Setting.settingFile.value[0] != '\0' ? p_Setting.settingFile.value : "(unset)")
					+ "  (file, " + p_Setting.settingFile.extension + ")";
			case TrackerSystemSettingType_SettingIp:
				return std::string(p_Setting.settingIp.value[0] != '\0' ? p_Setting.settingIp.value : "(unset)")
					+ "  (ip)";
			default:
				return "(unknown type)";
			}
		}

		void RebuildSettingList(TrackersState& p_State)
		{
			p_State.settingLabels.clear();
			if (p_State.selectedSystem >= (int)p_State.systems.size()) return;
			const TrackerSystem& t_System = p_State.systems[p_State.selectedSystem];
			for (uint32_t i = 0; i < t_System.currentSettingsCount; ++i)
			{
				const TrackerSystemSetting& t_Setting = t_System.trackerSystemSettings[i];
				p_State.settingLabels.push_back(std::string(t_Setting.id) + " = " + SettingValueString(t_Setting));
			}
			if (p_State.selectedSetting >= (int)p_State.settingLabels.size()) p_State.selectedSetting = 0;
		}

		void CommitSettingInput(TrackersState& p_State)
		{
			SetKeyboardCapture(false);
			p_State.mode = TrackersState::Mode::SystemDetail;

			if (p_State.selectedSystem >= (int)p_State.systems.size()) return;
			// --8<-- [start:commit-setting]
			TrackerSystem& t_System = p_State.systems[p_State.selectedSystem];
			if (p_State.selectedSetting >= (int)t_System.currentSettingsCount) return;
			TrackerSystemSetting& t_Setting = t_System.trackerSystemSettings[p_State.selectedSetting];

			switch (t_Setting.settingtype)
			{
			case TrackerSystemSettingType_SettingInt:
				try { t_Setting.settingInt.value = std::stoi(p_State.input); }
				catch (...) { Status::Error("\"" + p_State.input + "\" is not a valid integer."); return; }
				break;
			case TrackerSystemSettingType_SettingFile:
				std::snprintf(t_Setting.settingFile.value, sizeof(t_Setting.settingFile.value), "%s", p_State.input.c_str());
				break;
			case TrackerSystemSettingType_SettingIp:
				std::snprintf(t_Setting.settingIp.value, sizeof(t_Setting.settingIp.value), "%s", p_State.input.c_str());
				break;
			default:
				return;
			}

			const manus::SdkResult t_Result = manus::Trackers::SetSystems(p_State.systems);
			// --8<-- [end:commit-setting]
			if (!t_Result.Ok()) Status::Error("Failed to apply setting: " + t_Result.Description());
			else Status::Success("Applied \"" + std::string(t_Setting.id) + "\".");
			RefreshSystems(p_State);
			RebuildSettingList(p_State);
		}

		// --8<-- [start:set-offset-example]
		// Parses "x y z" (meters); empty input falls back to the MANUS
		// Universal Mount's example measurements for a left-hand tracker.
		void CommitOffsetInput(TrackersState& p_State)
		{
			SetKeyboardCapture(false);
			p_State.mode = TrackersState::Mode::Normal;
			p_State.pending = TrackersState::Pending::None;

			TrackerOffset t_Offset{};
			t_Offset.rotation = { 1.0f, 0.0f, 0.0f, 0.0f };
			t_Offset.entryType = TrackerOffsetType_LeftHandTrackerToCasing;

			if (p_State.offsetInput.find_first_not_of(" \t") == std::string::npos)
			{
				t_Offset.translation = { 0.003f, -0.058f, -0.043f };
			}
			else
			{
				float t_X = 0.0f, t_Y = 0.0f, t_Z = 0.0f;
				if (std::sscanf(p_State.offsetInput.c_str(), "%f %f %f", &t_X, &t_Y, &t_Z) != 3)
				{
					Status::Error("\"" + p_State.offsetInput + "\" is not 3 numbers - expected \"x y z\" in meters.");
					return;
				}
				t_Offset.translation = { t_X, t_Y, t_Z };
			}

			const manus::SdkResult t_Result = manus::Trackers::SetOffset(p_State.pendingOffsetUserId, t_Offset);
			if (!t_Result.Ok()) Status::Error("Failed to set offset: " + t_Result.Description());
			else Status::Success("User " + Id(p_State.pendingOffsetUserId) + ": left-hand tracker offset set to "
				+ Vec3String(t_Offset.translation) + ".");
		}
		// --8<-- [end:set-offset-example]

		Element RenderTrackerDetail(const TrackersState& p_State)
		{
			if (p_State.trackerIds.empty())
				return text("No trackers in the landscape.") | dim | center;
			const std::string& t_Id = p_State.trackerIds[p_State.selectedTracker];

			// Live pose from the tracker stream, matched by id.
			for (const TrackerData& t_Data : manus::Trackers::LatestData())
			{
				if (t_Id != t_Data.trackerId.id) continue;
				return hbox({
					vbox({
						text(t_Id) | bold,
						text("Quality:   " + std::string(manus::Trackers::QualityName(t_Data.quality))),
						text("Position:  " + Vec3String(t_Data.position) + "  (x y z)"),
						text("Rotation:  " + QuatString(t_Data.rotation) + "  (quaternion x y z w)"),
						text("User:      " + (t_Data.userId != 0 ? Id(t_Data.userId) : "-")),
						text("Role:      " + std::string(manus::Trackers::TypeName(t_Data.trackerType))),
						}),
					filler(),
					vbox({
						RenderRotationGizmo(t_Data.rotation),
						text("orientation (Z up)") | dim | center,
						}),
					});
			}
			return vbox({
				text(t_Id) | bold,
				text("No live data on the tracker stream yet.") | dim,
				});
		}

		Element RenderTimeouts()
		{
			bool t_Enabled = false;
			float t_Seconds = 0.0f;
			if (!manus::Trackers::GetTimeout(t_Enabled, t_Seconds).Ok())
				return text("Tracker timeout: unavailable") | dim;
			char t_Buffer[80];
			std::snprintf(t_Buffer, sizeof(t_Buffer), "Tracker timeout: %s   duration: %.0f s",
				t_Enabled ? "Enabled" : "Disabled", t_Seconds);
			return text(t_Buffer);
		}

		std::string ModeHints(const TrackersState& p_State)
		{
			switch (p_State.mode)
			{
			case TrackersState::Mode::Systems:
				return " [Enter] open system   [A] toggle active   [C] back ";
			case TrackersState::Mode::SystemDetail:
				return " [Enter] edit setting (bool: toggle)   [A] toggle active   [C] back ";
			case TrackersState::Mode::EditSetting:
				return " type a value   [Enter] apply   [Esc] cancel ";
			case TrackersState::Mode::PickUser:
				return p_State.pending == TrackersState::Pending::Offset
					? " [Up/Down] pick user   [Enter] next: enter the offset   [C] cancel "
					: " [Up/Down] pick user   [Enter] confirm   [C] cancel ";
			case TrackersState::Mode::PickRole:
				return " [Up/Down] pick role   [Enter] assign   [C] cancel ";
			case TrackersState::Mode::EnterOffset:
				return " type \"x y z\" in meters, or leave empty for the example offset   [Enter] apply   [Esc] cancel ";
			default:
				return " [A] assign...   [U] unassign   [T] offset...   [O] test tracker   [E] timeout on/off   [L] switch duration   [S] tracking systems ";
			}
		}
	}

	Component MakeTrackersScreen()
	{
		auto t_State = std::make_shared<TrackersState>();
		for (int i = TrackerType_Head; i < TrackerType_MAX_SIZE; ++i)
		{
			t_State->roles.push_back((TrackerType)i);
			t_State->roleLabels.push_back(manus::Trackers::TypeName((TrackerType)i));
		}

		Component t_TrackerMenu = Menu(&t_State->trackerLabels, &t_State->selectedTracker);
		Component t_SystemsMenu = Menu(&t_State->systemLabels, &t_State->selectedSystem);
		Component t_SettingsMenu = Menu(&t_State->settingLabels, &t_State->selectedSetting);
		Component t_UserMenu = Menu(&t_State->userLabels, &t_State->selectedUser);
		Component t_RoleMenu = Menu(&t_State->roleLabels, &t_State->selectedRole);

		InputOption t_InputOption;
		t_InputOption.multiline = false;
		t_InputOption.on_enter = [t_State] { CommitSettingInput(*t_State); };
		Component t_Input = Input(&t_State->input, "new value", t_InputOption);

		InputOption t_OffsetInputOption;
		t_OffsetInputOption.multiline = false;
		t_OffsetInputOption.on_enter = [t_State] { CommitOffsetInput(*t_State); };
		Component t_OffsetInput = Input(&t_State->offsetInput, "x y z (empty = example offset)", t_OffsetInputOption);

		Component t_Areas = Container::Tab(
			{ t_TrackerMenu, t_SystemsMenu, t_SettingsMenu, t_Input, t_UserMenu, t_RoleMenu, t_OffsetInput }, &t_State->tab);

		Component t_Root = Renderer(t_Areas, [=] {
			RebuildTrackerList(*t_State);

			using Mode = TrackersState::Mode;
			switch (t_State->mode)
			{
			case Mode::Systems: t_State->tab = 1; break;
			case Mode::SystemDetail: t_State->tab = 2; break;
			case Mode::EditSetting: t_State->tab = 3; break;
			case Mode::PickUser: t_State->tab = 4; break;
			case Mode::PickRole: t_State->tab = 5; break;
			case Mode::EnterOffset: t_State->tab = 6; break;
			default: t_State->tab = 0; break;
			}

			Element t_Body;
			switch (t_State->mode)
			{
			case Mode::Systems:
				t_Body = window(text(" Tracking systems "),
					t_State->systemLabels.empty()
						? text("(no tracking systems reported)") | dim
						: t_SystemsMenu->Render() | frame) | flex;
				break;
			case Mode::SystemDetail:
			case Mode::EditSetting:
			{
				const std::string t_SystemName = t_State->selectedSystem < (int)t_State->systems.size()
					? t_State->systems[t_State->selectedSystem].id : "?";
				Element t_Right = t_State->mode == Mode::EditSetting
					? window(text(" New value for "
						+ (t_State->selectedSetting < (int)t_State->settingLabels.size()
							? t_State->settingLabels[t_State->selectedSetting].substr(0, t_State->settingLabels[t_State->selectedSetting].find(" = "))
							: std::string("?")) + " "),
						t_Input->Render())
					: text("") | size(WIDTH, EQUAL, 0);
				t_Body = hbox({
					window(text(" " + t_SystemName + " - settings "),
						t_State->settingLabels.empty()
							? text("(this system has no settings)") | dim
							: t_SettingsMenu->Render() | frame) | flex,
					t_Right,
					}) | flex;
				break;
			}
			case Mode::PickUser:
				t_Body = window(text(" Pick a user "),
					t_State->userLabels.empty()
						? text("(no users)") | dim
						: t_UserMenu->Render() | frame) | flex;
				break;
			case Mode::PickRole:
				t_Body = window(text(" Pick a role for tracker \"" + t_State->pendingTrackerId + "\" "),
					t_RoleMenu->Render() | frame) | flex;
				break;
			case Mode::EnterOffset:
				t_Body = window(text(" Offset for user " + Id(t_State->pendingOffsetUserId)
					+ " - left-hand tracker to glove casing "),
					vbox({
						text("Enter the translation as \"x y z\" in meters (tracker relative to the mount)."),
						text("Leave empty and press [Enter] to use the MANUS Universal Mount's example: 0.003 -0.058 -0.043."),
						separator(),
						t_OffsetInput->Render(),
						})) | flex;
				break;
			default:
				t_Body = hbox({
					window(text(std::string(" Trackers ") + (t_State->testActive->load() ? "- test tracker ON " : "")),
						t_State->trackerLabels.empty()
							? text("(no trackers in landscape)") | dim
							: t_TrackerMenu->Render() | frame) | flex,
					vbox({
						RenderTrackerDetail(*t_State),
						separator(),
						RenderTimeouts(),
						}) | size(WIDTH, GREATER_THAN, 46),
					}) | flex;
				break;
			}

			return vbox({
				Status::Render(),
				t_Body,
				text(ModeHints(*t_State)) | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			using Mode = TrackersState::Mode;
			using Pending = TrackersState::Pending;

			if (t_State->mode == Mode::EditSetting)
			{
				if (p_Event == Event::Escape)
				{
					SetKeyboardCapture(false);
					t_State->mode = Mode::SystemDetail;
					Status::Clear();
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::EnterOffset)
			{
				if (p_Event == Event::Escape)
				{
					SetKeyboardCapture(false);
					t_State->mode = Mode::Normal;
					t_State->pending = Pending::None;
					Status::Clear();
					return true;
				}
				return false;
			}

			const bool t_IsC = p_Event == Event::Character('c') || p_Event == Event::Character('C');
			const bool t_IsA = p_Event == Event::Character('a') || p_Event == Event::Character('A');

			if (t_State->mode == Mode::Systems)
			{
				if (t_IsC) { t_State->mode = Mode::Normal; Status::Clear(); return true; }
				if (t_IsA && t_State->selectedSystem < (int)t_State->systems.size())
				{
					// --8<-- [start:toggle-system]
					t_State->systems[t_State->selectedSystem].active = !t_State->systems[t_State->selectedSystem].active;
					const manus::SdkResult t_Result = manus::Trackers::SetSystems(t_State->systems);
					// --8<-- [end:toggle-system]
					if (!t_Result.Ok()) Status::Error("Failed to toggle system: " + t_Result.Description());
					RefreshSystems(*t_State);
					return true;
				}
				if (p_Event == Event::Return)
				{
					RebuildSettingList(*t_State);
					t_State->mode = Mode::SystemDetail;
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::SystemDetail)
			{
				if (t_IsC) { t_State->mode = Mode::Systems; RefreshSystems(*t_State); return true; }
				if (t_IsA && t_State->selectedSystem < (int)t_State->systems.size())
				{
					t_State->systems[t_State->selectedSystem].active = !t_State->systems[t_State->selectedSystem].active;
					const manus::SdkResult t_Result = manus::Trackers::SetSystems(t_State->systems);
					if (!t_Result.Ok()) Status::Error("Failed to toggle system: " + t_Result.Description());
					RefreshSystems(*t_State);
					RebuildSettingList(*t_State);
					return true;
				}
				if (p_Event == Event::Return && t_State->selectedSystem < (int)t_State->systems.size())
				{
					TrackerSystem& t_System = t_State->systems[t_State->selectedSystem];
					if (t_State->selectedSetting >= (int)t_System.currentSettingsCount) return true;
					TrackerSystemSetting& t_Setting = t_System.trackerSystemSettings[t_State->selectedSetting];
					if (t_Setting.settingtype == TrackerSystemSettingType_SettingBool)
					{
						// Bools toggle directly instead of opening the editor.
						t_Setting.settingBool.value = !t_Setting.settingBool.value;
						const manus::SdkResult t_Result = manus::Trackers::SetSystems(t_State->systems);
						if (!t_Result.Ok()) Status::Error("Failed to apply setting: " + t_Result.Description());
						RefreshSystems(*t_State);
						RebuildSettingList(*t_State);
						return true;
					}
					t_State->input.clear();
					t_State->mode = Mode::EditSetting;
					SetKeyboardCapture(true);
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::PickUser)
			{
				if (t_IsC) { t_State->mode = Mode::Normal; t_State->pending = Pending::None; Status::Clear(); return true; }
				if (p_Event == Event::Return && t_State->selectedUser < (int)t_State->userIds.size())
				{
					if (t_State->pending == Pending::Assign)
					{
						t_State->mode = Mode::PickRole;
						Status::Info("Pick the role this tracker follows.");
						return true;
					}
					// Offset: move on to the small tool that lets the user type
					// the actual translation, instead of forcing the example values.
					t_State->pendingOffsetUserId = t_State->userIds[t_State->selectedUser];
					t_State->offsetInput.clear();
					t_State->mode = Mode::EnterOffset;
					SetKeyboardCapture(true);
					Status::Info("Type the offset as \"x y z\" in meters, or leave empty for the example.");
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::PickRole)
			{
				if (t_IsC) { t_State->mode = Mode::Normal; t_State->pending = Pending::None; Status::Clear(); return true; }
				if (p_Event == Event::Return)
				{
					const uint32_t t_UserId = t_State->userIds[t_State->selectedUser];
					const TrackerType t_Role = t_State->roles[t_State->selectedRole];
					const manus::SdkResult t_Result = manus::Trackers::AssignToUser(
						t_State->pendingTrackerId, t_UserId, t_Role);
					if (!t_Result.Ok()) Status::Error("Failed to assign tracker: " + t_Result.Description());
					else Status::Success("Assigned \"" + t_State->pendingTrackerId + "\" to user "
						+ Id(t_UserId) + " as " + manus::Trackers::TypeName(t_Role) + ".");
					t_State->mode = Mode::Normal;
					t_State->pending = Pending::None;
					return true;
				}
				return false;
			}

			// Normal mode.
			if (p_Event == Event::Character('s') || p_Event == Event::Character('S'))
			{
				RefreshSystems(*t_State);
				t_State->mode = Mode::Systems;
				return true;
			}
			if (p_Event == Event::Character('o') || p_Event == Event::Character('O'))
			{
				if (t_State->testActive->exchange(!t_State->testActive->load()))
				{
					Status::Info("Test tracker stopped.");
					return true;
				}
				Status::Success("Sending \"Test Tracker\" into Core at ~30 Hz (slowly rising).");
				auto t_Active = t_State->testActive;
				std::thread([t_Active] {
					float t_Height = 0.0f;
					while (t_Active->load())
					{
						t_Height += 0.0005f;
						if (t_Height >= 10.0f) t_Height = 0.0f;
						if (!manus::Trackers::SendTestTracker(t_Height).Ok()) break;
						std::this_thread::sleep_for(std::chrono::milliseconds(33));
					}
					}).detach();
				return true;
			}
			if (p_Event == Event::Character('e') || p_Event == Event::Character('E'))
			{
				bool t_Enabled = false;
				float t_Seconds = 0.0f;
				manus::Trackers::GetTimeout(t_Enabled, t_Seconds);
				const manus::SdkResult t_Result = manus::Trackers::SetTimeoutEnabled(!t_Enabled);
				if (!t_Result.Ok()) Status::Error("Failed to switch timeout: " + t_Result.Description());
				else Status::Success(std::string("Tracker timeout ") + (!t_Enabled ? "Enabled." : "Disabled."));
				return true;
			}
			if (p_Event == Event::Character('l') || p_Event == Event::Character('L'))
			{
				bool t_Enabled = false;
				float t_Seconds = 0.0f;
				manus::Trackers::GetTimeout(t_Enabled, t_Seconds);
				const float t_NewSeconds = t_Seconds == 30.0f ? 10.0f : 30.0f;
				const manus::SdkResult t_Result = manus::Trackers::SetTimeoutDuration(t_NewSeconds);
				if (!t_Result.Ok()) Status::Error("Failed to switch duration: " + t_Result.Description());
				else Status::Success("Tracker timeout duration set to " + std::to_string((int)t_NewSeconds) + " s.");
				return true;
			}

			if (t_State->trackerIds.empty()) return false;
			const std::string t_TrackerId = t_State->trackerIds[t_State->selectedTracker];

			if (p_Event == Event::Character('a') || p_Event == Event::Character('A'))
			{
				RebuildUserList(*t_State);
				t_State->pendingTrackerId = t_TrackerId;
				t_State->pending = TrackersState::Pending::Assign;
				t_State->mode = Mode::PickUser;
				Status::Info("Pick the user to assign \"" + t_TrackerId + "\" to.");
				return true;
			}
			if (p_Event == Event::Character('u') || p_Event == Event::Character('U'))
			{
				const manus::SdkResult t_Result = manus::Trackers::Unassign(t_TrackerId);
				if (!t_Result.Ok()) Status::Error("Failed to unassign tracker: " + t_Result.Description());
				else Status::Success("Unassigned \"" + t_TrackerId + "\".");
				return true;
			}
			if (p_Event == Event::Character('t') || p_Event == Event::Character('T'))
			{
				RebuildUserList(*t_State);
				t_State->pending = TrackersState::Pending::Offset;
				t_State->mode = Mode::PickUser;
				Status::Info("Tracker offset tells Core where the tracker sits relative to the glove. "
					"Pick the user, then enter the offset (or use the MANUS Universal Mount example).");
				return true;
			}
			return false;
			});
	}
}
