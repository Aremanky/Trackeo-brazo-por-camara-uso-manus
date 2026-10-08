// SDKClient sdk/ module - SDK lifetime and the connection to MANUS Core.
//
// The three connection modes:
//   Integrated - MANUS Core runs inside this process; no separate Core needed.
//   Local      - connect to a MANUS Core running on this machine.
//   Remote     - search the network for MANUS Core hosts and pick one.
#pragma once

#include "sdk/ErrorCodes.hpp"

#include "ManusSDKTypes.h"

#include <functional>
#include <string>
#include <vector>

namespace manus
{
	enum class ConnectionMode { Integrated, Local, Remote };

	namespace Connection
	{
		struct Info
		{
			bool connected = false;
			std::string hostName;    // empty in Integrated mode
			std::string sdkVersion;
			std::string coreVersion;
			bool versionsCompatible = false;
			uint32_t sessionId = 0;
		};

		/// @brief Initializes the SDK for the given mode, registers the
		/// connect/disconnect callbacks and sets the coordinate system (the SDK
		/// refuses to connect without one). Call exactly once, before anything else.
		SdkResult Initialize(ConnectionMode p_Mode);

		/// @brief Scans for MANUS Core hosts; blocks for ~p_WaitSeconds.
		/// In Local mode this scans loopback only - that is how a Core running
		/// on THIS machine is found; the network broadcast scan can miss it.
		SdkResult ScanForHosts(std::vector<ManusHost>& p_OutHosts, uint32_t p_WaitSeconds = 2);

		/// @brief Connects to a host found by ScanForHosts (Local/Remote mode).
		SdkResult Connect(const ManusHost& p_Host);

		/// @brief Connects to the in-process Core (Integrated mode).
		SdkResult ConnectIntegrated();

		/// @brief Live connection state, straight from the SDK.
		bool IsConnected();

		/// @brief The mode passed to Initialize.
		ConnectionMode Mode();

		/// @brief Versions, session id and host of the current connection.
		Info CurrentInfo();

		/// @brief Invoked (from SDK threads) on connect and disconnect.
		void SetOnChanged(std::function<void()> p_OnChanged);

		/// @brief Shuts the SDK down; safe to call when never initialized.
		void Shutdown();
	}
}
