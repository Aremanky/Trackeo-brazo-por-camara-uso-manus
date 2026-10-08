#include "sdk/Calibration.hpp"

#include "sdk/Paths.hpp"

#include "ManusSDK.h"

#include <filesystem>
#include <fstream>
#include <vector>

namespace manus
{
	// --8<-- [start:calibration-flow]
	SdkResult Calibration::GetNumberOfSteps(uint32_t p_GloveId, uint32_t& p_OutCount)
	{
		p_OutCount = 0;
		GloveCalibrationArgs t_Args{ p_GloveId };
		return CoreSdk_GloveCalibrationGetNumberOfSteps(t_Args, &p_OutCount);
	}

	SdkResult Calibration::GetStep(uint32_t p_GloveId, uint32_t p_StepIndex, Step& p_OutStep)
	{
		GloveCalibrationStepArgs t_Args{ p_GloveId, p_StepIndex };
		GloveCalibrationStepData t_Data;
		GloveCalibrationStepData_Init(&t_Data);
		const SDKReturnCode t_Result = CoreSdk_GloveCalibrationGetStepData(t_Args, &t_Data);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		p_OutStep.index = t_Data.index;
		p_OutStep.title = t_Data.title;
		p_OutStep.description = t_Data.description;
		p_OutStep.time = t_Data.time;
		return t_Result;
	}

	SdkResult Calibration::Start(uint32_t p_GloveId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		GloveCalibrationArgs t_Args{ p_GloveId };
		return CoreSdk_GloveCalibrationStart(t_Args, &p_OutAccepted);
	}

	SdkResult Calibration::ExecuteStep(uint32_t p_GloveId, uint32_t p_StepIndex, bool& p_OutSucceeded)
	{
		p_OutSucceeded = false;
		GloveCalibrationStepArgs t_Args{ p_GloveId, p_StepIndex };
		return CoreSdk_GloveCalibrationStartStep(t_Args, &p_OutSucceeded);
	}

	SdkResult Calibration::Finish(uint32_t p_GloveId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		GloveCalibrationArgs t_Args{ p_GloveId };
		return CoreSdk_GloveCalibrationFinish(t_Args, &p_OutAccepted);
	}

	SdkResult Calibration::Cancel(uint32_t p_GloveId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		GloveCalibrationArgs t_Args{ p_GloveId };
		return CoreSdk_GloveCalibrationStop(t_Args, &p_OutAccepted);
	}
	// --8<-- [end:calibration-flow]

	// --8<-- [start:save-calibration]
	SdkResult Calibration::SaveToFile(uint32_t p_GloveId, const std::string& p_FilePath)
	{
		// The size call also PREPARES the calibration data for retrieval.
		uint32_t t_Size = 0;
		SDKReturnCode t_Result = CoreSdk_GetGloveCalibrationSize(p_GloveId, &t_Size);
		if (t_Result != SDKReturnCode_Success) return t_Result;

		std::vector<unsigned char> t_Data(t_Size);
		t_Result = CoreSdk_GetGloveCalibration(t_Data.data(), t_Size);
		if (t_Result != SDKReturnCode_Success) return t_Result;

		std::error_code t_Error;
		std::filesystem::create_directories(std::filesystem::path(p_FilePath).parent_path(), t_Error);
		std::ofstream t_File(p_FilePath, std::ios::binary);
		if (!t_File) return SDKReturnCode_InvalidArgument;
		t_File.write((const char*)t_Data.data(), t_Data.size());
		return SDKReturnCode_Success;
	}
	// --8<-- [end:save-calibration]

	// --8<-- [start:load-calibration]
	SdkResult Calibration::LoadFromFile(uint32_t p_GloveId, const std::string& p_FilePath,
		SetGloveCalibrationReturnCode& p_OutResult)
	{
		p_OutResult = SetGloveCalibrationReturnCode_Error;

		std::ifstream t_File(p_FilePath, std::ios::binary);
		if (!t_File) return SDKReturnCode_InvalidArgument;
		std::vector<unsigned char> t_Data(
			(std::istreambuf_iterator<char>(t_File)), std::istreambuf_iterator<char>());
		if (t_Data.empty()) return SDKReturnCode_InvalidArgument;

		return CoreSdk_SetGloveCalibration(
			p_GloveId, t_Data.data(), (uint32_t)t_Data.size(), &p_OutResult);
	}
	// --8<-- [end:load-calibration]

	const char* Calibration::SetResultName(SetGloveCalibrationReturnCode p_Result)
	{
		switch (p_Result)
		{
		case SetGloveCalibrationReturnCode_Success: return "Success";
		case SetGloveCalibrationReturnCode_VersionError: return "the calibration was made with an incompatible version";
		case SetGloveCalibrationReturnCode_WrongSideError: return "the calibration is for the other hand side";
		case SetGloveCalibrationReturnCode_GloveNotFoundError: return "the glove was not found";
		case SetGloveCalibrationReturnCode_UserServiceError: return "Core's user service reported an error";
		case SetGloveCalibrationReturnCode_DeserializationError: return "the file could not be parsed as a calibration";
		default: return "an unspecified error";
		}
	}

	std::string Calibration::DefaultCalibrationFolder()
	{
		return Paths::DocumentsSubfolder("manus-calibrations");
	}
}
