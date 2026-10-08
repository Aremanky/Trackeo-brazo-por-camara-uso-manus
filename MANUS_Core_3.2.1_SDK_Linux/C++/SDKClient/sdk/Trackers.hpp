// SDKClient sdk/ module - trackers and tracking systems: live tracker data,
// user/role assignment, offsets, timeouts, per-system settings, and sending
// (test) tracker data into Core.
// Static tracker info (system, manufacturer, product) comes from the
// landscape - Landscape.trackers - see sdk/LandscapeCache.hpp.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <string>
#include <vector>

namespace manus
{
	namespace Trackers
	{
		const char* TypeName(TrackerType p_Type);
		const char* SystemTypeName(TrackerSystemType p_Type);
		const char* QualityName(TrackingQuality p_Quality);

		/// @brief Registers the tracker-stream callback. Call once, after SDK
		/// initialization. Live data is buffered per tracker id.
		SdkResult RegisterStream();

		/// @brief The most recent data of every tracker seen on the stream.
		std::vector<TrackerData> LatestData();

		/// @brief Assigns a tracker to a user with the given role (e.g.
		/// TrackerType_LeftHand). Roles tell Core which body part the tracker
		/// follows.
		SdkResult AssignToUser(const std::string& p_TrackerId, uint32_t p_UserId, TrackerType p_Role);

		/// @brief Unassigns a tracker (user id 0) and clears its role.
		SdkResult Unassign(const std::string& p_TrackerId);

		/// @brief Sets a tracker-to-hand offset for a user. The offset places
		/// the tracked point relative to the mount; measure it for your rig.
		SdkResult SetOffset(uint32_t p_UserId, const TrackerOffset& p_Offset);

		/// @brief Tracker timeout: when enabled, Core drops trackers that
		/// stopped sending data for the given duration.
		SdkResult GetTimeout(bool& p_OutEnabled, float& p_OutSeconds);
		SdkResult SetTimeoutEnabled(bool p_Enabled);
		SdkResult SetTimeoutDuration(float p_Seconds);

		/// @brief All tracking systems Core knows (OpenVR, Optitrack, ...) with
		/// their settings.
		SdkResult GetSystems(std::vector<TrackerSystem>& p_OutSystems);

		/// @brief Writes systems back to Core. Pass the SAME set obtained from
		/// GetSystems (with your modifications) - Core expects the full array.
		SdkResult SetSystems(const std::vector<TrackerSystem>& p_Systems);

		/// @brief Sends one custom/test tracker pose into Core, named
		/// "Test Tracker". Send repeatedly (e.g. ~30 Hz) to animate it; this is
		/// how external tracking data is injected via the SDK.
		SdkResult SendTestTracker(float p_HeightOffset);
	}
}
