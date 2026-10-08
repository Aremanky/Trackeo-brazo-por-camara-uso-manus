#include "sdk/Devices.hpp"

#include "sdk/LandscapeCache.hpp"

#include "ManusSDK.h"

namespace manus
{
	const char* Devices::SideName(Side p_Side)
	{
		switch (p_Side)
		{
		case Side_Left: return "Left";
		case Side_Right: return "Right";
		default: return "-";
		}
	}

	const char* Devices::FamilyName(DeviceFamilyType p_Family)
	{
		switch (p_Family)
		{
		case DeviceFamilyType_Prime1: return "Prime 1";
		case DeviceFamilyType_Prime2: return "Prime 2";
		case DeviceFamilyType_PrimeX: return "Prime X";
		case DeviceFamilyType_Prime3: return "Prime 3";
		case DeviceFamilyType_Metaglove: return "Metaglove";
		case DeviceFamilyType_MetaglovePro: return "Metaglove Pro";
		case DeviceFamilyType_MetagloveProPrecision: return "Metaglove Pro Precision";
		case DeviceFamilyType_MetagloveProHaptics: return "Metaglove Pro Haptics";
		case DeviceFamilyType_MetagloveProPrecisionHaptics: return "Metaglove Pro Precision Haptics";
		case DeviceFamilyType_MetagloveAir: return "Metaglove Air";
		case DeviceFamilyType_MetagloveAirHaptic: return "Metaglove Air Haptic";
		case DeviceFamilyType_MetagloveTopModule: return "Metaglove Top Module";
		case DeviceFamilyType_Virtual: return "Virtual";
		default: return "Unknown";
		}
	}

	const char* Devices::ClassName(DeviceClassType p_Class)
	{
		switch (p_Class)
		{
		case DeviceClassType_Dongle: return "Dongle";
		case DeviceClassType_Glove: return "Glove";
		case DeviceClassType_Glongle: return "Glongle";
		default: return "Unknown";
		}
	}

	const char* Devices::PairedStateName(DevicePairedState p_State)
	{
		switch (p_State)
		{
		case DevicePairedState_Paired: return "paired";
		case DevicePairedState_Unpaired: return "unpaired";
		case DevicePairedState_Pairing: return "pairing";
		default: return "unknown";
		}
	}

	// --8<-- [start:vibrate-fingers]
	SdkResult Devices::VibrateFingers(uint32_t p_GloveId, const std::array<float, 5>& p_Powers)
	{
		return CoreSdk_VibrateFingersForGlove(p_GloveId, p_Powers.data());
	}
	// --8<-- [end:vibrate-fingers]

	// --8<-- [start:pair]
	SdkResult Devices::PairGlove(uint32_t p_GloveId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		return CoreSdk_PairGlove(p_GloveId, &p_OutAccepted);
	}

	SdkResult Devices::PairGloveToDongle(uint32_t p_GloveId, uint32_t p_DongleId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		return CoreSdk_PairGloveToDongle(p_GloveId, p_DongleId, &p_OutAccepted);
	}
	// --8<-- [end:pair]

	// --8<-- [start:unpair]
	SdkResult Devices::UnpairGlove(uint32_t p_GloveId, bool& p_OutAccepted)
	{
		p_OutAccepted = false;
		return CoreSdk_UnpairGlove(p_GloveId, &p_OutAccepted);
	}
	// --8<-- [end:unpair]

	// --8<-- [start:find-dongle]
	uint32_t Devices::FindDongleWithFreeSlot(Side p_Side)
	{
		for (const DongleLandscapeData& t_Dongle : LandscapeCache::DonglesSortedById())
		{
			// Skip wired gloves acting as their own dongle ("Glongle").
			if (t_Dongle.classType != DeviceClassType_Dongle) continue;

			const uint32_t t_SlotGlove = p_Side == Side_Left ? t_Dongle.leftGloveID : t_Dongle.rightGloveID;
			if (t_SlotGlove == 0) return t_Dongle.id;
		}
		return 0;
	}
	// --8<-- [end:find-dongle]
}
