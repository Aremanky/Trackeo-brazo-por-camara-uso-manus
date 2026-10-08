// SDKClient sdk/ module - timecode: MANUS Core's synchronization with an
// external timecode signal (LTC / Genlock).
// The timecode state is read from the landscape - Landscape.time - see
// sdk/LandscapeCache.hpp. A timecode generator is configured via the MANUS
// Core Dashboard; in Core Integrated there is no timecode hardware attached.
#pragma once

#include "ManusSDKTypes.h"

#include <string>

namespace manus
{
	namespace Timecode
	{
		/// @brief Readable name for a timecode frame rate, e.g. "29.97 DF".
		const char* FPSName(TimecodeFPS p_FPS);

		/// @brief Decodes a stream publish timestamp for display.
		/// With an active timecode signal (p_OutIsTimecode = true) the result
		/// is "HH:MM:SS:FF" (FF = frame); otherwise it is wall-clock
		/// "HH:MM:SS.mmm". Returns "" when decoding fails.
		std::string TimecodeString(ManusTimestamp p_Timestamp, bool& p_OutIsTimecode);
	}
}
