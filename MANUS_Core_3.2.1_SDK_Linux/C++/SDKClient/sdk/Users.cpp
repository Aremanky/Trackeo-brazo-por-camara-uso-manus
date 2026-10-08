#include "sdk/Users.hpp"

#include "sdk/LandscapeCache.hpp"

#include "ManusSDK.h"

namespace manus
{
	// --8<-- [start:add-user]
	SdkResult Users::Add(const std::string& p_Name, uint32_t& p_OutId)
	{
		p_OutId = 0;
		// The SDK header takes a non-const char*; it does not modify the string.
		return CoreSdk_AddUser(const_cast<char*>(p_Name.c_str()), &p_OutId);
	}
	// --8<-- [end:add-user]

	// --8<-- [start:remove-user]
	SdkResult Users::Remove(uint32_t p_UserId)
	{
		return CoreSdk_RemoveUser(p_UserId);
	}
	// --8<-- [end:remove-user]

	// --8<-- [start:rename-user]
	SdkResult Users::Rename(uint32_t p_UserId, const std::string& p_Name)
	{
		return CoreSdk_SetUserName(p_UserId, const_cast<char*>(p_Name.c_str()));
	}
	// --8<-- [end:rename-user]

	// --8<-- [start:move-user]
	SdkResult Users::MoveUp(uint32_t p_UserId)
	{
		return CoreSdk_MoveUserUp(p_UserId);
	}

	SdkResult Users::MoveDown(uint32_t p_UserId)
	{
		return CoreSdk_MoveUserDown(p_UserId);
	}
	// --8<-- [end:move-user]

	// --8<-- [start:assign-dongle]
	SdkResult Users::AssignDongle(uint32_t p_UserId, uint32_t p_DongleId)
	{
		return CoreSdk_AssignDongleToUser(p_UserId, p_DongleId);
	}
	// --8<-- [end:assign-dongle]

	// --8<-- [start:assign-glove]
	SdkResult Users::AssignGlove(uint32_t p_UserId, uint32_t p_GloveId, Side p_Side)
	{
		return CoreSdk_AssignGloveToUser(p_UserId, p_GloveId, p_Side);
	}
	// --8<-- [end:assign-glove]

	SdkResult Users::GetAutoAssignment(bool& p_OutEnabled)
	{
		p_OutEnabled = false;
		return CoreSdk_GetAutoUserAssignment(&p_OutEnabled);
	}

	SdkResult Users::SetAutoAssignment(bool p_Enabled)
	{
		return CoreSdk_SetAutoUserAssignment(p_Enabled);
	}

	// --8<-- [start:find-user-for-glove]
	bool Users::TryFindUserForGlove(const Landscape& p_Landscape, uint32_t p_GloveId, UserLandscapeData& p_OutUser)
	{
		if (p_GloveId == 0) return false;
		for (uint32_t i = 0; i < p_Landscape.users.userCount; ++i)
		{
			const UserLandscapeData& t_User = p_Landscape.users.users[i];
			if (t_User.leftGloveID == p_GloveId || t_User.rightGloveID == p_GloveId)
			{
				p_OutUser = t_User;
				return true;
			}
		}
		return false;
	}
	// --8<-- [end:find-user-for-glove]

	bool Users::TryFindUserForGlove(uint32_t p_GloveId, UserLandscapeData& p_OutUser)
	{
		const Landscape t_Landscape = LandscapeCache::Snapshot();
		return TryFindUserForGlove(t_Landscape, p_GloveId, p_OutUser);
	}
}
