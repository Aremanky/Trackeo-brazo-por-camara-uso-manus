#include "sdk/Trackers.hpp"

#include "ManusSDK.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <mutex>

namespace manus
{
	const char* Trackers::TypeName(TrackerType p_Type)
	{
		switch (p_Type)
		{
		case TrackerType_Head: return "Head";
		case TrackerType_Waist: return "Waist";
		case TrackerType_LeftHand: return "Left Hand";
		case TrackerType_RightHand: return "Right Hand";
		case TrackerType_LeftFoot: return "Left Foot";
		case TrackerType_RightFoot: return "Right Foot";
		case TrackerType_LeftUpperArm: return "Left Upper Arm";
		case TrackerType_RightUpperArm: return "Right Upper Arm";
		case TrackerType_LeftUpperLeg: return "Left Upper Leg";
		case TrackerType_RightUpperLeg: return "Right Upper Leg";
		case TrackerType_Controller: return "Controller";
		case TrackerType_Camera: return "Camera";
		default: return "Unknown";
		}
	}

	const char* Trackers::SystemTypeName(TrackerSystemType p_Type)
	{
		switch (p_Type)
		{
		case TrackerSystemType_Antilatency: return "Antilatency";
		case TrackerSystemType_ART: return "ART";
		case TrackerSystemType_OpenVR: return "OpenVR";
		case TrackerSystemType_Optitrack: return "OptiTrack";
		case TrackerSystemType_Vicon: return "Vicon";
		case TrackerSystemType_OpenXR: return "OpenXR";
		default: return "Unknown";
		}
	}

	const char* Trackers::QualityName(TrackingQuality p_Quality)
	{
		switch (p_Quality)
		{
		case TrackingQuality_Trackable: return "trackable";
		case TrackingQuality_BadTracking: return "bad";
		default: return "untrackable";
		}
	}

	// --- Live tracker data ---------------------------------------------------

	namespace
	{
		std::mutex g_TrackerMutex;
		std::map<std::string, TrackerData> g_TrackerData; // keyed by tracker id

		// --8<-- [start:tracker-stream-callback]
		void OnTrackerStreamCallback(const TrackerStreamInfo* const p_Info)
		{
			// The stream announces the count; each tracker is fetched by index.
			for (uint32_t i = 0; i < p_Info->trackerCount; ++i)
			{
				TrackerData t_Data{};
				if (CoreSdk_GetTrackerData(i, &t_Data) != SDKReturnCode_Success) continue;
				std::lock_guard<std::mutex> t_Lock(g_TrackerMutex);
				g_TrackerData[t_Data.trackerId.id] = t_Data;
			}
		}
		// --8<-- [end:tracker-stream-callback]

		void FillTrackerId(TrackerId& p_OutId, const std::string& p_Id)
		{
			std::memset(p_OutId.id, 0, sizeof(p_OutId.id));
			std::strncpy(p_OutId.id, p_Id.c_str(), sizeof(p_OutId.id) - 1);
		}
	}

	SdkResult Trackers::RegisterStream()
	{
		return CoreSdk_RegisterCallbackForTrackerStream(*OnTrackerStreamCallback);
	}

	// --8<-- [start:latest-data]
	std::vector<TrackerData> Trackers::LatestData()
	{
		std::lock_guard<std::mutex> t_Lock(g_TrackerMutex);
		std::vector<TrackerData> t_Result;
		t_Result.reserve(g_TrackerData.size());
		for (const auto& t_Entry : g_TrackerData) t_Result.push_back(t_Entry.second);
		return t_Result;
	}
	// --8<-- [end:latest-data]

	// --- Assignment ------------------------------------------------------------

	// --8<-- [start:assign-to-user]
	SdkResult Trackers::AssignToUser(const std::string& p_TrackerId, uint32_t p_UserId, TrackerType p_Role)
	{
		TrackerId t_Id;
		FillTrackerId(t_Id, p_TrackerId);
		SDKReturnCode t_Result = CoreSdk_AssignTrackerToUser(t_Id, p_UserId);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		return CoreSdk_AssignRoleToTracker(t_Id, p_Role);
	}
	// --8<-- [end:assign-to-user]

