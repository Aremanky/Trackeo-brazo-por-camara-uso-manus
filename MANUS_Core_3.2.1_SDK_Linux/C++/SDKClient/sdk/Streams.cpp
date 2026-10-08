#include "sdk/Streams.hpp"

#include "ManusSDK.h"

#include <deque>
#include <map>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		std::deque<std::string> g_Lines;
		std::function<void()> g_OnChanged;

		constexpr size_t MAX_LINES = 500;

		void OnLogCallback(LogSeverity /*p_Severity*/, const char* const p_Log, uint32_t /*p_Length*/)
		{
			Logs::Push(std::string(p_Log));
		}
	}

	SdkResult Logs::Register()
	{
		return CoreSdk_RegisterCallbackForOnLog(*OnLogCallback);
	}

	void Logs::Push(const std::string& p_Line)
	{
		std::function<void()> t_OnChanged;
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_Lines.push_back(p_Line);
			while (g_Lines.size() > MAX_LINES) g_Lines.pop_front();
			t_OnChanged = g_OnChanged;
		}
		if (t_OnChanged) t_OnChanged();
	}

	std::vector<std::string> Logs::Tail(size_t p_Count)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		const size_t t_Count = p_Count < g_Lines.size() ? p_Count : g_Lines.size();
		return std::vector<std::string>(g_Lines.end() - t_Count, g_Lines.end());
	}

	void Logs::SetOnChanged(std::function<void()> p_OnChanged)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_OnChanged = std::move(p_OnChanged);
	}

	// --- Gesture stream ----------------------------------------------------

	namespace
	{
		std::mutex g_TimestampMutex;
		ManusTimestamp g_LatestTimestamp{};
		bool g_HasTimestamp = false;

		void FeedTimestamp(ManusTimestamp p_Timestamp)
		{
			std::lock_guard<std::mutex> t_Lock(g_TimestampMutex);
			g_LatestTimestamp = p_Timestamp;
			g_HasTimestamp = true;
		}
	}

	namespace
	{
		std::mutex g_GestureMutex;
		std::map<uint32_t, GestureStream::GloveGestures> g_GloveGestures;

		// --8<-- [start:gesture-stream-callback]
		void OnGestureStreamCallback(const GestureStreamInfo* const p_Info)
		{
			FeedTimestamp(p_Info->publishTime);
			for (uint32_t i = 0; i < p_Info->gestureProbabilitiesCount; ++i)
			{
				// The stream announces how many probability sets are available;
				// each set is fetched in chunks of MAX_GESTURE_DATA_CHUNK_SIZE.
				GestureProbabilities t_Chunk{};
				if (CoreSdk_GetGestureStreamData(i, 0, &t_Chunk) != SDKReturnCode_Success) continue;
				if (t_Chunk.isUserID) continue; // sets can belong to users too; we buffer per glove

				const uint32_t t_GloveId = t_Chunk.id;
				GestureStream::GloveGestures t_Data;
				t_Data.totalCount = t_Chunk.totalGestureCount;
				t_Data.probabilities.reserve(t_Chunk.totalGestureCount);

				uint32_t t_Read = 0;
				while (true)
				{
					for (uint32_t j = 0; j < t_Chunk.gestureCount; ++j)
						t_Data.probabilities.push_back(t_Chunk.gestureData[j]);
					t_Read += t_Chunk.gestureCount;
					if (t_Read >= t_Data.totalCount || t_Chunk.gestureCount == 0) break;
					if (CoreSdk_GetGestureStreamData(i, t_Read, &t_Chunk) != SDKReturnCode_Success) break;
				}

				std::lock_guard<std::mutex> t_Lock(g_GestureMutex);
				g_GloveGestures[t_GloveId] = std::move(t_Data);
			}
		}
		// --8<-- [end:gesture-stream-callback]
	}

	SdkResult GestureStream::Register()
	{
		return CoreSdk_RegisterCallbackForGestureStream(*OnGestureStreamCallback);
	}

	bool GestureStream::LatestForGlove(uint32_t p_GloveId, GloveGestures& p_OutGestures)
	{
		std::lock_guard<std::mutex> t_Lock(g_GestureMutex);
		const auto t_Found = g_GloveGestures.find(p_GloveId);
		if (t_Found == g_GloveGestures.end()) return false;
		p_OutGestures = t_Found->second;
		return true;
	}

	// --- Raw device data -------------------------------------------------------

	namespace
	{
		std::mutex g_RawDeviceMutex;
		std::map<uint32_t, RawDeviceData> g_RawDeviceData; // keyed by device id

		// --8<-- [start:raw-device-callback]
		void OnRawDeviceDataStreamCallback(const RawDeviceDataInfo* const p_Info)
		{
			FeedTimestamp(p_Info->publishTime);
			for (uint32_t i = 0; i < p_Info->rawDeviceDataCount; ++i)
			{
				RawDeviceData t_Data{};
				if (CoreSdk_GetRawDeviceData(i, &t_Data) != SDKReturnCode_Success) continue;
				std::lock_guard<std::mutex> t_Lock(g_RawDeviceMutex);
				g_RawDeviceData[t_Data.id] = t_Data;
			}
		}
		// --8<-- [end:raw-device-callback]
	}

	SdkResult RawDeviceStream::Register()
	{
		return CoreSdk_RegisterCallbackForRawDeviceDataStream(*OnRawDeviceDataStreamCallback);
	}

	// --8<-- [start:raw-device-accessor]
	bool RawDeviceStream::LatestForDevice(uint32_t p_DeviceId, RawDeviceData& p_OutData)
	{
		std::lock_guard<std::mutex> t_Lock(g_RawDeviceMutex);
		const auto t_Found = g_RawDeviceData.find(p_DeviceId);
		if (t_Found == g_RawDeviceData.end()) return false;
		p_OutData = t_Found->second;
		return true;
	}
	// --8<-- [end:raw-device-accessor]

	// --- Stream timestamps ---------------------------------------------------

	namespace
	{
		std::mutex g_ErgonomicsMutex;
		std::map<uint32_t, ErgonomicsData> g_ErgonomicsData; // keyed by glove id

		// --8<-- [start:ergonomics-callback]
		void OnErgonomicsStreamCallback(const ErgonomicsStream* const p_Stream)
		{
			FeedTimestamp(p_Stream->publishTime);
			for (uint32_t i = 0; i < p_Stream->dataCount; ++i)
			{
				if (p_Stream->data[i].isUserID) continue;
				std::lock_guard<std::mutex> t_Lock(g_ErgonomicsMutex);
				g_ErgonomicsData[p_Stream->data[i].id] = p_Stream->data[i];
			}
		}
		// --8<-- [end:ergonomics-callback]
	}

	// --8<-- [start:ergonomics-accessor]
	bool Ergonomics::LatestForGlove(uint32_t p_GloveId, ErgonomicsData& p_OutData)
	{
		std::lock_guard<std::mutex> t_Lock(g_ErgonomicsMutex);
		const auto t_Found = g_ErgonomicsData.find(p_GloveId);
		if (t_Found == g_ErgonomicsData.end()) return false;
		p_OutData = t_Found->second;
		return true;
	}
	// --8<-- [end:ergonomics-accessor]

	SdkResult StreamTime::Register()
	{
		return CoreSdk_RegisterCallbackForErgonomicsStream(*OnErgonomicsStreamCallback);
	}

	bool StreamTime::Latest(ManusTimestamp& p_OutTimestamp)
	{
		std::lock_guard<std::mutex> t_Lock(g_TimestampMutex);
		p_OutTimestamp = g_LatestTimestamp;
		return g_HasTimestamp;
	}
}
