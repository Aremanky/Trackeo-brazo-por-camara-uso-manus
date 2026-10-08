#include "ui/screens/CalibrationScreen.hpp"

#include "sdk/Calibration.hpp"

#include "ui/components/DeviceSelector.hpp"
#include "ui/components/FilePicker.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct WizardState
		{
			std::mutex mutex;
			bool running = false;
			std::atomic<bool> cancelRequested{ false };

			uint32_t gloveId = 0;
			uint32_t stepCount = 0;
			uint32_t currentStep = 0;
			manus::Calibration::Step step;
			std::string phase;    // "Get ready..." / "Hold the pose..."
			int countdown = 0;    // seconds remaining in the get-ready phase
		};

		struct CalibrationState
		{
			std::shared_ptr<DeviceSelectorState> gloves;
			std::shared_ptr<FilePickerState> filePicker;
			bool pickingFile = false;
			int tab = 0;
			std::shared_ptr<WizardState> wizard = std::make_shared<WizardState>();
		};

		// The whole calibration sequence on one worker thread: start, then per
		// step a short get-ready countdown followed by the (blocking) step
		// execution, and finish at the end. Cancel takes effect between phases.
		void RunWizard(std::shared_ptr<WizardState> p_Wizard, uint32_t p_GloveId)
		{
			auto t_SetPhase = [&](const std::string& p_Phase, int p_Countdown) {
				std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
				p_Wizard->phase = p_Phase;
				p_Wizard->countdown = p_Countdown;
				};
			auto t_Stop = [&](const std::string& p_Message, bool p_IsError) {
				bool t_Ignored = false;
				manus::Calibration::Cancel(p_GloveId, t_Ignored);
				if (p_IsError) Status::Error(p_Message); else Status::Info(p_Message);
				std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
				p_Wizard->running = false;
				};

			bool t_Accepted = false;
			manus::SdkResult t_Result = manus::Calibration::Start(p_GloveId, t_Accepted);
			if (!t_Result.Ok() || !t_Accepted)
			{
				Status::Error("Could not start calibration"
					+ (t_Result.Ok() ? std::string(" - Core declined.") : ": " + t_Result.Description()));
				std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
				p_Wizard->running = false;
				return;
			}

			uint32_t t_StepCount = 0;
			t_Result = manus::Calibration::GetNumberOfSteps(p_GloveId, t_StepCount);
			if (!t_Result.Ok() || t_StepCount == 0)
			{
				t_Stop("Calibration has no steps for this glove.", true);
				return;
			}
			{
				std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
				p_Wizard->stepCount = t_StepCount;
			}

			for (uint32_t t_StepIndex = 0; t_StepIndex < t_StepCount; ++t_StepIndex)
			{
				manus::Calibration::Step t_Step;
				if (!manus::Calibration::GetStep(p_GloveId, t_StepIndex, t_Step).Ok())
				{
					t_Stop("Could not get step data - calibration aborted.", true);
					return;
				}
				{
					std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
					p_Wizard->currentStep = t_StepIndex;
					p_Wizard->step = t_Step;
				}

				// Get-ready countdown so the user can read the instruction.
				for (int t_Second = 3; t_Second > 0; --t_Second)
				{
					if (p_Wizard->cancelRequested) { t_Stop("Calibration cancelled.", false); return; }
					t_SetPhase("Get ready...", t_Second);
					std::this_thread::sleep_for(std::chrono::seconds(1));
				}
				if (p_Wizard->cancelRequested) { t_Stop("Calibration cancelled.", false); return; }

				// Continuous steps keep recording through movement, so
				// "hold the pose" would be misleading for them.
				t_SetPhase(t_Step.time < 0.0f ? "Recording - move through the motion..." : "Hold the pose - recording...", 0);
				bool t_StepSucceeded = false;
				t_Result = manus::Calibration::ExecuteStep(p_GloveId, t_StepIndex, t_StepSucceeded);
				if (!t_Result.Ok() || !t_StepSucceeded)
				{
					t_Stop("Step " + std::to_string(t_StepIndex + 1) + " failed - calibration aborted.", true);
					return;
				}
			}

			t_SetPhase("Finalizing - Core is processing the calibration...", 0);
			t_Accepted = false;
			t_Result = manus::Calibration::Finish(p_GloveId, t_Accepted);
			if (!t_Result.Ok() || !t_Accepted)
				Status::Error("Could not finish calibration"
					+ (t_Result.Ok() ? std::string(" - Core declined.") : ": " + t_Result.Description()));
			else
				Status::Success("Calibration successful - all " + std::to_string(t_StepCount)
					+ " steps completed and the result is applied to glove " + Id(p_GloveId) + ".");

			std::lock_guard<std::mutex> t_Lock(p_Wizard->mutex);
			p_Wizard->running = false;
		}

		Element RenderWizard(WizardState& p_Wizard)
		{
			std::lock_guard<std::mutex> t_Lock(p_Wizard.mutex);
			if (!p_Wizard.running)
			{
				return vbox({
					text("Pick a glove on the left and press [Enter] or [S] to calibrate.") | bold,
					text(""),
					text("The wizard runs every step automatically: read the instruction,"),
					text("a 3-second countdown follows, then hold the pose while it records."),
					}) | center;
			}

			// Step X of N - 1-based for humans.
			char t_Header[64];
			std::snprintf(t_Header, sizeof(t_Header), "Step %u of %u",
				p_Wizard.currentStep + 1, p_Wizard.stepCount);

			Elements t_Lines = {
				text(t_Header) | bold,
				text(p_Wizard.step.title) | bold | color(ftxui::Color::Cyan),
				text(p_Wizard.step.description),
				text(""),
			};
			if (p_Wizard.countdown > 0)
			{
				t_Lines.push_back(text(p_Wizard.phase + "  " + std::to_string(p_Wizard.countdown)) | bold
					| color(ftxui::Color::Yellow));
			}
			else
			{
				char t_Duration[48] = "";
				if (p_Wizard.step.time > 0.0f)
					std::snprintf(t_Duration, sizeof(t_Duration), "  (~%.0f s)", p_Wizard.step.time);
				else if (p_Wizard.step.time < 0.0f)
					std::snprintf(t_Duration, sizeof(t_Duration), "  (continuous, ~%.0f s estimated)", -p_Wizard.step.time);
				t_Lines.push_back(text(p_Wizard.phase + t_Duration) | bold | color(ftxui::Color::Green));
			}
			t_Lines.push_back(text(""));
			t_Lines.push_back(text("[C] cancel") | dim);
			return vbox(std::move(t_Lines)) | center;
		}
	}

	Component MakeCalibrationScreen()
	{
		auto t_State = std::make_shared<CalibrationState>();
		t_State->gloves = MakeDeviceSelectorState(DeviceKind::Gloves);
		t_State->filePicker = MakeFilePickerState(
			manus::Calibration::DefaultCalibrationFolder(), ".mcal",
			[t_State](const std::filesystem::path& p_File) {
				const uint32_t t_GloveId = SelectedId(*t_State->gloves);
				SetGloveCalibrationReturnCode t_Verdict = SetGloveCalibrationReturnCode_Error;
				const manus::SdkResult t_Result = manus::Calibration::LoadFromFile(
					t_GloveId, p_File.string(), t_Verdict);
				if (!t_Result.Ok())
					Status::Error("Failed to load calibration: " + t_Result.Description());
				else if (t_Verdict != SetGloveCalibrationReturnCode_Success)
					Status::Error("Core rejected the calibration: "
						+ std::string(manus::Calibration::SetResultName(t_Verdict)) + ".");
				else
					Status::Success("Applied \"" + p_File.filename().string() + "\" to glove " + Id(t_GloveId) + ".");
				t_State->pickingFile = false;
			});

		Component t_GloveSelector = MakeDeviceSelector(t_State->gloves);
		Component t_FilePicker = MakeFilePicker(t_State->filePicker);
		Component t_Areas = Container::Tab({ t_GloveSelector, t_FilePicker }, &t_State->tab);

		Component t_Root = Renderer(t_Areas, [=] {
			t_State->tab = t_State->pickingFile ? 1 : 0;

			Element t_Left = t_State->pickingFile
				? window(text(" Pick a .mcal calibration file "), t_FilePicker->Render())
				: window(text(" Gloves "), t_GloveSelector->Render());

			bool t_Running;
			{
				std::lock_guard<std::mutex> t_Lock(t_State->wizard->mutex);
				t_Running = t_State->wizard->running;
			}

			return vbox({
				Status::Render(),
				hbox({
					t_Left | flex,
					window(text(" Calibration "), RenderWizard(*t_State->wizard)) | flex,
					}) | flex,
				text(t_State->pickingFile
					? " [Up/Down] browse   [Enter] open folder / apply file   [C] cancel "
					: t_Running
					? " [C] cancel calibration "
					: " [Enter]/[S] calibrate glove   [K] save .mcal   [L] load .mcal...   (profiles are stored per user when auto-assignment is off) ") | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			const bool t_IsC = p_Event == Event::Character('c') || p_Event == Event::Character('C');

			if (t_State->pickingFile)
			{
				if (t_IsC)
				{
					t_State->pickingFile = false;
					Status::Clear();
					return true;
				}
				return false;
			}

			bool t_Running;
			{
				std::lock_guard<std::mutex> t_Lock(t_State->wizard->mutex);
				t_Running = t_State->wizard->running;
			}
			if (t_Running)
			{
				if (t_IsC)
				{
					t_State->wizard->cancelRequested = true;
					Status::Info("Cancelling after the current phase...");
					return true;
				}
				return false; // everything else is ignored while calibrating
			}

			if (!HasSelection(*t_State->gloves)) return false;
			const uint32_t t_GloveId = SelectedId(*t_State->gloves);

			if (p_Event == Event::Return || p_Event == Event::Character('s') || p_Event == Event::Character('S'))
			{
				{
					std::lock_guard<std::mutex> t_Lock(t_State->wizard->mutex);
					t_State->wizard->running = true;
					t_State->wizard->gloveId = t_GloveId;
					t_State->wizard->stepCount = 0;
					t_State->wizard->currentStep = 0;
					t_State->wizard->phase = "Starting...";
				}
				t_State->wizard->cancelRequested = false;
				Status::Clear();
				std::thread(RunWizard, t_State->wizard, t_GloveId).detach();
				return true;
			}
			if (p_Event == Event::Character('k') || p_Event == Event::Character('K'))
			{
				const std::string t_Path = manus::Calibration::DefaultCalibrationFolder()
					+ "/glove_" + Id(t_GloveId) + ".mcal";
				const manus::SdkResult t_Result = manus::Calibration::SaveToFile(t_GloveId, t_Path);
				if (!t_Result.Ok()) Status::Error("Failed to save calibration: " + t_Result.Description());
				else Status::Success("Saved to " + t_Path);
				return true;
			}
			if (p_Event == Event::Character('l') || p_Event == Event::Character('L'))
			{
				t_State->pickingFile = true;
				RefreshFilePicker(*t_State->filePicker);
				Status::Info("Pick the .mcal file to apply to glove " + Id(t_GloveId) + ".");
				return true;
			}
			return false;
			});
	}
}
