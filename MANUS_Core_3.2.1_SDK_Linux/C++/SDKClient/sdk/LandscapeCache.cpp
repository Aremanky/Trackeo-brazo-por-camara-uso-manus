#include "sdk/LandscapeCache.hpp"

#include "ManusSDK.h"

#include <algorithm>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		Landscape g_Landscape{};
		bool g_HasLandscape = false;
		std::vector<GestureLandscapeData> g_Gestures;
		std::function<void()> g_OnChanged;

		// --8<-- [start:landscape-callback]
		void OnLandscapeCallback(const Landscape* const p_Landscape)
		{
			// The gesture names live outside the landscape struct and must be
			// fetched separately; the count comes from the landscape itself.
			std::vector<GestureLandscapeData> t_Gestures(p_Landscape->gestureCount);
			if (p_Landscape->gestureCount > 0)
				CoreSdk_GetGestureLandscapeData(t_Gestures.data(), (uint32_t)t_Gestures.size());

			std::function<void()> t_OnChanged;
			{
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				g_Landscape = *p_Landscape;
				g_Gestures = std::move(t_Gestures);
				g_HasLandscape = true;
				t_OnChanged = g_OnChanged;
			}
			if (t_OnChanged) t_OnChanged();
		}
		// --8<-- [end:landscape-callback]
	}

	SdkResult LandscapeCache::Register()
	{
		return CoreSdk_RegisterCallbackForLandscapeStream(*OnLandscapeCallback);
	}

	bool LandscapeCache::HasLandscape()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_HasLandscape;
	}

	Landscape LandscapeCache::Snapshot()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_Landscape;
	}

	std::vector<GloveLandscapeData> LandscapeCache::GlovesSortedById()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		std::vector<GloveLandscapeData> t_Gloves(
			g_Landscape.gloveDevices.gloves,
			g_Landscape.gloveDevices.gloves + g_Landscape.gloveDevices.gloveCount);
		std::sort(t_Gloves.begin(), t_Gloves.end(),
			[](const GloveLandscapeData& a, const GloveLandscapeData& b) { return a.id < b.id; });
		return t_Gloves;
	}

	std::vector<DongleLandscapeData> LandscapeCache::DonglesSortedById()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		std::vector<DongleLandscapeData> t_Dongles(
			g_Landscape.gloveDevices.dongles,
			g_Landscape.gloveDevices.dongles + g_Landscape.gloveDevices.dongleCount);
		std::sort(t_Dongles.begin(), t_Dongles.end(),
			[](const DongleLandscapeData& a, const DongleLandscapeData& b) { return a.id < b.id; });
		return t_Dongles;
	}

	std::vector<GestureLandscapeData> LandscapeCache::Gestures()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_Gestures;
	}

	void LandscapeCache::SetOnChanged(std::function<void()> p_OnChanged)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_OnChanged = std::move(p_OnChanged);
	}
}
