// SDKClient sdk/ module - the user system: grouping gloves and dongles per user.
// User *data* (names, assigned devices) comes from the landscape - see
// sdk/LandscapeCache.hpp (Landscape.users).
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <string>

namespace manus
{
	namespace Users
	{
		/// @brief Creates a user with the given name; p_OutId receives the new user's id.
		SdkResult Add(const std::string& p_Name, uint32_t& p_OutId);

		SdkResult Remove(uint32_t p_UserId);

		SdkResult Rename(uint32_t p_UserId, const std::string& p_Name);

		/// @brief Moves the user up/down in Core's user list.
		SdkResult MoveUp(uint32_t p_UserId);
		SdkResult MoveDown(uint32_t p_UserId);

		/// @brief Assigns a dongle to a user. Pass dongle id 0 to unassign.
		SdkResult AssignDongle(uint32_t p_UserId, uint32_t p_DongleId);

		/// @brief Assigns a glove to a user's left or right hand.
		/// Pass glove id 0 to unassign that side.
		SdkResult AssignGlove(uint32_t p_UserId, uint32_t p_GloveId, Side p_Side);

		/// @brief Automatic glove assignment. Only available in Core Integrated.
		SdkResult GetAutoAssignment(bool& p_OutEnabled);
		SdkResult SetAutoAssignment(bool p_Enabled);

		/// @brief Finds the user a glove is assigned to (as either hand).
		/// Core only produces skeleton, ergonomics and gesture data for
		/// gloves that are assigned to a user (raw device data flows
		/// regardless of assignment).
		bool TryFindUserForGlove(const Landscape& p_Landscape, uint32_t p_GloveId, UserLandscapeData& p_OutUser);

		/// @brief Same, on the latest landscape snapshot.
		bool TryFindUserForGlove(uint32_t p_GloveId, UserLandscapeData& p_OutUser);
	}
}
