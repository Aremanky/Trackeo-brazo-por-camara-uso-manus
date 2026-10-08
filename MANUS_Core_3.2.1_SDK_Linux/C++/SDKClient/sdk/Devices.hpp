// SDKClient sdk/ module - glove & dongle operations: haptics and pairing,
// plus readable names for the device enums.
// Device *data* (battery, license, pairing state) comes from the landscape -
// see sdk/LandscapeCache.hpp.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <array>

namespace manus
{
	namespace Devices
	{
		const char* SideName(Side p_Side);
		const char* FamilyName(DeviceFamilyType p_Family);
		const char* ClassName(DeviceClassType p_Class);
		const char* PairedStateName(DevicePairedState p_State);

		/// @brief Vibrates the fingers of a glove (only on haptics-capable
		/// gloves). Order: thumb, index, middle, ring, pinky; strength 0.0-1.0.
		/// One call is one short pulse; send repeatedly for a longer vibration.
		SdkResult VibrateFingers(uint32_t p_GloveId, const std::array<float, 5>& p_Powers);

		/// @brief Asks Core to pair a glove, letting Core pick the dongle.
		SdkResult PairGlove(uint32_t p_GloveId, bool& p_OutAccepted);

		/// @brief Asks Core to pair a glove to a specific dongle.
		SdkResult PairGloveToDongle(uint32_t p_GloveId, uint32_t p_DongleId, bool& p_OutAccepted);

		/// @brief The first dongle in the landscape with a free slot for the
		/// given hand side (ID order). Returns 0 when there is none.
		uint32_t FindDongleWithFreeSlot(Side p_Side);

		/// @brief Asks Core to unpair a glove from its dongle.
		SdkResult UnpairGlove(uint32_t p_GloveId, bool& p_OutAccepted);
	}
}
