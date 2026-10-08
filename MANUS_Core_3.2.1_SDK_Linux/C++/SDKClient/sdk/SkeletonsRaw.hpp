// SDKClient sdk/ module - raw skeletons: per-glove hand data on the
// standardized MANUS hand model, straight from the estimation system, without
// retargeting. Includes the wrist motion source and the Metaglove
// casing/pinch compensation settings.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <cstdint>
#include <vector>

namespace manus
{
	namespace SkeletonsRaw
	{
		struct RawSkeleton
		{
			RawSkeletonInfo info;
			std::vector<SkeletonNode> nodes;
		};

		/// @brief Registers the raw-skeleton-stream callback. Call once, after
		/// SDK initialization. Data flows whenever a glove is active; buffered
		/// per glove id.
		SdkResult RegisterStream();

		/// @brief The most recent raw skeleton of a glove; false if none yet.
		bool LatestForGlove(uint32_t p_GloveId, RawSkeleton& p_OutSkeleton);

		/// @brief The static node hierarchy of a glove's raw skeleton (parent
		/// links, chain/joint classification). Needed to interpret node data,
		/// especially with a local coordinate system.
		SdkResult NodeHierarchy(uint32_t p_GloveId, std::vector<NodeInfo>& p_OutNodes);

		const char* HandMotionName(HandMotion p_Motion);
		const char* FingerJointName(FingerJointType p_Joint);
		const char* ChainName(ChainType p_Chain);

		/// @brief The wrist motion source of the raw skeleton stream:
		/// None, IMU, Tracker, Tracker (rotation only) or Auto.
		SdkResult GetHandMotion(HandMotion& p_OutMotion);
		SdkResult SetHandMotion(HandMotion p_Motion);

		/// @brief Pinch compensation: corrects finger tips while pinching.
		SdkResult GetPinchCompensation(bool& p_OutEnabled);
		SdkResult SetPinchCompensation(bool p_Enabled);

		/// @brief Casing compensation filter strength (Metaglove).
		SdkResult GetCasingCompensation(float& p_OutStrength);
		SdkResult SetCasingCompensation(float p_Strength);
	}
}
