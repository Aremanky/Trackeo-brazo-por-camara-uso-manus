#include "sdk/Firmware.hpp"

#include "ManusSDK.h"

namespace manus
{
	SdkResult Firmware::Update(uint32_t p_DeviceId, bool& p_OutAccepted, std::string& p_OutMessage)
	{
		Response t_Response{};
		const SDKReturnCode t_Result = CoreSdk_UpdateFirmware(p_DeviceId, &t_Response);
		p_OutAccepted = t_Response.result;
		p_OutMessage = t_Response.message.message;
		return t_Result;
	}
}
