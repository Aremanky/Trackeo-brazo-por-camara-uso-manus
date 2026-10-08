#include "ui/screens/UsersScreen.hpp"

#include "sdk/Connection.hpp"
#include "sdk/Devices.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/Users.hpp"

#include "ui/components/DeviceSelector.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/KeyboardCapture.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/component_options.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>

#include <memory>
#include <string>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct UsersState
		{
			enum class Mode { Normal, AddName, RenameName, PickDongle, PickGlove, PickUnassignSide };
			Mode mode = Mode::Normal;
			int tab = 0; // 0 = user list, 1 = text input, 2 = dongle picker, 3 = glove picker

			int selected = 0;
			std::vector<uint32_t> ids;
			std::vector<std::string> labels;

			std::string input;
			uint32_t targetUserId = 0;
			uint32_t confirmRemoveId = 0;

			bool autoAssign = false;
			bool autoAssignKnown = false;

			std::shared_ptr<DeviceSelectorState> dongleSel;
			std::shared_ptr<DeviceSelectorState> gloveSel;
		};

		void RebuildUserList(UsersState& p_State)
		{
			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
			p_State.ids.clear();
			p_State.labels.clear();
			for (uint32_t i = 0; i < t_Landscape.users.userCount; ++i)
			{
				const UserLandscapeData& t_User = t_Landscape.users.users[i];
				std::string t_Label = std::to_string(i + 1) + ". "
					+ (t_User.name[0] != '\0' ? std::string(t_User.name) : "(unnamed)")
					+ "  (id " + Id(t_User.id) + ")"
					+ "  dongle: " + (t_User.dongleID != 0 ? Id(t_User.dongleID) : "-")
					+ "  L: " + (t_User.leftGloveID != 0 ? Id(t_User.leftGloveID) : "-")
					+ "  R: " + (t_User.rightGloveID != 0 ? Id(t_User.rightGloveID) : "-");
				p_State.ids.push_back(t_User.id);
				p_State.labels.push_back(t_Label);
			}
			if (p_State.selected >= (int)p_State.ids.size()) p_State.selected = (int)p_State.ids.size() - 1;
			if (p_State.selected < 0) p_State.selected = 0;
		}

		bool TryGetUser(uint32_t p_UserId, UserLandscapeData& p_OutUser)
		{
			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
			for (uint32_t i = 0; i < t_Landscape.users.userCount; ++i)
			{
				if (t_Landscape.users.users[i].id == p_UserId)
				{
					p_OutUser = t_Landscape.users.users[i];
					return true;
				}
			}
			return false;
		}

		bool HasSelectedUser(const UsersState& p_State)
		{
			return p_State.selected >= 0 && p_State.selected < (int)p_State.ids.size();
		}

		uint32_t SelectedUserId(const UsersState& p_State)
		{
			return HasSelectedUser(p_State) ? p_State.ids[p_State.selected] : 0;
		}

		void RefreshAutoAssignment(UsersState& p_State)
		{
			p_State.autoAssignKnown = manus::Users::GetAutoAssignment(p_State.autoAssign).Ok();
		}

		void LeaveInputMode(UsersState& p_State)
		{
			p_State.mode = UsersState::Mode::Normal;
			SetKeyboardCapture(false);
		}

		void CommitInput(UsersState& p_State)
		{
			const std::string t_Name = p_State.input;
			if (t_Name.empty())
			{
				Status::Info("Name is empty - user not " +
					std::string(p_State.mode == UsersState::Mode::AddName ? "created." : "renamed."));
				LeaveInputMode(p_State);
				return;
			}

			if (p_State.mode == UsersState::Mode::AddName)
			{
				uint32_t t_NewId = 0;
				const manus::SdkResult t_Result = manus::Users::Add(t_Name, t_NewId);
				if (t_Result.Ok()) Status::Success("Created user \"" + t_Name + "\" with id " + Id(t_NewId) + ".");
				else Status::Error("Failed to create user: " + t_Result.Description());
			}
			else if (p_State.mode == UsersState::Mode::RenameName)
			{
				const manus::SdkResult t_Result = manus::Users::Rename(p_State.targetUserId, t_Name);
				if (t_Result.Ok()) Status::Success("Renamed user " + Id(p_State.targetUserId) + " to \"" + t_Name + "\".");
				else Status::Error("Failed to rename user: " + t_Result.Description());
			}
			LeaveInputMode(p_State);
		}

		std::string ModeHints(const UsersState& p_State)
		{
			switch (p_State.mode)
			{
			case UsersState::Mode::AddName:
			case UsersState::Mode::RenameName:
				return " type a name   [Enter] confirm   [Esc] cancel ";
			case UsersState::Mode::PickDongle:
				return " [Up/Down] pick dongle   [Enter] assign   [C] cancel ";
			case UsersState::Mode::PickGlove:
				return " [Up/Down] pick glove   [Enter] assign   [C] cancel ";
			case UsersState::Mode::PickUnassignSide:
				return " [L] unassign left glove   [R] unassign right glove   [C] cancel ";
			default:
				break;
			}
			if (p_State.confirmRemoveId != 0)
				return " [Y] confirm removal   [C] cancel ";
			return " [A] add   [N] rename   [R] remove   [I]/[K] move   [D]/[U] dongle   [G]/[W] glove   [T] auto-assign ";
		}
	}

	Component MakeUsersScreen()
	{
		auto t_State = std::make_shared<UsersState>();
		t_State->dongleSel = MakeDeviceSelectorState(DeviceKind::Dongles);
		t_State->gloveSel = MakeDeviceSelectorState(DeviceKind::Gloves);

		Component t_UserMenu = Menu(&t_State->labels, &t_State->selected);

		InputOption t_InputOption;
		t_InputOption.multiline = false;
		t_InputOption.on_enter = [t_State] { CommitInput(*t_State); };
		Component t_Input = Input(&t_State->input, "user name", t_InputOption);

		Component t_DongleSelector = MakeDeviceSelector(t_State->dongleSel);
		Component t_GloveSelector = MakeDeviceSelector(t_State->gloveSel);

		Component t_Areas = Container::Tab(
			{ t_UserMenu, t_Input, t_DongleSelector, t_GloveSelector }, &t_State->tab);

		Component t_Root = Renderer(t_Areas, [t_State, t_UserMenu, t_Input, t_DongleSelector, t_GloveSelector] {
			RebuildUserList(*t_State);
			if (!t_State->autoAssignKnown) RefreshAutoAssignment(*t_State);

			switch (t_State->mode)
			{
			case UsersState::Mode::AddName:
			case UsersState::Mode::RenameName: t_State->tab = 1; break;
			case UsersState::Mode::PickDongle: t_State->tab = 2; break;
			case UsersState::Mode::PickGlove: t_State->tab = 3; break;
			default: t_State->tab = 0; break;
			}

			Element t_Right;
			switch (t_State->mode)
			{
			case UsersState::Mode::AddName:
				t_Right = window(text(" New user name "), t_Input->Render());
				break;
			case UsersState::Mode::RenameName:
				t_Right = window(text(" Rename user " + Id(t_State->targetUserId) + " "), t_Input->Render());
				break;
			case UsersState::Mode::PickDongle:
				t_Right = window(text(" Assign a dongle to user " + Id(t_State->targetUserId) + " "),
					t_DongleSelector->Render());
				break;
			case UsersState::Mode::PickGlove:
				t_Right = window(text(" Assign a glove to user " + Id(t_State->targetUserId) + " "),
					t_GloveSelector->Render());
				break;
			case UsersState::Mode::PickUnassignSide:
				t_Right = window(text(" Unassign glove "),
					text("User " + Id(t_State->targetUserId)
						+ " has two gloves - press [L] or [R]."));
				break;
			default:
			{
				Elements t_Info = {
					text("Auto-assignment: " + std::string(!t_State->autoAssignKnown
						? "unknown" : t_State->autoAssign ? "Enabled" : "Disabled")),
				};
				if (manus::Connection::Mode() == manus::ConnectionMode::Remote)
					t_Info.push_back(text("(Core Remote keeps auto-assignment disabled.)") | dim);

				// Gloves nobody owns stream no skeleton/ergonomics/gesture
				// data - surface them here, where assigning is one key away.
				const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
				Elements t_Unassigned;
				for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
				{
					UserLandscapeData t_User{};
					if (!manus::Users::TryFindUserForGlove(t_Landscape, t_Glove.id, t_User))
						t_Unassigned.push_back(text("  Glove " + Id(t_Glove.id) + "  "
							+ manus::Devices::SideName(t_Glove.side)));
				}
				if (!t_Unassigned.empty())
				{
					t_Info.push_back(separator());
					t_Info.push_back(text("Without a user (no data flows):") | dim);
					for (Element& t_Line : t_Unassigned)
						t_Info.push_back(t_Line | dim);
				}
				t_Info.push_back(filler());
				t_Right = vbox(std::move(t_Info));
				break;
			}
			}

			return vbox({
				Status::Render(),
				hbox({
					window(text(" Users "),
						t_State->labels.empty()
							? text("(no users)") | dim
							: t_UserMenu->Render() | frame) | flex,
					t_Right | size(WIDTH, GREATER_THAN,
						t_State->mode == UsersState::Mode::Normal ? 30 : 56),
					}) | flex,
				text(ModeHints(*t_State)) | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			using Mode = UsersState::Mode;

			// Text-input modes: Enter is handled by the Input's on_enter;
			// Esc cancels. Everything else goes to the Input component.
			if (t_State->mode == Mode::AddName || t_State->mode == Mode::RenameName)
			{
				if (p_Event == Event::Escape)
				{
					LeaveInputMode(*t_State);
					Status::Clear();
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::PickDongle)
			{
				if (p_Event == Event::Return)
				{
					if (HasSelection(*t_State->dongleSel))
					{
						const uint32_t t_DongleId = SelectedId(*t_State->dongleSel);
						const manus::SdkResult t_Result = manus::Users::AssignDongle(t_State->targetUserId, t_DongleId);
						if (t_Result.Ok()) Status::Success("Assigned dongle " + Id(t_DongleId)
							+ " to user " + Id(t_State->targetUserId) + ".");
						else Status::Error("Failed to assign dongle: " + t_Result.Description());
					}
					t_State->mode = Mode::Normal;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C'))
				{
					t_State->mode = Mode::Normal;
					Status::Clear();
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::PickGlove)
			{
				if (p_Event == Event::Return)
				{
					if (HasSelection(*t_State->gloveSel))
					{
						const uint32_t t_GloveId = SelectedId(*t_State->gloveSel);
						Side t_Side = Side_Left;
						for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
							if (t_Glove.id == t_GloveId) { t_Side = t_Glove.side; break; }

						const manus::SdkResult t_Result = manus::Users::AssignGlove(t_State->targetUserId, t_GloveId, t_Side);
						if (t_Result.Ok()) Status::Success("Assigned glove " + Id(t_GloveId)
							+ " to user " + Id(t_State->targetUserId) + ".");
						else Status::Error("Failed to assign glove: " + t_Result.Description());
					}
					t_State->mode = Mode::Normal;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C'))
				{
					t_State->mode = Mode::Normal;
					Status::Clear();
					return true;
				}
				return false;
			}

			if (t_State->mode == Mode::PickUnassignSide)
			{
				Side t_Side = Side_Invalid;
				if (p_Event == Event::Character('l') || p_Event == Event::Character('L')) t_Side = Side_Left;
				if (p_Event == Event::Character('r') || p_Event == Event::Character('R')) t_Side = Side_Right;
				if (t_Side != Side_Invalid)
				{
					const manus::SdkResult t_Result = manus::Users::AssignGlove(t_State->targetUserId, 0, t_Side);
					if (t_Result.Ok()) Status::Success(std::string("Unassigned ")
						+ (t_Side == Side_Left ? "left" : "right") + " glove from user "
						+ Id(t_State->targetUserId) + ".");
					else Status::Error("Failed to unassign glove: " + t_Result.Description());
					t_State->mode = Mode::Normal;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C'))
				{
					t_State->mode = Mode::Normal;
					Status::Clear();
					return true;
				}
				return false;
			}

			// Remove confirmation.
			if (t_State->confirmRemoveId != 0)
			{
				if (p_Event == Event::Character('y') || p_Event == Event::Character('Y'))
				{
					const manus::SdkResult t_Result = manus::Users::Remove(t_State->confirmRemoveId);
					if (t_Result.Ok()) Status::Success("Removed user " + Id(t_State->confirmRemoveId) + ".");
					else Status::Error("Failed to remove user: " + t_Result.Description());
					t_State->confirmRemoveId = 0;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C')
					|| p_Event == Event::Character('n') || p_Event == Event::Character('N'))
				{
					t_State->confirmRemoveId = 0;
					Status::Clear();
					return true;
				}
				return false;
			}

			// Normal mode.
			if (p_Event == Event::Character('a') || p_Event == Event::Character('A'))
			{
				t_State->mode = Mode::AddName;
				t_State->input.clear();
				SetKeyboardCapture(true);
				Status::Info("Type a name for the new user.");
				return true;
			}
			if (p_Event == Event::Character('t') || p_Event == Event::Character('T'))
			{
				const bool t_NewValue = !t_State->autoAssign;
				const manus::SdkResult t_Result = manus::Users::SetAutoAssignment(t_NewValue);
				RefreshAutoAssignment(*t_State);
				if (!t_Result.Ok())
					Status::Error("Failed to change auto-assignment: " + t_Result.Description());
				else if (t_State->autoAssign != t_NewValue)
					Status::Info(std::string("Core kept auto-assignment ")
						+ (t_State->autoAssign ? "Enabled" : "Disabled")
						+ (manus::Connection::Mode() == manus::ConnectionMode::Remote
							? " - Core Remote does not allow enabling it." : "."));
				else
					Status::Success(std::string("Auto-assignment ") + (t_State->autoAssign ? "Enabled." : "Disabled."));
				return true;
			}

			if (!HasSelectedUser(*t_State)) return false;
			const uint32_t t_UserId = SelectedUserId(*t_State);

			if (p_Event == Event::Character('n') || p_Event == Event::Character('N'))
			{
				UserLandscapeData t_User{};
				t_State->mode = Mode::RenameName;
				t_State->targetUserId = t_UserId;
				t_State->input = TryGetUser(t_UserId, t_User) ? t_User.name : "";
				SetKeyboardCapture(true);
				Status::Info("Type the new name for user " + Id(t_UserId) + ".");
				return true;
			}
			if (p_Event == Event::Character('r') || p_Event == Event::Character('R'))
			{
				t_State->confirmRemoveId = t_UserId;
				Status::Info("Remove user " + Id(t_UserId) + "? [Y] confirm, [C] cancel.");
				return true;
			}
			if (p_Event == Event::Character('i') || p_Event == Event::Character('I'))
			{
				const manus::SdkResult t_Result = manus::Users::MoveUp(t_UserId);
				if (!t_Result.Ok()) Status::Error("Failed to move user: " + t_Result.Description());
				return true;
			}
			if (p_Event == Event::Character('k') || p_Event == Event::Character('K'))
			{
				const manus::SdkResult t_Result = manus::Users::MoveDown(t_UserId);
				if (!t_Result.Ok()) Status::Error("Failed to move user: " + t_Result.Description());
				return true;
			}
			if (p_Event == Event::Character('d') || p_Event == Event::Character('D'))
			{
				t_State->mode = Mode::PickDongle;
				t_State->targetUserId = t_UserId;
				Status::Info("Pick a dongle for user " + Id(t_UserId) + ".");
				return true;
			}
			if (p_Event == Event::Character('u') || p_Event == Event::Character('U'))
			{
				UserLandscapeData t_User{};
				if (TryGetUser(t_UserId, t_User) && t_User.dongleID == 0)
				{
					Status::Info("User " + Id(t_UserId) + " has no dongle assigned.");
					return true;
				}
				const manus::SdkResult t_Result = manus::Users::AssignDongle(t_UserId, 0);
				if (t_Result.Ok()) Status::Success("Unassigned dongle from user " + Id(t_UserId) + ".");
				else Status::Error("Failed to unassign dongle: " + t_Result.Description());
				return true;
			}
			if (p_Event == Event::Character('g') || p_Event == Event::Character('G'))
			{
				t_State->mode = Mode::PickGlove;
				t_State->targetUserId = t_UserId;
				Status::Info("Pick a glove for user " + Id(t_UserId) + ".");
				return true;
			}
			if (p_Event == Event::Character('w') || p_Event == Event::Character('W'))
			{
				UserLandscapeData t_User{};
				if (!TryGetUser(t_UserId, t_User)) return true;
				const bool t_HasLeft = t_User.leftGloveID != 0;
				const bool t_HasRight = t_User.rightGloveID != 0;
				if (!t_HasLeft && !t_HasRight)
				{
					Status::Info("User " + Id(t_UserId) + " has no gloves assigned.");
					return true;
				}
				if (t_HasLeft && t_HasRight)
				{
					t_State->mode = Mode::PickUnassignSide;
					t_State->targetUserId = t_UserId;
					Status::Info("Unassign which glove? [L] left, [R] right.");
					return true;
				}
				const Side t_Side = t_HasLeft ? Side_Left : Side_Right;
				const manus::SdkResult t_Result = manus::Users::AssignGlove(t_UserId, 0, t_Side);
				if (t_Result.Ok()) Status::Success(std::string("Unassigned ")
					+ (t_HasLeft ? "left" : "right") + " glove from user " + Id(t_UserId) + ".");
				else Status::Error("Failed to unassign glove: " + t_Result.Description());
				return true;
			}
			return false;
			});
	}
}
