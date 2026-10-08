#include "sdk/SkeletonsRetargeted.hpp"

#include "ManusSDK.h"

#include <algorithm>
#include <cstdio>
#include <map>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		std::map<uint32_t, SkeletonsRetargeted::LiveSkeleton> g_Latest; // keyed by skeleton id
		std::vector<uint32_t> g_LoadedIds;

		// --8<-- [start:skeleton-stream-callback]
		void OnSkeletonStreamCallback(const SkeletonStreamInfo* const p_Info)
		{
			// An update only contains skeletons whose data changed, so entries
			// are merged into the buffer instead of replacing it wholesale.
			for (uint32_t i = 0; i < p_Info->skeletonsCount; ++i)
			{
				SkeletonsRetargeted::LiveSkeleton t_Skeleton;
				if (CoreSdk_GetSkeletonInfo(i, &t_Skeleton.info) != SDKReturnCode_Success) continue;
				t_Skeleton.nodes.resize(t_Skeleton.info.nodesCount);
				if (CoreSdk_GetSkeletonData(i, t_Skeleton.nodes.data(), t_Skeleton.info.nodesCount) != SDKReturnCode_Success)
					continue;
				const uint32_t t_Id = t_Skeleton.info.id;
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				g_Latest[t_Id] = std::move(t_Skeleton);
			}
		}
		// --8<-- [end:skeleton-stream-callback]

		// --8<-- [start:hand-nodes]
		NodeSetup MakeNode(uint32_t p_Id, uint32_t p_ParentId, float p_X, float p_Y, float p_Z, const char* p_Name)
		{
			NodeSetup t_Node;
			NodeSetup_Init(&t_Node);
			t_Node.id = p_Id;                 // unique per node in a skeleton
			t_Node.parentID = p_ParentId;     // the root has itself (0) as parent
			t_Node.type = NodeType_Joint;
			t_Node.settings.usedSettings = NodeSettingsFlag_None;
			t_Node.transform.position = { p_X, p_Y, p_Z };
			std::snprintf(t_Node.name, sizeof(t_Node.name), "%s", p_Name);
			return t_Node;
		}

		// Example joint positions of a hand lying flat on a table, in meters,
		// world space. Per finger: 4 joints from knuckle to tip.
		// (Illustrative values - replace with your own model's data.)
		const float g_FingerX[5] = { 0.025320f, 0.052904f, 0.051287f, 0.049802f, 0.047309f };
		const float g_FingerY[5] = { 0.024950f, 0.011181f, 0.000000f, -0.011274f, -0.020145f };
		const float g_JointLengths[5][3] = {
			{ 0.032742f, 0.028739f, 0.028739f }, // thumb
			{ 0.038257f, 0.020884f, 0.018759f }, // index
			{ 0.041861f, 0.024766f, 0.019683f }, // middle
			{ 0.039736f, 0.023564f, 0.019868f }, // ring
			{ 0.033175f, 0.018020f, 0.019129f }, // pinky
		};

		bool SetupHandNodes(uint32_t p_SetupIndex, Side p_Side)
		{
			// Root node: id 0, parent 0 (= no parent).
			if (CoreSdk_AddNodeToSkeletonSetup(p_SetupIndex, MakeNode(0, 0, 0, 0, 0, "Hand")) != SDKReturnCode_Success)
				return false;

			// The left hand mirrors the right on the Y axis.
			const float t_Mirror = p_Side == Side_Left ? -1.0f : 1.0f;
			uint32_t t_NodeId = 1;
			for (int t_Finger = 0; t_Finger < 5; ++t_Finger)
			{
				float t_X = g_FingerX[t_Finger];
				const float t_Y = t_Mirror * g_FingerY[t_Finger];
				uint32_t t_ParentId = 0;
				for (int t_Joint = 0; t_Joint < 4; ++t_Joint)
				{
					if (CoreSdk_AddNodeToSkeletonSetup(p_SetupIndex,
						MakeNode(t_NodeId, t_ParentId, t_X, t_Y, 0.0f, "fingerdigit")) != SDKReturnCode_Success)
						return false;
					t_ParentId = t_NodeId++;
					if (t_Joint < 3) t_X += g_JointLengths[t_Finger][t_Joint];
				}
			}
			return true;
		}
		// --8<-- [end:hand-nodes]

		// --8<-- [start:hand-chains]
		bool SetupHandChains(uint32_t p_SetupIndex, Side p_Side)
		{
			// Chains tell Core which nodes belong to which body part and what
			// glove data drives them. First the hand (wrist) chain...
			{
				ChainSettings t_Settings;
				ChainSettings_Init(&t_Settings);
				t_Settings.usedSettings = ChainType_Hand;
				t_Settings.hand.handMotion = HandMotion_IMU;
				t_Settings.hand.fingerChainIdsUsed = 5;
				for (int i = 0; i < 5; ++i) t_Settings.hand.fingerChainIds[i] = i + 1;

				ChainSetup t_Chain;
				ChainSetup_Init(&t_Chain);
				t_Chain.id = 0;
				t_Chain.type = ChainType_Hand;
				t_Chain.dataType = ChainType_Hand;
				t_Chain.side = p_Side;
				t_Chain.dataIndex = 0;
				t_Chain.nodeIdCount = 1;
				t_Chain.nodeIds[0] = 0; // the root node
				t_Chain.settings = t_Settings;
				if (CoreSdk_AddChainToSkeletonSetup(p_SetupIndex, t_Chain) != SDKReturnCode_Success) return false;
			}

			// ...then one chain per finger, each linking back to the hand chain.
			const ChainType t_FingerTypes[5] = {
				ChainType_FingerThumb, ChainType_FingerIndex, ChainType_FingerMiddle,
				ChainType_FingerRing, ChainType_FingerPinky };
			for (int i = 0; i < 5; ++i)
			{
				ChainSettings t_Settings;
				ChainSettings_Init(&t_Settings);
				t_Settings.usedSettings = t_FingerTypes[i];
				t_Settings.finger.handChainId = 0;
				t_Settings.finger.metacarpalBoneId = -1; // no separate metacarpal node in this example
				t_Settings.finger.useLeafAtEnd = false;

				ChainSetup t_Chain;
				ChainSetup_Init(&t_Chain);
				t_Chain.id = i + 1;
				t_Chain.type = t_FingerTypes[i];
				t_Chain.dataType = t_FingerTypes[i];
				t_Chain.side = p_Side;
				t_Chain.dataIndex = 0;
				t_Chain.nodeIdCount = 4;
				for (int j = 0; j < 4; ++j) t_Chain.nodeIds[j] = (i * 4) + 1 + j;
				t_Chain.settings = t_Settings;
				if (CoreSdk_AddChainToSkeletonSetup(p_SetupIndex, t_Chain) != SDKReturnCode_Success) return false;
			}
			return true;
		}
		// --8<-- [end:hand-chains]
	}

	SdkResult SkeletonsRetargeted::RegisterStream()
	{
		return CoreSdk_RegisterCallbackForSkeletonStream(*OnSkeletonStreamCallback);
	}

	std::vector<SkeletonsRetargeted::LiveSkeleton> SkeletonsRetargeted::Latest()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		std::vector<LiveSkeleton> t_Result;
		t_Result.reserve(g_Latest.size());
		for (const auto& t_Entry : g_Latest) t_Result.push_back(t_Entry.second);
		return t_Result;
	}

	bool SkeletonsRetargeted::LatestForSkeleton(uint32_t p_SkeletonId, LiveSkeleton& p_OutSkeleton)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		const auto t_Found = g_Latest.find(p_SkeletonId);
		if (t_Found == g_Latest.end()) return false;
		p_OutSkeleton = t_Found->second;
		return true;
	}

	std::vector<uint32_t> SkeletonsRetargeted::LoadedIds()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_LoadedIds;
	}

	// --8<-- [start:example-hand]
	SdkResult SkeletonsRetargeted::CreateExampleHandSetup(Side p_Side, uint32_t& p_OutIndex)
	{
		p_OutIndex = 0;

		SkeletonSetupInfo t_Setup;
		SkeletonSetupInfo_Init(&t_Setup);
		t_Setup.type = SkeletonType_Hand;
		t_Setup.settings.scaleToTarget = true;
		t_Setup.settings.useEndPointApproximations = true;
		// Animate this skeleton with the gloves of the user at index 0.
		// A skeleton targeting a non-existent user simply does not animate.
		t_Setup.settings.targetType = SkeletonTargetType_UserIndexData;
		t_Setup.settings.skeletonTargetUserIndexData.userIndex = 0;
		std::snprintf(t_Setup.name, sizeof(t_Setup.name), "%s", p_Side == Side_Left ? "LeftHand" : "RightHand");

		const SDKReturnCode t_Result = CoreSdk_CreateSkeletonSetup(t_Setup, &p_OutIndex);
		if (t_Result != SDKReturnCode_Success) return t_Result;

		if (!SetupHandNodes(p_OutIndex, p_Side)) return SDKReturnCode_Error;
		if (!SetupHandChains(p_OutIndex, p_Side)) return SDKReturnCode_Error;
		return SDKReturnCode_Success;
	}

	SdkResult SkeletonsRetargeted::LoadExampleHand(Side p_Side, bool p_SendToDevTools,
		uint32_t p_SessionId, uint32_t& p_OutSkeletonId)
	{
		p_OutSkeletonId = 0;

		uint32_t t_SetupIndex = 0;
		SdkResult t_Result = CreateExampleHandSetup(p_Side, t_SetupIndex);
		if (!t_Result.Ok()) return t_Result;

		if (p_SendToDevTools)
		{
			// Saving the setup as a temporary skeleton makes it visible to the
			// DevTools application for inspection/editing.
			t_Result = CoreSdk_SaveTemporarySkeleton(t_SetupIndex, p_SessionId, true);
			if (!t_Result.Ok()) return t_Result;
		}

		t_Result = CoreSdk_LoadSkeleton(t_SetupIndex, &p_OutSkeletonId);
		if (!t_Result.Ok()) return t_Result;
		if (p_OutSkeletonId == 0) return SDKReturnCode_Error;

		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_LoadedIds.push_back(p_OutSkeletonId);
		return SDKReturnCode_Success;
	}
	// --8<-- [end:example-hand]

	SdkResult SkeletonsRetargeted::LoadSetup(uint32_t p_SetupIndex, uint32_t& p_OutSkeletonId)
	{
		p_OutSkeletonId = 0;
		const SdkResult t_Result = CoreSdk_LoadSkeleton(p_SetupIndex, &p_OutSkeletonId);
		if (!t_Result.Ok()) return t_Result;
		if (p_OutSkeletonId == 0) return SDKReturnCode_Error;
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_LoadedIds.push_back(p_OutSkeletonId);
		return SDKReturnCode_Success;
	}

	// --8<-- [start:unload]
	SdkResult SkeletonsRetargeted::Unload(uint32_t p_SkeletonId)
	{
		const SDKReturnCode t_Result = CoreSdk_UnloadSkeleton(p_SkeletonId);
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_LoadedIds.erase(std::remove(g_LoadedIds.begin(), g_LoadedIds.end(), p_SkeletonId), g_LoadedIds.end());
		g_Latest.erase(p_SkeletonId); // no ghost entry after unloading
		return t_Result;
	}
	// --8<-- [end:unload]
}