	// --8<-- [start:unassign]
	SdkResult Trackers::Unassign(const std::string& p_TrackerId)
	{
		// Trackers are unassigned by assigning them to user id 0.
		TrackerId t_Id;
		FillTrackerId(t_Id, p_TrackerId);
		SDKReturnCode t_Result = CoreSdk_AssignTrackerToUser(t_Id, 0);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		return CoreSdk_AssignRoleToTracker(t_Id, TrackerType_Unknown);
	}
	// --8<-- [end:unassign]

	SdkResult Trackers::SetOffset(uint32_t p_UserId, const TrackerOffset& p_Offset)
	{
		TrackerOffset t_Offset = p_Offset;
		return CoreSdk_SetTrackerOffset(p_UserId, &t_Offset);
	}

	// --- Timeouts ----------------------------------------------------------------

	// --8<-- [start:timeouts]
	SdkResult Trackers::GetTimeout(bool& p_OutEnabled, float& p_OutSeconds)
	{
		p_OutEnabled = false;
		p_OutSeconds = 0.0f;
		SDKReturnCode t_Result = CoreSdk_GetTrackerTimeOutEnabled(&p_OutEnabled);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		return CoreSdk_GetTrackerTimeOut(&p_OutSeconds);
	}

	SdkResult Trackers::SetTimeoutEnabled(bool p_Enabled)
	{
		return CoreSdk_SetTrackerTimeOutEnabled(p_Enabled);
	}

	SdkResult Trackers::SetTimeoutDuration(float p_Seconds)
	{
		return CoreSdk_SetTrackerTimeOut(p_Seconds);
	}
	// --8<-- [end:timeouts]

	// --- Tracking systems ------------------------------------------------------

	// --8<-- [start:tracker-systems]
	SdkResult Trackers::GetSystems(std::vector<TrackerSystem>& p_OutSystems)
	{
		p_OutSystems.clear();
		TrackerSystem t_Systems[MAX_NUM_TRACKER_SYSTEMS];
		uint32_t t_Count = 0;
		const SDKReturnCode t_Result = CoreSdk_GetTrackerSystemsSettings(t_Systems, &t_Count);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		p_OutSystems.assign(t_Systems, t_Systems + t_Count);
		return t_Result;
	}

	SdkResult Trackers::SetSystems(const std::vector<TrackerSystem>& p_Systems)
	{
		// Core expects the full array as obtained from GetSystems.
		TrackerSystem t_Systems[MAX_NUM_TRACKER_SYSTEMS]{};
		const size_t t_Count = std::min<size_t>(p_Systems.size(), MAX_NUM_TRACKER_SYSTEMS);
		std::copy(p_Systems.begin(), p_Systems.begin() + t_Count, t_Systems);
		return CoreSdk_SetTrackerSystemsSettings(t_Systems);
	}
	// --8<-- [end:tracker-systems]

	// --- Test tracker ------------------------------------------------------------

	// --8<-- [start:send-test-tracker]
	SdkResult Trackers::SendTestTracker(float p_HeightOffset)
	{
		TrackerData t_Data;
		TrackerData_Init(&t_Data);
		FillTrackerId(t_Data.trackerId, "Test Tracker");
		t_Data.isHmd = false;
		t_Data.trackerType = TrackerType_Unknown;
		t_Data.position = { 0.0f, p_HeightOffset, 0.0f };
		t_Data.rotation = { 1.0f, 0.0f, 0.0f, 0.0f };
		t_Data.quality = TrackingQuality_Trackable;
		t_Data.trackedPoint = TrackedPoint_Casing;
		return CoreSdk_SendDataForTrackers(&t_Data, 1);
	}
	// --8<-- [end:send-test-tracker]
}
