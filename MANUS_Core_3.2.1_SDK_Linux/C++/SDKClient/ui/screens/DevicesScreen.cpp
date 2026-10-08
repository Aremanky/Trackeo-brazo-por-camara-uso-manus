#include "ui/screens/DevicesScreen.hpp"

#include "sdk/Devices.hpp"
#include "sdk/Firmware.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/Streams.hpp"
#include "sdk/Users.hpp"

#include "ui/components/DeviceSelector.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/SkeletonSketch.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>

#include <array>
#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct DevicesState
		{
			std::shared_ptr<DeviceSelectorState> all;      // main device list
			std::shared_ptr<DeviceSelectorState> dongles;  // pair-to-dongle picker
			int tab = 0;                                   // 0 = main, 1 = dongle picker

			bool pickingDongle = false;
			uint32_t pairGloveId = 0;

			uint32_t confirmFirmwareId = 0;                // 0 = no confirmation pending
			bool confirmIsGlove = false;

			std::shared_ptr<std::atomic<bool>> hapticsBusy = std::make_shared<std::atomic<bool>>(false);
		};

		bool TryGetGlove(uint32_t p_GloveId, GloveLandscapeData& p_OutGlove)
		{
			for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
			{
				if (t_Glove.id == p_GloveId)
				{
					p_OutGlove = t_Glove;
					return true;
				}
			}
			return false;
		}

		std::string VersionString(const Version& p_Version)
		{
			return std::to_string(p_Version.major) + "."
				+ std::to_string(p_Version.minor) + "."
				+ std::to_string(p_Version.patch);
		}

		// Live raw sensor data of a glove: per-finger position and rotation.
		// Not every glove family streams this - e.g. Prime gloves and Quantum Metagloves don't, so absence here doesn't necessarily mean the data is
		// just late.
		Element RenderRawSensors(uint32_t p_GloveId)
		{
			RawDeviceData t_Data{};
			if (!manus::RawDeviceStream::LatestForDevice(p_GloveId, t_Data))
				return text("(no raw sensor data - either none has arrived yet, or this glove type doesn't provide it)") | dim;

			static const char* const s_SensorNames[] = { "Thumb ", "Index ", "Middle", "Ring  ", "Pinky " };
			Elements t_Lines = { text("Raw sensors (pos x y z | rot x y z w):") | bold };
			for (uint32_t i = 0; i < t_Data.sensorCount; ++i)
			{
				const ManusTransform& t_Sensor = t_Data.sensorData[i];
				char t_Line[128];
				std::snprintf(t_Line, sizeof(t_Line), "%s %6.3f %6.3f %6.3f | %5.2f %5.2f %5.2f %5.2f",
					i < 5 ? s_SensorNames[i] : "Extra ",
					t_Sensor.position.x, t_Sensor.position.y, t_Sensor.position.z,
					t_Sensor.rotation.x, t_Sensor.rotation.y, t_Sensor.rotation.z, t_Sensor.rotation.w);
				t_Lines.push_back(text(t_Line));
			}
			char t_Device[96];
			std::snprintf(t_Device, sizeof(t_Device), "Device rotation:   %5.2f %5.2f %5.2f %5.2f",
				t_Data.rotation.x, t_Data.rotation.y, t_Data.rotation.z, t_Data.rotation.w);
			t_Lines.push_back(text(t_Device));

			// The same sensor data as a sketch - one colored dot per finger,
			// plus a white dot marking the device origin.
			std::vector<SketchPoint> t_Points;
			t_Points.push_back({ { 0.0f, 0.0f, 0.0f }, ftxui::Color::White });
			for (uint32_t i = 0; i < t_Data.sensorCount; ++i)
				t_Points.push_back({ t_Data.sensorData[i].position, FingerColor((int)i) });
			t_Lines.push_back(RenderSketch(t_Points, {}, 90, 56, 0.25f) | center);
			t_Lines.push_back(text("thumb index middle ring pinky") | dim | center);

			return vbox(std::move(t_Lines));
		}

		Element RenderDetail(const DevicesState& p_State)
		{
			if (!HasSelection(*p_State.all))
				return text("Select a device on the left.") | dim | center;

			const uint32_t t_Id = SelectedId(*p_State.all);

			if (SelectedIsGlove(*p_State.all))
			{
				for (const GloveLandscapeData& t_Glove : manus::LandscapeCache::GlovesSortedById())
				{
					if (t_Glove.id != t_Id) continue;
					// Skeleton/ergonomics/gesture data only flows for gloves
					// assigned to a user (raw sensor data flows regardless).
					UserLandscapeData t_User{};
					const bool t_HasUser = manus::Users::TryFindUserForGlove(t_Glove.id, t_User);
					return vbox({
						text("Glove " + Id(t_Glove.id)) | bold,
						text("Family:    " + std::string(manus::Devices::FamilyName(t_Glove.familyType))),
						text("Side:      " + std::string(manus::Devices::SideName(t_Glove.side))),
						text("Battery:   " + std::to_string(t_Glove.batteryPercentage) + "%"),
						text("Signal:    " + std::to_string(t_Glove.transmissionStrength) + "%"),
						text("Haptics:   " + std::string(t_Glove.isHaptics ? "yes" : "no")),
						text(t_Glove.pairedState == DevicePairedState_Paired
							? "Pairing:   paired to dongle " + Id(t_Glove.dongleID)
							: "Pairing:   " + std::string(manus::Devices::PairedStateName(t_Glove.pairedState))),
						text(t_HasUser
							? "User:      " + (t_User.name[0] != '\0' ? std::string(t_User.name) : "(unnamed)")
								+ " (id " + Id(t_User.id) + ")"
							: "User:      not assigned"),
						text("Firmware:  " + VersionString(t_Glove.firmwareVersion)),
						text("Hardware:  " + VersionString(t_Glove.hardwareVersion)),
						separator(),
						RenderRawSensors(t_Glove.id),
						});
				}
			}
			else
			{
				for (const DongleLandscapeData& t_Dongle : manus::LandscapeCache::DonglesSortedById())
				{
					if (t_Dongle.id != t_Id) continue;
					return vbox({
						text("Dongle " + Id(t_Dongle.id)) | bold,
						text("Family:      " + std::string(manus::Devices::FamilyName(t_Dongle.familyType))),
						text("License:     " + std::string(t_Dongle.licenseType[0] != '\0' ? t_Dongle.licenseType : "none")),
						text("Channel:     " + std::to_string(t_Dongle.channel)),
						text("Left glove:  " + Id(t_Dongle.leftGloveID)),
						text("Right glove: " + Id(t_Dongle.rightGloveID)),
						text("Firmware:    " + VersionString(t_Dongle.firmwareVersion)),
						text("Hardware:    " + VersionString(t_Dongle.hardwareVersion)),
						});
				}
			}
			return text("Device disappeared from the landscape.") | dim | center;
		}

		// One haptic frame every ~40 ms; vibration decays quickly, so patterns
		// are made by sending continuously.
		void PlayHapticsPattern(uint32_t p_GloveId, std::shared_ptr<std::atomic<bool>> p_Busy)
		{
			std::thread([p_GloveId, p_Busy] {
				auto t_Send = [p_GloveId](const std::array<float, 5>& p_Powers) {
					const bool t_Ok = manus::Devices::VibrateFingers(p_GloveId, p_Powers).Ok();
					std::this_thread::sleep_for(std::chrono::milliseconds(40));
					return t_Ok;
					};

				// Part 1: finger sweep - each finger buzzes alone, thumb to pinky.
				for (int t_Finger = 0; t_Finger < 5; ++t_Finger)
				{
					for (int t_Frame = 0; t_Frame < 6; ++t_Frame) // ~240 ms per finger
					{
						std::array<float, 5> t_Powers = {};
						t_Powers[t_Finger] = 0.8f;
						if (!t_Send(t_Powers))
						{
							Status::Error("Haptics failed on glove " + Id(p_GloveId) + ".");
							*p_Busy = false;
							return;
						}
					}
				}

				// Part 2: all fingers ramp up and back down (triangle, ~1.6 s).
				for (int t_Frame = 0; t_Frame < 40; ++t_Frame)
				{
					const float t_Power = t_Frame < 20 ? t_Frame / 20.0f : (40 - t_Frame) / 20.0f;
					std::array<float, 5> t_Powers;
					t_Powers.fill(t_Power);
					if (!t_Send(t_Powers)) break;
				}

				manus::Devices::VibrateFingers(p_GloveId, {});
				Status::Success("Haptic pattern finished on glove " + Id(p_GloveId) + ".");
				*p_Busy = false;
				}).detach();
		}

		void UpdateFirmware(uint32_t p_DeviceId, bool p_IsGlove)
		{
			// Core only answers the initial request; there is no progress
			// stream to show (a known SDK limitation, not a client choice).
			std::thread([p_DeviceId, p_IsGlove] {
				Status::Busy("Requesting firmware update for "
					+ std::string(p_IsGlove ? "glove " : "dongle ") + Id(p_DeviceId) + "...");
				bool t_Accepted = false;
				std::string t_Message;
				const manus::SdkResult t_Result = manus::Firmware::Update(p_DeviceId, t_Accepted, t_Message);
				if (!t_Result.Ok())
					Status::Error("Firmware update failed: " + t_Result.Description());
				else if (!t_Accepted)
					Status::Error("Core declined the firmware update: " + t_Message);
				else
					Status::Success("Firmware update started: " + t_Message);
				}).detach();
		}

		std::string ActionHints(const DevicesState& p_State)
		{
			if (p_State.pickingDongle)
				return " [Up/Down] pick dongle   [Enter] pair   [C] cancel ";
			if (p_State.confirmFirmwareId != 0)
				return " [Y] confirm firmware update   [C] cancel ";
			if (SelectedIsGlove(*p_State.all))
				return " [V] vibrate   [P] pair   [D] pair to dongle...   [U] unpair   [F] update firmware ";
			if (HasSelection(*p_State.all))
				return " [F] update firmware ";
			return "";
		}
	}

	Component MakeDevicesScreen()
	{
		auto t_State = std::make_shared<DevicesState>();
		t_State->all = MakeDeviceSelectorState(DeviceKind::GlovesAndDongles);
		t_State->dongles = MakeDeviceSelectorState(DeviceKind::Dongles);

		Component t_AllSelector = MakeDeviceSelector(t_State->all);
		Component t_DongleSelector = MakeDeviceSelector(t_State->dongles);
		Component t_Selectors = Container::Tab({ t_AllSelector, t_DongleSelector }, &t_State->tab);

		Component t_Root = Renderer(t_Selectors, [t_State, t_Selectors] {
			t_State->tab = t_State->pickingDongle ? 1 : 0;

			const std::string t_ListTitle = t_State->pickingDongle
				? " Pick a dongle for glove " + Id(t_State->pairGloveId) + " "
				: " Devices ";

			return vbox({
				Status::Render(),
				hbox({
					window(text(t_ListTitle), t_Selectors->Render()) | flex,
					RenderDetail(*t_State) | size(WIDTH, GREATER_THAN, 36),
					}) | flex,
				text(ActionHints(*t_State)) | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			// Pair-to-dongle picker mode.
			if (t_State->pickingDongle)
			{
				if (p_Event == Event::Return)
				{
					if (HasSelection(*t_State->dongles))
					{
						const uint32_t t_DongleId = SelectedId(*t_State->dongles);
						bool t_Accepted = false;
						const manus::SdkResult t_Result =
							manus::Devices::PairGloveToDongle(t_State->pairGloveId, t_DongleId, t_Accepted);
						if (!t_Result.Ok())
							Status::Error("Pairing failed: " + t_Result.Description());
						else if (!t_Accepted)
							Status::Error("Core declined the pairing request.");
						else
							Status::Success("Pairing glove " + Id(t_State->pairGloveId)
								+ " to dongle " + Id(t_DongleId) + "...");
					}
					t_State->pickingDongle = false;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C'))
				{
					t_State->pickingDongle = false;
					Status::Clear();
					return true;
				}
				return false; // arrows go to the dongle picker
			}

			// Firmware confirmation prompt.
			if (t_State->confirmFirmwareId != 0)
			{
				if (p_Event == Event::Character('y') || p_Event == Event::Character('Y'))
				{
					UpdateFirmware(t_State->confirmFirmwareId, t_State->confirmIsGlove);
					t_State->confirmFirmwareId = 0;
					return true;
				}
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C')
					|| p_Event == Event::Character('n') || p_Event == Event::Character('N'))
				{
					t_State->confirmFirmwareId = 0;
					Status::Clear();
					return true;
				}
				return false;
			}

			if (!HasSelection(*t_State->all)) return false;
			const uint32_t t_Id = SelectedId(*t_State->all);
			const bool t_IsGlove = SelectedIsGlove(*t_State->all);

			if ((p_Event == Event::Character('v') || p_Event == Event::Character('V')) && t_IsGlove)
			{
				if (t_State->hapticsBusy->exchange(true))
				{
					Status::Info("A haptic pattern is already playing.");
					return true;
				}
				Status::Busy("Playing haptic pattern on glove " + Id(t_Id) + " - finger sweep, then a ramp...");
				PlayHapticsPattern(t_Id, t_State->hapticsBusy);
				return true;
			}
			if ((p_Event == Event::Character('p') || p_Event == Event::Character('P')) && t_IsGlove)
			{
				GloveLandscapeData t_Glove{};
				if (!TryGetGlove(t_Id, t_Glove)) return true;
				if (t_Glove.pairedState == DevicePairedState_Paired)
				{
					Status::Info("Glove " + Id(t_Id) + " is already paired to dongle "
						+ Id(t_Glove.dongleID) + " - [U] unpair it first.");
					return true;
				}

				bool t_Accepted = false;
				const manus::SdkResult t_Result = manus::Devices::PairGlove(t_Id, t_Accepted);
				if (!t_Result.Ok()) Status::Error("Pairing failed: " + t_Result.Description());
				else if (!t_Accepted) Status::Error("Core declined pairing glove " + Id(t_Id) + ".");
				else Status::Success("Pairing glove " + Id(t_Id) + "...");
				return true;
			}
			if ((p_Event == Event::Character('d') || p_Event == Event::Character('D')) && t_IsGlove)
			{
				GloveLandscapeData t_Glove{};
				if (TryGetGlove(t_Id, t_Glove) && t_Glove.pairedState == DevicePairedState_Paired)
				{
					Status::Info("Glove " + Id(t_Id) + " is already paired to dongle "
						+ Id(t_Glove.dongleID) + " - [U] unpair it first.");
					return true;
				}
				t_State->pickingDongle = true;
				t_State->pairGloveId = t_Id;
				Status::Info("Pick the dongle to pair glove " + Id(t_Id) + " to.");
				return true;
			}
			if ((p_Event == Event::Character('u') || p_Event == Event::Character('U')) && t_IsGlove)
			{
				GloveLandscapeData t_Glove{};
				if (TryGetGlove(t_Id, t_Glove))
				{
					if (t_Glove.pairedState != DevicePairedState_Paired)
					{
						Status::Info("Glove " + Id(t_Id) + " is not paired to a dongle.");
						return true;
					}
					// A wired glove acts as its own dongle and cannot be unpaired.
					if (t_Glove.id == t_Glove.dongleID)
					{
						Status::Info("Glove " + Id(t_Id)
							+ " is connected via USB (it is its own dongle); there is nothing to unpair.");
						return true;
					}
				}
				bool t_Accepted = false;
				const manus::SdkResult t_Result = manus::Devices::UnpairGlove(t_Id, t_Accepted);
				if (!t_Result.Ok()) Status::Error("Unpairing failed: " + t_Result.Description());
				else if (!t_Accepted) Status::Error("Core declined the unpairing request.");
				else Status::Success("Unpairing glove " + Id(t_Id) + "...");
				return true;
			}
			if (p_Event == Event::Character('f') || p_Event == Event::Character('F'))
			{
				t_State->confirmFirmwareId = t_Id;
				t_State->confirmIsGlove = t_IsGlove;
				std::string t_Prompt = "Update firmware of "
					+ std::string(t_IsGlove ? "glove " : "dongle ") + Id(t_Id)
					+ "? [Y] confirm, [C] cancel.";
				if (t_IsGlove) t_Prompt += " Connect the glove via USB first";
				Status::Info(t_Prompt);
				return true;
			}
			return false;
			});
	}
}
