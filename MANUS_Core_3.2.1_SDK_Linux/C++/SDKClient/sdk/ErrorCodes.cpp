#include "sdk/ErrorCodes.hpp"

#include <sstream>

namespace manus
{
	const char* ReturnCodeName(SDKReturnCode p_Code)
	{
		switch (p_Code)
		{
		case SDKReturnCode_Success: return "Success";
		case SDKReturnCode_Error: return "Error";
		case SDKReturnCode_InvalidArgument: return "InvalidArgument";
		case SDKReturnCode_ArgumentSizeMismatch: return "ArgumentSizeMismatch";
		case SDKReturnCode_UnsupportedStringSizeEncountered: return "UnsupportedStringSizeEncountered";
		case SDKReturnCode_SdkNotAvailable: return "SdkNotAvailable";
		case SDKReturnCode_HostFinderNotAvailable: return "HostFinderNotAvailable";
		case SDKReturnCode_DataNotAvailable: return "DataNotAvailable";
		case SDKReturnCode_MemoryError: return "MemoryError";
		case SDKReturnCode_InternalError: return "InternalError";
		case SDKReturnCode_FunctionCalledAtWrongTime: return "FunctionCalledAtWrongTime";
		case SDKReturnCode_NotConnected: return "NotConnected";
		case SDKReturnCode_ConnectionTimeout: return "ConnectionTimeout";
		case SDKReturnCode_InvalidID: return "InvalidID";
		case SDKReturnCode_NullPointer: return "NullPointer";
		case SDKReturnCode_InvalidSequence: return "InvalidSequence";
		case SDKReturnCode_NoCoordinateSystemSet: return "NoCoordinateSystemSet";
		case SDKReturnCode_SdkIsTerminating: return "SdkIsTerminating";
		case SDKReturnCode_StubNullPointer: return "StubNullPointer";
		case SDKReturnCode_SkeletonNotLoaded: return "SkeletonNotLoaded";
		case SDKReturnCode_FunctionNotAvailable: return "FunctionNotAvailable";
		default: return "UnknownReturnCode";
		}
	}

	const char* ReturnCodeHint(SDKReturnCode p_Code)
	{
		switch (p_Code)
		{
		case SDKReturnCode_SdkNotAvailable:
			return "The SDK was not initialized, or was already shut down.";
		case SDKReturnCode_FunctionCalledAtWrongTime:
			return "This call is not valid in the current SDK state (e.g. before initialization).";
		case SDKReturnCode_NotConnected:
			return "There is no connection to MANUS Core.";
		case SDKReturnCode_ConnectionTimeout:
			return "The connection to MANUS Core timed out.";
		case SDKReturnCode_NoCoordinateSystemSet:
			return "A coordinate system must be set before connecting.";
		case SDKReturnCode_SkeletonNotLoaded:
			return "The skeleton is not loaded (max 32 skeletons per session).";
		case SDKReturnCode_FunctionNotAvailable:
			return "Not available in this mode or version of the SDK.";
		default:
			return "";
		}
	}

	std::string Describe(SDKReturnCode p_Code)
	{
		std::ostringstream t_Stream;
		t_Stream << ReturnCodeName(p_Code) << " (" << static_cast<int32_t>(p_Code) << ")";
		const char* t_Hint = ReturnCodeHint(p_Code);
		if (t_Hint[0] != '\0') t_Stream << " - " << t_Hint;
		return t_Stream.str();
	}
}
