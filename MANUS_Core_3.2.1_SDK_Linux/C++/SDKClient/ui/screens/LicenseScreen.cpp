#include "ui/screens/LicenseScreen.hpp"

#include "sdk/LandscapeCache.hpp"
#include "sdk/License.hpp"

#include "ui/components/DeviceSelector.hpp"
#include "ui/components/FilePicker.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>

#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct LicenseState
		{
			bool pickingFile = false;
			int tab = 0; // 0 = dongle list, 1 = file picker
			uint32_t targetDongleId = 0;

			std::shared_ptr<DeviceSelectorState> dongles;
			std::shared_ptr<FilePickerState> filePicker;
		};

		Element RenderLicenseFlags()
		{
			const LicenseInfo t_License = manus::LandscapeCache::Snapshot().settings.license;

			const std::vector<std::pair<std::string, bool>> t_Flags = {
				{ "Recording", t_License.recording },
				{ "Exporting", t_License.exporting },
				{ "Advanced Exporting", t_License.advancedExporting },
				{ "SDK", t_License.sdk },
				{ "Raw", t_License.raw },
				{ "Integrated", t_License.integrated },
				{ "Linux", t_License.linuxTarget },
				{ "Unity", t_License.unitySession },
				{ "Unreal", t_License.unrealSession },
				{ "OpenXR", t_License.openXRSession },
				{ "MotionBuilder", t_License.mobuSession },
				{ "Xsens", t_License.xsensSession },
				{ "OptiTrack", t_License.optitrackSession },
				{ "Qualisys", t_License.qualisysSession },
				{ "Vicon", t_License.viconSession },
				{ "Nokov", t_License.nokovSession },
				{ "Icido", t_License.icidoSession },
				{ "Siemens", t_License.siemensSession },
				{ "VRED", t_License.vredSession },
				{ "Cortex", t_License.cortexSession },
				{ "FZ Motion", t_License.fzMotionSession },
				{ "WorldViz", t_License.worldVizSession },
				{ "Noraxon", t_License.noraxonSession },
				{ "Noitom", t_License.noitomSession },
				{ "Ableton", t_License.abletonSession },
			};

			// Two columns to keep the list compact.
			Elements t_Left, t_Right;
			const size_t t_Half = (t_Flags.size() + 1) / 2;
			for (size_t i = 0; i < t_Flags.size(); ++i)
			{
				Element t_Line = hbox({
					text(t_Flags[i].first + ": ") | size(WIDTH, EQUAL, 20),
					t_Flags[i].second ? text("yes") | color(ftxui::Color::Green) : text("no") | dim,
					});
				(i < t_Half ? t_Left : t_Right).push_back(t_Line);
			}

			return vbox({
				text("Max glove pairs: " + std::to_string(t_License.maxGlovePairs)),
				separator(),
				hbox({ vbox(std::move(t_Left)), separator(), vbox(std::move(t_Right)) }),
				});
		}

		Element RenderDongleLicense(const LicenseState& p_State)
		{
			if (!HasSelection(*p_State.dongles))
				return text("Select a dongle on the left.") | dim;

			const uint32_t t_DongleId = SelectedId(*p_State.dongles);
			for (const DongleLandscapeData& t_Dongle : manus::LandscapeCache::DonglesSortedById())
			{
				if (t_Dongle.id != t_DongleId) continue;

				const std::string t_Expiration = manus::License::TimestampString(t_Dongle.licenseExpiration);
				Element t_ExpirationLine;
				switch (t_Dongle.licenseTermType)
				{
				case LicenseTermType_Recurring:
					t_ExpirationLine = text("Expires:         " + t_Expiration);
					break;
				case LicenseTermType_Perpetual:
					t_ExpirationLine = vbox({
						text("Updates until:   " + t_Expiration),
						text("(perpetual: keeps running, stops receiving updates)") | dim,
						});
					break;
				default:
					t_ExpirationLine = text("Expiration:      " + t_Expiration);
					break;
				}

				// The status reflects how the Core build reporting the landscape evaluated the
				// license; only the healthy case is green. SupportExpired in particular means a
				// Perpetual license that is fine on older Cores but does not cover this build.
				Element t_StatusLine = text("Status:          " + std::string(manus::License::StatusName(t_Dongle.licenseStatus)));
				switch (t_Dongle.licenseStatus)
				{
				case LicenseStatus_Valid: t_StatusLine = t_StatusLine | color(ftxui::Color::Green); break;
				case LicenseStatus_Invalid:
				case LicenseStatus_Expired:
				case LicenseStatus_SupportExpired: t_StatusLine = t_StatusLine | color(ftxui::Color::Red); break;
				default: t_StatusLine = t_StatusLine | dim; break;
				}

				return vbox({
					text("Dongle " + Id(t_Dongle.id)) | bold,
					text("License name:    " + std::string(t_Dongle.licenseName[0] != '\0' ? t_Dongle.licenseName : "-")),
					text("License type:    " + std::string(t_Dongle.licenseType[0] != '\0' ? t_Dongle.licenseType : "-")),
					text("Term:            " + std::string(manus::License::TermName(t_Dongle.licenseTermType))),
					t_StatusLine,
					t_ExpirationLine,
					text("Max glove pairs: " + std::to_string(t_Dongle.licenseMaxNumberOfGlovePairs)),
					});
			}
			return text("Dongle disappeared from the landscape.") | dim;
		}

		void RetrieveLicense(uint32_t p_DongleId)
		{
			// Core exchanges the license with the online license service; this
			// blocks, so it runs on a worker thread.
			std::thread([p_DongleId] {
				Status::Busy("Retrieving the newest license for dongle " + Id(p_DongleId) + "...");
				bool t_Accepted = false;
				std::string t_Message;
				const manus::SdkResult t_Result = manus::License::Retrieve(p_DongleId, t_Accepted, t_Message);
				if (!t_Result.Ok())
					Status::Error("License retrieval failed: " + t_Result.Description());
				else if (!t_Accepted)
					Status::Error("Core could not retrieve a license: " + t_Message);
				else
					Status::Success("License retrieved: " + t_Message);
				}).detach();
		}
	}

	Component MakeLicenseScreen()
	{
		auto t_State = std::make_shared<LicenseState>();
		t_State->dongles = MakeDeviceSelectorState(DeviceKind::Dongles);
		t_State->filePicker = MakeFilePickerState(
			manus::License::DefaultLicenseFolder(), ".lic",
			[t_State](const std::filesystem::path& p_File) {
				bool t_Accepted = false;
				std::string t_Message;
				const manus::SdkResult t_Result = manus::License::SetFromFile(
					t_State->targetDongleId, p_File.string(), t_Accepted, t_Message);
				if (!t_Result.Ok())
					Status::Error("Failed to set license: " + t_Result.Description()
						+ (t_Message.empty() ? "" : " (" + t_Message + ")"));
				else if (!t_Accepted)
					Status::Error("Core declined the license: " + t_Message);
				else
					Status::Success("License applied to dongle " + Id(t_State->targetDongleId)
						+ ": " + t_Message);
				t_State->pickingFile = false;
			});

		Component t_DongleSelector = MakeDeviceSelector(t_State->dongles);
		Component t_FilePicker = MakeFilePicker(t_State->filePicker);
		Component t_Areas = Container::Tab({ t_DongleSelector, t_FilePicker }, &t_State->tab);

		Component t_Root = Renderer(t_Areas, [t_State, t_DongleSelector, t_FilePicker] {
			t_State->tab = t_State->pickingFile ? 1 : 0;

			Element t_Left = t_State->pickingFile
				? window(text(" Pick a .lic file for dongle " + Id(t_State->targetDongleId) + " "),
					t_FilePicker->Render())
				: window(text(" Dongles "), t_DongleSelector->Render());

			return vbox({
				Status::Render(),
				hbox({
					t_Left | flex,
					vbox({
						window(text(" Dongle license "), RenderDongleLicense(*t_State)),
						window(text(" Combined license features "), RenderLicenseFlags()) | flex,
						}),
					}) | flex,
				text(t_State->pickingFile
					? " [Up/Down] browse   [Enter] open folder / apply file   [C] cancel "
					: " [S] set license from file...   [R] retrieve newest license ") | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			if (t_State->pickingFile)
			{
				if (p_Event == Event::Character('c') || p_Event == Event::Character('C'))
				{
					t_State->pickingFile = false;
					Status::Clear();
					return true;
				}
				return false; // navigation & Enter go to the file picker
			}

			if (!HasSelection(*t_State->dongles))
			{
				if (p_Event == Event::Character('s') || p_Event == Event::Character('S')
					|| p_Event == Event::Character('r') || p_Event == Event::Character('R'))
				{
					Status::Info("No dongle in the landscape to license.");
					return true;
				}
				return false;
			}
			const uint32_t t_DongleId = SelectedId(*t_State->dongles);

			if (p_Event == Event::Character('s') || p_Event == Event::Character('S'))
			{
				t_State->targetDongleId = t_DongleId;
				t_State->pickingFile = true;
				RefreshFilePicker(*t_State->filePicker);
				Status::Info("Pick the .lic file to apply to dongle " + Id(t_DongleId) + ".");
				return true;
			}
			if (p_Event == Event::Character('r') || p_Event == Event::Character('R'))
			{
				RetrieveLicense(t_DongleId);
				return true;
			}
			return false;
			});
	}
}
