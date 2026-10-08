#include "sdk/Timecode.hpp"

#include "ManusSDK.h"

#include <cstdio>

namespace manus
{
	// --8<-- [start:timecode-string]
	std::string Timecode::TimecodeString(ManusTimestamp p_Timestamp, bool& p_OutIsTimecode)
	{
		p_OutIsTimecode = false;

		ManusTimestampInfo t_Info{};
		if (CoreSdk_GetTimestampInfo(p_Timestamp, &t_Info) != SDKReturnCode_Success) return "";

		p_OutIsTimecode = t_Info.timecode;
		char t_Buffer[24];
		if (t_Info.timecode)
		{
			// In timecode the fraction is the frame number.
			std::snprintf(t_Buffer, sizeof(t_Buffer), "%02u:%02u:%02u:%02u",
				t_Info.hour, t_Info.minute, t_Info.second, t_Info.fraction);
		}
		else
		{
			// Without timecode the fraction is milliseconds (wall clock, UTC).
			std::snprintf(t_Buffer, sizeof(t_Buffer), "%02u:%02u:%02u.%03u",
				t_Info.hour, t_Info.minute, t_Info.second, t_Info.fraction);
		}
		return t_Buffer;
	}
	// --8<-- [end:timecode-string]

	const char* Timecode::FPSName(TimecodeFPS p_FPS)
	{
		switch (p_FPS)
		{
		case TimecodeFPS_23_976: return "23.976";
		case TimecodeFPS_24: return "24";
		case TimecodeFPS_25: return "25";
		case TimecodeFPS_29_97: return "29.97";
		case TimecodeFPS_30: return "30";
		case TimecodeFPS_48: return "48";
		case TimecodeFPS_50: return "50";
		case TimecodeFPS_59_94: return "59.94";
		case TimecodeFPS_60: return "60";
		case TimecodeFPS_29_97DF: return "29.97 DF";
		case TimecodeFPS_59_94DF: return "59.94 DF";
		default: return "Undefined";
		}
	}
}
