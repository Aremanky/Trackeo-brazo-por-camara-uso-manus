#include "sdk/Connection.hpp"

#include "sdk/Streams.hpp"

#include "ManusSDK.h"

#include <cstring>
#include <mutex>

namespace manus
{
	namespace
	{
		std::mutex g_Mutex;
		ConnectionMode g_Mode = ConnectionMode::Remote;
		bool g_Initialized = false;
		Connection::Info g_Info;
		std::function<void()> g_OnChanged;

		void NotifyChanged()
		{
			std::function<void()> t_OnChanged;
			{
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				t_OnChanged = g_OnChanged;
			}
			if (t_OnChanged) t_OnChanged();
		}

		// --8<-- [start:on-connected]
		void OnConnectedCallback(const ManusHost* const p_Host)
		{
			// Optional, but worth showing: an SDK/Core version mismatch is a
			// common cause of confusing behavior.
			ManusVersion t_SdkVersion{}, t_CoreVersion{};
			bool t_IsCompatible = false;
			const bool t_HaveVersions = CoreSdk_GetVersionsAndCheckCompatibility(
				&t_SdkVersion, &t_CoreVersion, &t_IsCompatible) == SDKReturnCode_Success;

			uint32_t t_SessionId = 0;
			CoreSdk_GetSessionId(&t_SessionId);

			{
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				g_Info.connected = true;
				g_Info.hostName.assign(p_Host->hostName,
					strnlen(p_Host->hostName, MAX_NUM_CHARS_IN_HOST_NAME));
				g_Info.sdkVersion = t_HaveVersions ? t_SdkVersion.versionInfo : "";
				g_Info.coreVersion = t_HaveVersions ? t_CoreVersion.versionInfo : "";
				g_Info.versionsCompatible = t_IsCompatible;
				g_Info.sessionId = t_SessionId;
			}

			Logs::Push("Connected to MANUS Core.");
			if (t_HaveVersions && !t_IsCompatible)
				Logs::Push("WARNING: SDK and Core versions are not compatible.");
			NotifyChanged();
		}
		// --8<-- [end:on-connected]

		void OnDisconnectedCallback(const ManusHost* const /*p_Host*/)
		{
			{
				std::lock_guard<std::mutex> t_Lock(g_Mutex);
				g_Info.connected = false;
			}
			Logs::Push("Disconnected from MANUS Core.");
			NotifyChanged();
		}
	}

	// --8<-- [start:initialize]
	SdkResult Connection::Initialize(ConnectionMode p_Mode)
	{
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_Mode = p_Mode;
		}

		// Integrated runs Core inside this process; the other modes talk to a
		// separately running MANUS Core.
		SDKReturnCode t_Result = p_Mode == ConnectionMode::Integrated
			? CoreSdk_InitializeIntegrated()
			: CoreSdk_InitializeCore();
		if (t_Result != SDKReturnCode_Success) return t_Result;
		g_Initialized = true;

		t_Result = CoreSdk_RegisterCallbackForOnConnect(*OnConnectedCallback);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		t_Result = CoreSdk_RegisterCallbackForOnDisconnect(*OnDisconnectedCallback);
		if (t_Result != SDKReturnCode_Success) return t_Result;

		// --8<-- [start:coordinate-system]
		// Without a coordinate system the SDK refuses to connect to any host.
		// This client uses: z-up, x-from-viewer, right-handed, meter scale.
		// (Unity, Unreal etc. each use their own; set what matches your app.)
		CoordinateSystemVUH t_VUH;
		CoordinateSystemVUH_Init(&t_VUH);
		t_VUH.handedness = Side_Right;
		t_VUH.up = AxisPolarity_PositiveZ;
		t_VUH.view = AxisView_XFromViewer;
		t_VUH.unitScale = 1.0f;
		return CoreSdk_InitializeCoordinateSystemWithVUH(t_VUH, true);
		// --8<-- [end:coordinate-system]
	}
	// --8<-- [end:initialize]

	// --8<-- [start:scan-for-hosts]
	SdkResult Connection::ScanForHosts(std::vector<ManusHost>& p_OutHosts, uint32_t p_WaitSeconds)
	{
		p_OutHosts.clear();

		bool t_LoopbackOnly;
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			t_LoopbackOnly = g_Mode == ConnectionMode::Local;
		}

		// Blocks while hosts get a chance to reply to the search.
		SDKReturnCode t_Result = CoreSdk_LookForHosts(p_WaitSeconds, t_LoopbackOnly);
		if (t_Result != SDKReturnCode_Success) return t_Result;

		uint32_t t_HostCount = 0;
		t_Result = CoreSdk_GetNumberOfAvailableHostsFound(&t_HostCount);
		if (t_Result != SDKReturnCode_Success) return t_Result;
		if (t_HostCount == 0) return SDKReturnCode_Success;

		p_OutHosts.resize(t_HostCount);
		t_Result = CoreSdk_GetAvailableHostsFound(p_OutHosts.data(), t_HostCount);
		if (t_Result != SDKReturnCode_Success) p_OutHosts.clear();
		return t_Result;
	}
	// --8<-- [end:scan-for-hosts]

	// --8<-- [start:connect]
	SdkResult Connection::Connect(const ManusHost& p_Host)
	{
		return CoreSdk_ConnectToHost(p_Host);
	}

	SdkResult Connection::ConnectIntegrated()
	{
		// The in-process Core is addressed with an empty host struct.
		ManusHost t_Empty;
		ManusHost_Init(&t_Empty);
		return CoreSdk_ConnectToHost(t_Empty);
	}
	// --8<-- [end:connect]

	bool Connection::IsConnected()
	{
		bool t_Connected = false;
		if (CoreSdk_GetIsConnectedToCore(&t_Connected) != SDKReturnCode_Success) return false;
		return t_Connected;
	}

	ConnectionMode Connection::Mode()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_Mode;
	}

	Connection::Info Connection::CurrentInfo()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		return g_Info;
	}

	void Connection::SetOnChanged(std::function<void()> p_OnChanged)
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		g_OnChanged = std::move(p_OnChanged);
	}

	void Connection::Shutdown()
	{
		if (!g_Initialized) return;
		g_Initialized = false;
		CoreSdk_ShutDown();
	}
}
