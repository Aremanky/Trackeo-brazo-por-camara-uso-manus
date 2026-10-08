// SDKClient sdk/ module - dongle licensing.
//
// A license is a feature entitlement written to a dongle: either applied from
// a .lic file, or refreshed from the MANUS license service (Core exchanges the
// dongle's current license online and writes back the newest one; requires the
// license service to be reachable from the Core machine).
// License *flags* (SDK, recording, plugin sessions, ...) are read from the
// landscape - Landscape.settings.license - see sdk/LandscapeCache.hpp.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <cstdint>
#include <string>

namespace manus
{
	namespace License
	{
		/// @brief Reads a .lic file and writes it to the given dongle.
		/// p_OutAccepted / p_OutMessage carry Core's response.
		/// Returns SDKReturnCode_InvalidArgument when the file cannot be read.
		SdkResult SetFromFile(uint32_t p_DongleId, const std::string& p_FilePath,
			bool& p_OutAccepted, std::string& p_OutMessage);

		/// @brief Asks Core to fetch the newest license for the dongle from the
		/// MANUS license service. Blocks for the online exchange - call from a
		/// worker thread.
		SdkResult Retrieve(uint32_t p_DongleId, bool& p_OutAccepted, std::string& p_OutMessage);

		/// @brief The default folder for license files:
		/// Documents/manus-licenses (falls back to the home directory).
		std::string DefaultLicenseFolder();

		/// @brief Readable name for a dongle's license level (SKU),
		/// e.g. LicenseType_CoreXOPro -> "Core XO Pro".
		const char* LevelName(LicenseType p_Level);

		/// @brief Readable name for the license term model. Recurring licenses
		/// block at their end date; Perpetual ones keep running but stop
		/// receiving updates after it. Unknown for V2 licenses.
		const char* TermName(LicenseTermType p_Term);

		/// @brief Readable name for the license status the reporting Core build
		/// evaluated for a dongle. SupportExpired means a Perpetual license whose
		/// support window ended before this (too new) Core build was released.
		/// Unknown when talking to an older Core that does not report the field.
		const char* StatusName(LicenseStatus p_Status);

		/// @brief A ManusTimestamp as "YYYY-MM-DD HH:MM:SS" (empty timestamp -> "-").
		std::string TimestampString(ManusTimestamp p_Timestamp);
	}
}
