#include "sdk/License.hpp"

#include "sdk/Paths.hpp"

#include "ManusSDK.h"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <vector>

namespace manus
{
	// --8<-- [start:set-license]
	SdkResult License::SetFromFile(uint32_t p_DongleId, const std::string& p_FilePath,
		bool& p_OutAccepted, std::string& p_OutMessage)
	{
		p_OutAccepted = false;
		p_OutMessage.clear();

		std::ifstream t_File(p_FilePath, std::ios::binary);
		if (!t_File)
		{
			p_OutMessage = "Could not read the file.";
			return SDKReturnCode_InvalidArgument;
		}
		std::vector<char> t_Data(
			(std::istreambuf_iterator<char>(t_File)), std::istreambuf_iterator<char>());
		if (t_Data.empty())
		{
			p_OutMessage = "The file is empty.";
			return SDKReturnCode_InvalidArgument;
		}

		Response t_Response{};
		const SDKReturnCode t_Result = CoreSdk_SetLicense(
			p_DongleId, t_Data.data(), (uint32_t)t_Data.size(), &t_Response);
		p_OutAccepted = t_Response.result;
		p_OutMessage = t_Response.message.message;
		return t_Result;
	}
	// --8<-- [end:set-license]

	// --8<-- [start:retrieve-license]
	SdkResult License::Retrieve(uint32_t p_DongleId, bool& p_OutAccepted, std::string& p_OutMessage)
	{
		p_OutAccepted = false;
		p_OutMessage.clear();

		Response t_Response{};
		const SDKReturnCode t_Result = CoreSdk_RetrieveLicense(p_DongleId, &t_Response);
		p_OutAccepted = t_Response.result;
		p_OutMessage = t_Response.message.message;
		return t_Result;
	}
	// --8<-- [end:retrieve-license]

	const char* License::LevelName(LicenseType p_Level)
	{
		switch (p_Level)
		{
		case LicenseType_Polygon: return "Polygon";
		case LicenseType_CoreXO: return "Core XO";
		case LicenseType_CorePro: return "Core Pro";
		case LicenseType_CoreXOPro: return "Core XO Pro";
		case LicenseType_CoreX: return "Core X";
		case LicenseType_CoreO: return "Core O";
		case LicenseType_CoreQ: return "Core Q";
		case LicenseType_CoreXPro: return "Core X Pro";
		case LicenseType_CoreOPro: return "Core O Pro";
		case LicenseType_CoreQPro: return "Core Q Pro";
		case LicenseType_CoreXOQPro: return "Core XOQ Pro";
		case LicenseType_CoreXR: return "Core XR";
		case LicenseType_CorePrimeThree: return "Core Prime 3";
		case LicenseType_Feature: return "Feature-based";
		default: return "Undefined";
		}
	}

	const char* License::TermName(LicenseTermType p_Term)
	{
		switch (p_Term)
		{
		case LicenseTermType_Recurring: return "Recurring";
		case LicenseTermType_Perpetual: return "Perpetual";
		default: return "Unknown";
		}
	}

	const char* License::StatusName(LicenseStatus p_Status)
	{
		switch (p_Status)
		{
		case LicenseStatus_Valid: return "Valid";
		case LicenseStatus_Invalid: return "Invalid (key/signature did not verify)";
		case LicenseStatus_Expired: return "Expired";
		case LicenseStatus_SupportExpired: return "Support expired (this build is newer than the license's support window)";
		default: return "Unknown";
		}
	}

	std::string License::TimestampString(ManusTimestamp p_Timestamp)
	{
		if (p_Timestamp.time == 0) return "-";

		ManusTimestampInfo t_Info{};
		if (CoreSdk_GetTimestampInfo(p_Timestamp, &t_Info) != SDKReturnCode_Success) return "-";

		char t_Buffer[32];
		std::snprintf(t_Buffer, sizeof(t_Buffer), "%04u-%02u-%02u %02u:%02u:%02u",
			t_Info.year, t_Info.month, t_Info.day, t_Info.hour, t_Info.minute, t_Info.second);
		return t_Buffer;
	}

	std::string License::DefaultLicenseFolder()
	{
		// Prefer Documents/manus-licenses when it already exists; otherwise
		// fall back to the Documents folder itself.
		const std::filesystem::path t_Licenses = Paths::DocumentsSubfolder("manus-licenses");
		std::error_code t_Error;
		if (std::filesystem::is_directory(t_Licenses, t_Error)) return t_Licenses.string();
		return Paths::Documents();
	}
}
