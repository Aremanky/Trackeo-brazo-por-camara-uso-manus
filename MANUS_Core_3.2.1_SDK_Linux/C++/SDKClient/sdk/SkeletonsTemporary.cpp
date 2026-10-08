#include "sdk/SkeletonsTemporary.hpp"

#include "sdk/Paths.hpp"
#include "sdk/SkeletonsRetargeted.hpp"

#include "ManusSDK.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		std::vector<uint32_t> g_OwnedIndexes;

		void TrackIndex(uint32_t p_Index)
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_OwnedIndexes.push_back(p_Index);
		}

		void UntrackIndex(uint32_t p_Index)
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_OwnedIndexes.erase(
				std::remove(g_OwnedIndexes.begin(), g_OwnedIndexes.end(), p_Index), g_OwnedIndexes.end());
		}
	}

	SdkResult SkeletonsTemporary::CountForAllSessions(uint32_t& p_OutCount)
	{
		p_OutCount = 0;
		TemporarySkeletonCountForAllSessions t_Counts{};
		const SDKReturnCode t_Result = CoreSdk_GetTemporarySkeletonCountForAllSessions(&t_Counts);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		for (uint32_t i = 0; i < t_Counts.sessionsCount; ++i)
			p_OutCount += t_Counts.temporarySkeletonCountForSessions[i].skeletonCount;
		return t_Result;
	}

	// --8<-- [start:temporary-skeletons]
	SdkResult SkeletonsTemporary::BuildExample(uint32_t p_SessionId, uint32_t& p_OutIndex)
	{
		SdkResult t_Result = SkeletonsRetargeted::CreateExampleHandSetup(Side_Left, p_OutIndex);
		if (!t_Result.Ok()) return t_Result;

		// Saving (without loading) is what shares the setup with DevTools.
		t_Result = CoreSdk_SaveTemporarySkeleton(p_OutIndex, p_SessionId, false);
		if (t_Result.Ok()) TrackIndex(p_OutIndex);
		return t_Result;
	}

	SdkResult SkeletonsTemporary::SaveToFile(uint32_t p_SkeletonIndex, uint32_t p_SessionId, const std::string& p_FilePath)
	{
		// Compression must be requested first; it also reports the data size.
		uint32_t t_SizeInBytes = 0;
		SdkResult t_Result = CoreSdk_CompressTemporarySkeletonAndGetSize(p_SkeletonIndex, p_SessionId, &t_SizeInBytes);
		if (!t_Result.Ok()) return t_Result;

		std::vector<unsigned char> t_Data(t_SizeInBytes);
		t_Result = CoreSdk_GetCompressedTemporarySkeletonData(t_Data.data(), t_SizeInBytes);
		if (!t_Result.Ok()) return t_Result;

		std::error_code t_Error;
		std::filesystem::create_directories(std::filesystem::path(p_FilePath).parent_path(), t_Error);
		std::ofstream t_File(p_FilePath, std::ios::binary);
		if (!t_File) return SDKReturnCode_InvalidArgument;
		t_File.write((const char*)t_Data.data(), t_Data.size());
		return SDKReturnCode_Success;
	}

	SdkResult SkeletonsTemporary::LoadFromFile(uint32_t p_SessionId, const std::string& p_FilePath, uint32_t& p_OutIndex)
	{
		p_OutIndex = 0;

		std::ifstream t_File(p_FilePath, std::ios::binary);
		if (!t_File) return SDKReturnCode_InvalidArgument;
		std::vector<unsigned char> t_Data(
			(std::istreambuf_iterator<char>(t_File)), std::istreambuf_iterator<char>());
		if (t_Data.empty()) return SDKReturnCode_InvalidArgument;

		// An empty setup acts as the container for the file's data.
		SkeletonSetupInfo t_Setup;
		SkeletonSetupInfo_Init(&t_Setup);
		SdkResult t_Result = CoreSdk_CreateSkeletonSetup(t_Setup, &p_OutIndex);
		if (!t_Result.Ok()) return t_Result;

		t_Result = CoreSdk_GetTemporarySkeletonFromCompressedData(
			p_OutIndex, p_SessionId, t_Data.data(), (uint32_t)t_Data.size());
		if (t_Result.Ok()) TrackIndex(p_OutIndex);
		return t_Result;
	}
	// --8<-- [end:temporary-skeletons]

	SdkResult SkeletonsTemporary::Clear(uint32_t p_SkeletonIndex, uint32_t p_SessionId)
	{
		const SdkResult t_Result = CoreSdk_ClearTemporarySkeleton(p_SkeletonIndex, p_SessionId);
		if (t_Result.Ok()) UntrackIndex(p_SkeletonIndex);
		return t_Result;
	}

	SdkResult SkeletonsTemporary::ClearAll()
	{
		const SdkResult t_Result = CoreSdk_ClearAllTemporarySkeletons();
		if (t_Result.Ok())
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_OwnedIndexes.clear();
		}
		return t_Result;
	}

	void SkeletonsTemporary::Untrack(uint32_t p_SkeletonIndex)
	{
		UntrackIndex(p_SkeletonIndex);
	}

	std::vector<uint32_t> SkeletonsTemporary::OwnedIndexes()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_OwnedIndexes;
	}

	std::string SkeletonsTemporary::DefaultSkeletonFolder()
	{
		return Paths::DocumentsSubfolder("ManusTemporarySkeleton");
	}
}
