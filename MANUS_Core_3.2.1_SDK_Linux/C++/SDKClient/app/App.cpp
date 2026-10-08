#include "app/App.hpp"

#include "sdk/Connection.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/SkeletonsRaw.hpp"
#include "sdk/SkeletonsRetargeted.hpp"
#include "sdk/Streams.hpp"
#include "sdk/Trackers.hpp"

#include "ui/components/Focusable.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/KeyboardCapture.hpp"
#include "ui/components/LogPanel.hpp"
#include "ui/screens/CalibrationScreen.hpp"
#include "ui/screens/DevicesScreen.hpp"
#include "ui/screens/ErgonomicsScreen.hpp"
#include "ui/screens/GesturesScreen.hpp"
#include "ui/screens/LandscapeBrowser.hpp"
#include "ui/screens/LicenseScreen.hpp"
#include "ui/screens/SkeletonsScreen.hpp"
#include "ui/screens/TimecodeScreen.hpp"
#include "ui/screens/TrackersScreen.hpp"
#include "ui/screens/UsersScreen.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/component_options.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/component/mouse.hpp>
#include <ftxui/component/screen_interactive.hpp>
#include <ftxui/dom/elements.hpp>

#include <atomic>
#include <chrono>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace ftxui;

namespace app
{
	namespace
	{
		enum class Phase { ModeSelect, Working, Stalled, HostList, Home, InScreen };

		struct Shell
		{
			std::mutex mutex;
			Phase phase = Phase::ModeSelect;
			std::string status = "Select how to connect to MANUS Core.";
			manus::ConnectionMode mode = manus::ConnectionMode::Local;
			std::vector<ManusHost> hosts;
			std::vector<std::string> hostLabels;
		};

		Shell g_Shell;
		ScreenInteractive* g_Screen = nullptr;

		void Redraw()
		{
			if (g_Screen != nullptr) g_Screen->PostEvent(Event::Custom);
		}

		void SetPhase(Phase p_Phase, const std::string& p_Status)
		{
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				g_Shell.phase = p_Phase;
				g_Shell.status = p_Status;
			}
			Redraw();
		}

		// --- Startup flows (run on a worker thread; SDK calls block) ---------

		void ConnectIntegratedFlow()
		{
			SetPhase(Phase::Working, "Starting Core Integrated...");
			const manus::SdkResult t_Result = manus::Connection::ConnectIntegrated();
			if (!t_Result.Ok())
			{
				SetPhase(Phase::Stalled, "Failed to start Core Integrated: " + t_Result.Description());
				return;
			}
			SetPhase(Phase::Home, "");
		}

		void ConnectFlow(ManusHost p_Host)
		{
			SetPhase(Phase::Working, "Connecting to \"" + std::string(p_Host.hostName) + "\"...");
			const manus::SdkResult t_Result = manus::Connection::Connect(p_Host);
			if (!t_Result.Ok())
			{
				SetPhase(Phase::Stalled, "Failed to connect: " + t_Result.Description());
				return;
			}
			SetPhase(Phase::Home, "");
		}

		void ScanFlow()
		{
			manus::ConnectionMode t_Mode;
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				t_Mode = g_Shell.mode;
			}

			SetPhase(Phase::Working, t_Mode == manus::ConnectionMode::Local
				? "Looking for a MANUS Core on this machine..."
				: "Looking for MANUS Core hosts on the network...");

