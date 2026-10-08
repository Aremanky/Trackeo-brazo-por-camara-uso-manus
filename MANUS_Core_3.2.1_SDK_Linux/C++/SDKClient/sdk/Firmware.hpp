// SDKClient sdk/ module - firmware updates for dongles and gloves.
//
// Notes:
//  - Update gloves over a USB cable; updating a wirelessly connected glove is
//    not supported.
//  - Core only reports the initial response; there is no progress stream.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include <cstdint>
#include <string>

namespace manus
{
	namespace Firmware
	{
		/// @brief Asks Core to update the firmware of a device (dongle or glove).
		/// p_OutAccepted / p_OutMessage carry Core's response to the request.
		SdkResult Update(uint32_t p_DeviceId, bool& p_OutAccepted, std::string& p_OutMessage);
	}
}
