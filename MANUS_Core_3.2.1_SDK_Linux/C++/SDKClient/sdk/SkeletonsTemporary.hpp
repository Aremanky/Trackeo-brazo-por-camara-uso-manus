// SDKClient sdk/ module - temporary skeletons: skeleton setups shared with the
// DevTools application for inspection/editing (NOT loaded for animation), and
// their .mskl file round-trip.
// Note: some of these functions are not available in every Core mode/version -
// present SDKReturnCode_FunctionNotAvailable as information, not as an error.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <cstdint>
#include <string>
#include <vector>

namespace manus
{
	namespace SkeletonsTemporary
	{
		/// @brief Number of temporary skeletons across all connected sessions.
		SdkResult CountForAllSessions(uint32_t& p_OutCount);

		/// @brief Builds the example hand setup and saves it as a temporary
		/// skeleton for the given session, so DevTools can see it.
		SdkResult BuildExample(uint32_t p_SessionId, uint32_t& p_OutIndex);

		/// @brief Compresses a temporary skeleton and writes it to a .mskl file.
		SdkResult SaveToFile(uint32_t p_SkeletonIndex, uint32_t p_SessionId, const std::string& p_FilePath);

		/// @brief Reads a .mskl file and registers it as a temporary skeleton
		/// for the given session.
		SdkResult LoadFromFile(uint32_t p_SessionId, const std::string& p_FilePath, uint32_t& p_OutIndex);

		/// @brief Removes one of this client's temporary skeletons.
		SdkResult Clear(uint32_t p_SkeletonIndex, uint32_t p_SessionId);

		/// @brief Removes the temporary skeletons of ALL sessions (also other clients').
		SdkResult ClearAll();

		/// @brief Setup indexes of temporary skeletons created by this client.
		std::vector<uint32_t> OwnedIndexes();

		/// @brief Drops a setup index from OwnedIndexes without clearing it in
		/// Core - for setups consumed by loading them as a skeleton.
		void Untrack(uint32_t p_SkeletonIndex);

		/// @brief Default folder for .mskl files: Documents/ManusTemporarySkeleton
		/// (created on demand when saving).
		std::string DefaultSkeletonFolder();
	}
}
