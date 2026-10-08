// SDKClient ui/ component - shared value formatting.
// Device/user/session IDs are displayed as hex everywhere (the MANUS
// convention); counts and measurements stay decimal.
#pragma once

#include <cstdint>
#include <string>

namespace ui
{
	/// @brief An ID as uppercase hex with 0x prefix, e.g. "0xE6E8A5DC".
	std::string Id(uint32_t p_Id);
}
