#include "sdk/SkeletonsRaw.hpp"

#include "ManusSDK.h"

#include <map>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		std::map<uint32_t, SkeletonsRaw::RawSkeleton> g_RawSkeletons; // keyed by glove id

		// --8<-- [start:raw-skeleton-stream-callback]
		void OnRawSkeletonStreamCallback(const SkeletonStreamInfo* const p_Info)
		{
			for (uint32_t i = 0; i < p_Info->skeletonsCount; ++i)
			{
				SkeletonsRaw::RawSkeleton t_Skeleton;
				if (CoreSdk_GetRawSkeletonInfo(i, &t_Skeleton.info) != SDKReturnCode_Success) continue;
				t_Skeleton.nodes.resize(t_Skeleton.info.nodesCount);
				if (CoreSdk_GetRawSkeletonData(i, t_Skeleton.nodes.data(), t_Skeleton.info.nodesCount) != SDKReturnCode_Success)
					continue;
				const uint32_t t_GloveId = t_Skeleton.info.gloveId;
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				g_RawSkeletons[t_GloveId] = std::move(t_Skeleton);
			}
		}
		// --8<-- [end:raw-skeleton-stream-callback]
	}

	SdkResult SkeletonsRaw::RegisterStream()
	{
		return CoreSdk_RegisterCallbackForRawSkeletonStream(*OnRawSkeletonStreamCallback);
	}

	bool SkeletonsRaw::LatestForGlove(uint32_t p_GloveId, RawSkeleton& p_OutSkeleton)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		const auto t_Found = g_RawSkeletons.find(p_GloveId);
		if (t_Found == g_RawSkeletons.end()) return false;
		p_OutSkeleton = t_Found->second;
		return true;
	}

	// --8<-- [start:node-hierarchy]
	SdkResult SkeletonsRaw::NodeHierarchy(uint32_t p_GloveId, std::vector<NodeInfo>& p_OutNodes)
	{
		p_OutNodes.clear();
		uint32_t t_Count = 0;
		SDKReturnCode t_Result = CoreSdk_GetRawSkeletonNodeCount(p_GloveId, &t_Count);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		p_OutNodes.resize(t_Count);
		t_Result = CoreSdk_GetRawSkeletonNodeInfoArray(p_GloveId, p_OutNodes.data(), t_Count);
		if (t_Result != SDKReturnCode_Success) p_OutNodes.clear();
		return t_Result;
	}
	// --8<-- [end:node-hierarchy]

	const char* SkeletonsRaw::HandMotionName(HandMotion p_Motion)
	{
		switch (p_Motion)
		{
		case HandMotion_None: return "None (wrist stays in place)";
		case HandMotion_IMU: return "IMU (wrist rotation from the glove IMU)";
		case HandMotion_Tracker: return "Tracker (wrist position + rotation)";
		case HandMotion_Tracker_RotationOnly: return "Tracker (rotation only)";
		case HandMotion_Auto: return "Auto (best available source)";
		default: return "Unknown";
		}
	}

	const char* SkeletonsRaw::FingerJointName(FingerJointType p_Joint)
	{
		switch (p_Joint)
		{
		case FingerJointType_Metacarpal: return "Metacarpal";
		case FingerJointType_Proximal: return "Proximal";
		case FingerJointType_Intermediate: return "Intermediate";
		case FingerJointType_Distal: return "Distal";
		default: return "-";
		}
	}

	const char* SkeletonsRaw::ChainName(ChainType p_Chain)
	{
		switch (p_Chain)
		{
		case ChainType_Hand: return "Hand";
		case ChainType_FingerThumb: return "Thumb";
		case ChainType_FingerIndex: return "Index";
		case ChainType_FingerMiddle: return "Middle";
		case ChainType_FingerRing: return "Ring";
		case ChainType_FingerPinky: return "Pinky";
		case ChainType_Arm: return "Arm";
		case ChainType_Leg: return "Leg";
		case ChainType_Neck: return "Neck";
		case ChainType_Spine: return "Spine";
		case ChainType_Pelvis: return "Pelvis";
		case ChainType_Head: return "Head";
		case ChainType_Shoulder: return "Shoulder";
		case ChainType_Foot: return "Foot";
		case ChainType_Toe: return "Toe";
		default: return "-";
		}
	}

	SdkResult SkeletonsRaw::GetHandMotion(HandMotion& p_OutMotion)
	{
		p_OutMotion = HandMotion_None;
		return CoreSdk_GetRawSkeletonHandMotion(&p_OutMotion);
	}

	SdkResult SkeletonsRaw::SetHandMotion(HandMotion p_Motion)
	{
		return CoreSdk_SetRawSkeletonHandMotion(p_Motion);
	}

	SdkResult SkeletonsRaw::GetPinchCompensation(bool& p_OutEnabled)
	{
		p_OutEnabled = false;
		return CoreSdk_GetRawSkeletonPinchCompensation(&p_OutEnabled);
	}

	SdkResult SkeletonsRaw::SetPinchCompensation(bool p_Enabled)
	{
		return CoreSdk_SetRawSkeletonPinchCompensation(p_Enabled);
	}

	SdkResult SkeletonsRaw::GetCasingCompensation(float& p_OutStrength)
	{
		p_OutStrength = 0.0f;
		return CoreSdk_GetRawSkeletonCasingCompensation(&p_OutStrength);
	}

	SdkResult SkeletonsRaw::SetCasingCompensation(float p_Strength)
	{
		return CoreSdk_SetRawSkeletonCasingCompensation(p_Strength);
	}
}
