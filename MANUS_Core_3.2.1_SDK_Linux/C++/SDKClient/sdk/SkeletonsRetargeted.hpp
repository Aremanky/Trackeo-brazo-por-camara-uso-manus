// SDKClient sdk/ module - retargeted skeletons: build a skeleton setup
// (nodes + chains), load it into Core, and receive the animated result on the
// skeleton stream. This is THE central concept for getting hand animation out
// of the SDK - the example builds a minimal 21-node hand.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <vector>

namespace manus
{
	namespace SkeletonsRetargeted
	{
		struct LiveSkeleton
		{
			SkeletonInfo info;
			std::vector<SkeletonNode> nodes; // world/local per the coordinate system set at init
		};

		/// @brief Registers the skeleton-stream callback. Call once, after SDK
		/// initialization. The stream only flows while skeletons are loaded,
		/// and an update only contains the skeletons that changed - data is
		/// therefore buffered per skeleton id.
		SdkResult RegisterStream();

		/// @brief The most recent data of every skeleton seen on the stream,
		/// in ascending-id order.
		std::vector<LiveSkeleton> Latest();

		/// @brief The most recent data of one skeleton; false if none yet.
		bool LatestForSkeleton(uint32_t p_SkeletonId, LiveSkeleton& p_OutSkeleton);

		/// @brief Skeleton ids this client loaded into Core (via LoadExampleHand).
		std::vector<uint32_t> LoadedIds();

		/// @brief Builds the example hand *setup*: a root node, 5 fingers of 4
		/// joints each (flat-on-a-table pose), one hand chain and 5 finger
		/// chains. The setup is temporary until loaded. p_OutIndex identifies it.
		SdkResult CreateExampleHandSetup(Side p_Side, uint32_t& p_OutIndex);

		/// @brief Builds the example hand and loads it into Core for animation,
		/// targeting user index 0. With p_SendToDevTools the setup is also
		/// saved as a temporary skeleton so the DevTools application can
		/// inspect and edit it.
		SdkResult LoadExampleHand(Side p_Side, bool p_SendToDevTools, uint32_t p_SessionId, uint32_t& p_OutSkeletonId);

		/// @brief Loads an existing skeleton setup (e.g. one imported from a
		/// .mskl file via SkeletonsTemporary::LoadFromFile) into Core for
		/// animation.
		SdkResult LoadSetup(uint32_t p_SetupIndex, uint32_t& p_OutSkeletonId);

		/// @brief Unloads a previously loaded skeleton.
		SdkResult Unload(uint32_t p_SkeletonId);
	}
}