			std::vector<ManusHost> t_Hosts;
			const manus::SdkResult t_Result = manus::Connection::ScanForHosts(t_Hosts);
			if (!t_Result.Ok())
			{
				SetPhase(Phase::Stalled, "Host scan failed: " + t_Result.Description());
				return;
			}
			if (t_Hosts.empty())
			{
				SetPhase(Phase::Stalled, "No MANUS Core hosts found.");
				return;
			}

			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				g_Shell.hosts = t_Hosts;
				g_Shell.hostLabels.clear();
				for (const ManusHost& t_Host : t_Hosts)
				{
					g_Shell.hostLabels.push_back(
						std::string(t_Host.hostName) + "  (" + t_Host.ipAddress + ", Core "
						+ std::to_string(t_Host.manusCoreVersion.major) + "."
						+ std::to_string(t_Host.manusCoreVersion.minor) + "."
						+ std::to_string(t_Host.manusCoreVersion.patch) + ")");
				}
			}

			if (t_Mode == manus::ConnectionMode::Local)
			{
				// Local mode: connect straight to the Core on this machine.
				ConnectFlow(t_Hosts[0]);
				return;
			}
			SetPhase(Phase::HostList, "Pick a host to connect to.");
		}

		void StartModeFlow(manus::ConnectionMode p_Mode)
		{
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				g_Shell.mode = p_Mode;
			}

			SetPhase(Phase::Working, "Initializing the SDK...");
			// --8<-- [start:register-callbacks]
			manus::SdkResult t_Result = manus::Connection::Initialize(p_Mode);
			if (t_Result.Ok()) t_Result = manus::Logs::Register();
			if (t_Result.Ok()) t_Result = manus::LandscapeCache::Register();
			if (t_Result.Ok()) t_Result = manus::GestureStream::Register();
			if (t_Result.Ok()) t_Result = manus::StreamTime::Register();
			if (t_Result.Ok()) t_Result = manus::Trackers::RegisterStream();
			if (t_Result.Ok()) t_Result = manus::SkeletonsRetargeted::RegisterStream();
			if (t_Result.Ok()) t_Result = manus::SkeletonsRaw::RegisterStream();
			if (t_Result.Ok()) t_Result = manus::RawDeviceStream::Register();
			// --8<-- [end:register-callbacks]
			if (!t_Result.Ok())
			{
				SetPhase(Phase::Stalled, "SDK initialization failed: " + t_Result.Description());
				return;
			}

			if (p_Mode == manus::ConnectionMode::Integrated)
			{
				ConnectIntegratedFlow();
				return;
			}
			ScanFlow();
		}

		void RetryFlow()
		{
			manus::ConnectionMode t_Mode;
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				t_Mode = g_Shell.mode;
			}
			if (t_Mode == manus::ConnectionMode::Integrated) ConnectIntegratedFlow();
			else ScanFlow();
		}

		// --- Chrome -----------------------------------------------------------

		Element RenderHeader(const std::string& p_Breadcrumb)
		{
			const manus::Connection::Info t_Info = manus::Connection::CurrentInfo();
			std::string t_Right = "Not connected";
			if (t_Info.connected)
			{
				t_Right = t_Info.hostName.empty()
					? "Connected (Integrated)"
					: "Connected to " + t_Info.hostName;
				t_Right += "   Session " + ui::Id(t_Info.sessionId);
			}
			return hbox({
				text(" MANUS SDKClient ") | bold,
				text(p_Breadcrumb),
				filler(),
				text(t_Right + " "),
				}) | inverted;
		}
	}

	int Run()
	{
		ScreenInteractive t_Screen = ScreenInteractive::Fullscreen();
		t_Screen.TrackMouse(true);
		g_Screen = &t_Screen;

		// Any data change (log line, landscape update, connect/disconnect)
		// requests a redraw; a disconnect additionally interrupts navigation.
		manus::Logs::SetOnChanged(Redraw);
		manus::LandscapeCache::SetOnChanged(Redraw);
		manus::Connection::SetOnChanged([] {
			if (!manus::Connection::IsConnected())
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				if (g_Shell.phase == Phase::Home || g_Shell.phase == Phase::InScreen)
				{
					g_Shell.phase = Phase::Stalled;
					g_Shell.status = "Disconnected from MANUS Core.";
				}
			}
			Redraw();
			});

		std::thread t_Worker;
		auto t_RestartWorker = [&](std::function<void()> p_Job) {
			if (t_Worker.joinable()) t_Worker.join();
			t_Worker = std::thread(std::move(p_Job));
			};

		// --- Screen registry ---------------------------------------------------
		struct ScreenEntry { std::string name; Component component; };
		std::vector<ScreenEntry> t_Entries;
		t_Entries.push_back({ "Devices", ui::MakeDevicesScreen() });
		t_Entries.push_back({ "Users", ui::MakeUsersScreen() });
		t_Entries.push_back({ "Calibration", ui::MakeCalibrationScreen() });
		t_Entries.push_back({ "Skeletons", ui::MakeSkeletonsScreen() });
		t_Entries.push_back({ "Trackers", ui::MakeTrackersScreen() });
		t_Entries.push_back({ "Ergonomics", ui::MakeErgonomicsScreen() });
		t_Entries.push_back({ "Gestures", ui::MakeGesturesScreen() });
		t_Entries.push_back({ "Timecode", ui::MakeTimecodeScreen() });
		t_Entries.push_back({ "License", ui::MakeLicenseScreen() });
		t_Entries.push_back({ "Landscape Browser", ui::MakeLandscapeBrowser() });

		std::vector<std::string> t_ScreenNames;
		Components t_ScreenComponents;
		for (const ScreenEntry& t_Entry : t_Entries)
		{
			t_ScreenNames.push_back(t_Entry.name);
			// AlwaysFocusable keeps a screen's hotkeys working even when its
			// menus are empty (FTXUI drops key events for unfocusable subtrees).
			t_ScreenComponents.push_back(ui::AlwaysFocusable(t_Entry.component));
		}

		// --- Menus -------------------------------------------------------------
		std::vector<std::string> t_Modes = {
			"Core Integrated - run standalone, no separate MANUS Core needed",
			"Core Local     - connect to the MANUS Core running on this machine",
			"Core Remote    - search the network for MANUS Core hosts",
		};
		int t_SelectedMode = 1;
		MenuOption t_ModeOption = MenuOption::Vertical();
		// FTXUI's highlight bar follows focused_entry (default 0), not selected;
		// keep it in sync with the non-zero initial selection.
		t_ModeOption.focused_entry = t_SelectedMode;
		t_ModeOption.on_enter = [&] {
			const manus::ConnectionMode t_Mode =
				t_SelectedMode == 0 ? manus::ConnectionMode::Integrated :
				t_SelectedMode == 1 ? manus::ConnectionMode::Local :
				manus::ConnectionMode::Remote;
			t_RestartWorker([t_Mode] { StartModeFlow(t_Mode); });
			};
		Component t_ModeMenu = Menu(&t_Modes, &t_SelectedMode, t_ModeOption);

		int t_SelectedHost = 0;
		MenuOption t_HostOption = MenuOption::Vertical();
		t_HostOption.on_enter = [&] {
			std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
			if (g_Shell.phase == Phase::HostList &&
				t_SelectedHost >= 0 && t_SelectedHost < (int)g_Shell.hosts.size())
			{
				ManusHost t_Host = g_Shell.hosts[t_SelectedHost];
				t_RestartWorker([t_Host] { ConnectFlow(t_Host); });
			}
			};
		Component t_HostMenu = Menu(&g_Shell.hostLabels, &t_SelectedHost, t_HostOption);

		int t_SelectedScreen = 0;
		int t_ActiveScreen = 0;
		MenuOption t_HomeOption = MenuOption::Vertical();
		t_HomeOption.on_enter = [&] {
			t_ActiveScreen = t_SelectedScreen;
			SetPhase(Phase::InScreen, "");
			};
		Component t_HomeMenu = Menu(&t_ScreenNames, &t_SelectedScreen, t_HomeOption);

		Component t_ScreenTab = Container::Tab(t_ScreenComponents, &t_ActiveScreen);

		// Keyboard focus follows the phase.
		int t_ActiveArea = 0;
		Component t_Areas = Container::Tab(
			{ t_ModeMenu, t_HostMenu, t_HomeMenu, t_ScreenTab }, &t_ActiveArea);

		// A sibling, not a child, of t_Areas: it is never part of the
		// keyboard-focus cycle (Renderer/CatchEvent without a focusable child
		// is not Focusable(), so Tab-navigation skips it automatically) or the
		// active child of t_RootChildren, so the global CatchEvent below forwards
		// mouse wheel events to it directly - that way the log scrolls with the
		// wheel no matter where the cursor is or which screen has focus (menus
		// would otherwise claim the wheel first to move their own selection).
		Component t_LogPanel = ui::MakeLogPanel(6);
		Component t_RootChildren = Container::Vertical({ t_Areas, t_LogPanel });

		int t_Frame = 0;
		Component t_Root = Renderer(t_RootChildren, [&] {
			std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
			++t_Frame;

			Element t_Body;
			std::string t_Breadcrumb;
			std::string t_Hints = " [Esc] quit ";
			switch (g_Shell.phase)
			{
			case Phase::ModeSelect:
				t_ActiveArea = 0;
				t_Body = vbox({ text("How do you want to connect?") | bold, t_ModeMenu->Render() }) | flex;
				t_Hints = " [Up/Down] select   [Enter] confirm   [Esc] quit ";
				break;
			case Phase::Working:
				t_Body = hbox({ spinner(2, t_Frame / 2), text(" " + g_Shell.status) }) | center | flex;
				break;
			case Phase::Stalled:
				t_Body = text(g_Shell.status) | center | flex;
				t_Hints = " [R] retry   [Esc] quit ";
				break;
			case Phase::HostList:
				t_ActiveArea = 1;
				t_Body = vbox({ text("Hosts found:") | bold, t_HostMenu->Render() | frame }) | flex;
				t_Hints = " [Up/Down] select   [Enter] connect   [R] rescan   [Esc] quit ";
				break;
			case Phase::Home:
				t_ActiveArea = 2;
				t_Breadcrumb = "- Menu";
				t_Body = vbox({ text("Menu") | bold, t_HomeMenu->Render() }) | flex;
				t_Hints = " [Up/Down] select   [Enter] open   [Esc] quit ";
				break;
			case Phase::InScreen:
				t_ActiveArea = 3;
				t_Breadcrumb = "- " + t_ScreenNames[t_ActiveScreen];
				t_Body = t_ScreenTab->Render() | flex;
				t_Hints = " [Q] back to menu   [Esc] quit ";
				break;
			}
			t_Hints += "  [mouse wheel] scroll log ";

			return vbox({
				RenderHeader(t_Breadcrumb),
				t_Body,
				t_LogPanel->Render(),
				text(t_Hints) | dim,
				});
			});

		t_Root = CatchEvent(t_Root, [&](Event p_Event) {
			// Mouse is only ever used to scroll the log (see the comment above
			// t_LogPanel); every other mouse event is swallowed right here so it
			// never reaches a menu (no hover highlight, no click-to-select).
			if (p_Event.is_mouse())
			{
				const Mouse& t_Mouse = p_Event.mouse();
				if (t_Mouse.button == Mouse::WheelUp || t_Mouse.button == Mouse::WheelDown
					|| t_Mouse.button == Mouse::WheelLeft || t_Mouse.button == Mouse::WheelRight)
				{
					t_LogPanel->OnEvent(p_Event);
				}
				return true;
			}

			// While a screen has an active text field, every key belongs to it
			// (typing "q" must not navigate, Esc cancels the field).
			if (ui::IsKeyboardCaptured()) return false;

			if (p_Event == Event::Escape)
			{
				t_Screen.Exit();
				return true;
			}
			if (p_Event == Event::Character('q') || p_Event == Event::Character('Q'))
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				if (g_Shell.phase == Phase::InScreen)
				{
					g_Shell.phase = Phase::Home;
					return true;
				}
				return false;
			}
			if (p_Event == Event::Character('r') || p_Event == Event::Character('R'))
			{
				std::lock_guard<std::mutex> t_Lock(g_Shell.mutex);
				if (g_Shell.phase == Phase::Stalled || g_Shell.phase == Phase::HostList)
				{
					t_RestartWorker(RetryFlow);
					return true;
				}
				return false;
			}
			return false;
			});

		// ~30 fps refresh so live data appears even without input events.
		std::atomic<bool> t_Running{ true };
		std::thread t_Refresh([&] {
			while (t_Running)
			{
				std::this_thread::sleep_for(std::chrono::milliseconds(33));
				t_Screen.PostEvent(Event::Custom);
			}
			});

		t_Screen.Loop(t_Root);

		t_Running = false;
		t_Refresh.join();
		if (t_Worker.joinable()) t_Worker.join();

		// Detach UI hooks before shutdown; SDK threads may still fire callbacks.
		g_Screen = nullptr;
		manus::Logs::SetOnChanged(nullptr);
		manus::LandscapeCache::SetOnChanged(nullptr);
		manus::Connection::SetOnChanged(nullptr);

		manus::Connection::Shutdown();
		return 0;
	}
}
