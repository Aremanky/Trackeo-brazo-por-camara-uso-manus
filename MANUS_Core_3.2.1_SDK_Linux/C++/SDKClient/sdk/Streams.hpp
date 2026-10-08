// SDKClient sdk/ module - data streams coming from MANUS Core.
// Rule: SDK callbacks only copy data into buffers here; UI code only reads.
// Buffers are keyed by device id - never "the first glove".
//
// Wired so far: the log stream and the gesture stream. The remaining data
// streams (ergonomics, raw device data, skeletons, trackers) are added
// together with their screens.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace manus
{
	namespace Logs
	{
		/// @brief Registers the SDK's OnLog callback. Call once, after SDK initialization.
		SdkResult Register();

		/// @brief Adds a client-side message to the same buffer (status updates etc.).
		void Push(const std::string& p_Line);

		/// @brief The most recent p_Count lines, oldest first.
		std::vector<std::string> Tail(size_t p_Count);

		/// @brief Invoked (from any thread) whenever a line is added.
		/// The UI uses this to request a redraw.
		void SetOnChanged(std::function<void()> p_OnChanged);
	}

	namespace GestureStream
	{
		struct GloveGestures
		{
			uint32_t totalCount = 0;
			std::vector<GestureProbability> probabilities; // id + percent (0.0-1.0)
		};

		/// @brief Registers the SDK's gesture-stream callback. Call once, after
		/// SDK initialization. Gesture data is only sent when a glove's data
		/// changes, so a still glove produces no updates.
		SdkResult Register();

		/// @brief Latest gesture confidences for a glove; false if none were
		/// received yet. Gesture id -> name mapping comes from
		/// LandscapeCache::Gestures().
		bool LatestForGlove(uint32_t p_GloveId, GloveGestures& p_OutGestures);
	}

	namespace RawDeviceStream
	{
		/// @brief Registers the raw-device-data stream callback. Call once,
		/// after SDK initialization. Sensor order: thumb, index, middle, ring,
		/// pinky.
		SdkResult Register();

		/// @brief The most recent raw sensor data of a device; false if none yet.
		bool LatestForDevice(uint32_t p_DeviceId, RawDeviceData& p_OutData);
	}

	namespace Ergonomics
	{
		/// @brief Latest joint angles of a glove (degrees, indexed by
		/// ErgonomicsDataType); false if none were received yet. The stream is
		/// registered by StreamTime::Register.
		bool LatestForGlove(uint32_t p_GloveId, ErgonomicsData& p_OutData);
	}

	namespace StreamTime
	{
		/// @brief Registers the ergonomics-stream callback, which feeds both
		/// the Ergonomics buffer and the stream publish timestamp (it flows
		/// whenever a glove is connected). The other stream callbacks in this
		/// module feed the same timestamp. Call once, after SDK initialization.
		SdkResult Register();

		/// @brief The publish timestamp of the most recent stream data; false
		/// while no stream data has been received. When Core has an active
		/// timecode signal this timestamp encodes timecode - decode it with
		/// Timecode::TimecodeString.
		bool Latest(ManusTimestamp& p_OutTimestamp);
	}
}
