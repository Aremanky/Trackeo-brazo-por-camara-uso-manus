// SDKClient sdk/ module - glove calibration
// (start -> per-step execute -> finish), and saving/loading calibration
// profiles as .mcal files.
//
// Storage note: Core stores calibration per GLOVE while auto-assignment is on,
// and per USER when it is off (the ...ForUser SDK variants address the latter).
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <cstdint>
#include <string>

namespace manus
{
	namespace Calibration
	{
		struct Step
		{
			uint32_t index = 0;
			std::string title;
			std::string description;
			// Expected duration in seconds; NEGATIVE means a continuous step
			// and the value is Core's estimate.
			float time = 0.0f;
		};

		SdkResult GetNumberOfSteps(uint32_t p_GloveId, uint32_t& p_OutCount);
		SdkResult GetStep(uint32_t p_GloveId, uint32_t p_StepIndex, Step& p_OutStep);

		/// @brief Begins a calibration session for the glove.
		SdkResult Start(uint32_t p_GloveId, bool& p_OutAccepted);

		/// @brief Runs one calibration step. BLOCKS for the duration of the
		/// step (the user holds the pose meanwhile) - call from a worker thread.
		SdkResult ExecuteStep(uint32_t p_GloveId, uint32_t p_StepIndex, bool& p_OutSucceeded);

		/// @brief Ends the session, saving and applying the result.
		SdkResult Finish(uint32_t p_GloveId, bool& p_OutAccepted);

		/// @brief Aborts the session without applying.
		SdkResult Cancel(uint32_t p_GloveId, bool& p_OutAccepted);

		/// @brief Writes the glove's current calibration to a .mcal file.
		SdkResult SaveToFile(uint32_t p_GloveId, const std::string& p_FilePath);

		/// @brief Applies a .mcal file to the glove. p_OutResult carries Core's
		/// verdict - see SetResultName for a readable form.
		SdkResult LoadFromFile(uint32_t p_GloveId, const std::string& p_FilePath,
			SetGloveCalibrationReturnCode& p_OutResult);

		/// @brief Readable name for Core's set-calibration verdict.
		const char* SetResultName(SetGloveCalibrationReturnCode p_Result);

		/// @brief Default folder for .mcal files: Documents/manus-calibrations.
		std::string DefaultCalibrationFolder();
	}
}
