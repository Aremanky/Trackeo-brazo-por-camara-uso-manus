// SDKClient sdk/ module - the latest landscape from MANUS Core.
//
// The landscape is Core's record of everything it currently sees (devices,
// users, skeletons, trackers, timecode, gestures) and arrives about once per
// second via a stream callback. The callback copies it here under a mutex;
// everything else reads snapshots. UI code never blocks the SDK thread.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <functional>
#include <vector>

namespace manus
{
	namespace LandscapeCache
	{
		/// @brief Registers the SDK's landscape-stream callback. Call once, after SDK initialization.
		SdkResult Register();

		/// @brief True once the first landscape has arrived from Core.
		bool HasLandscape();

		/// @brief A copy of the most recent landscape.
		Landscape Snapshot();

		/// @brief Gloves in ascending-ID order. (The raw landscape array order
		/// can change between updates, which makes lists jump around.)
		std::vector<GloveLandscapeData> GlovesSortedById();

		/// @brief Dongles in ascending-ID order.
		std::vector<DongleLandscapeData> DonglesSortedById();

		/// @brief Gesture id/name pairs, fetched alongside each landscape update.
		std::vector<GestureLandscapeData> Gestures();

		/// @brief Invoked (from the SDK thread) whenever a new landscape arrives.
		void SetOnChanged(std::function<void()> p_OnChanged);
	}
}
