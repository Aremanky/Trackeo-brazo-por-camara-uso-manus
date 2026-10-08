"""
SDKClient Example - Python version
Interactive menu-based client demonstrating various Manus SDK features
Similar to the C++ SDKClient example
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import threading
import select
import sys
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import IntEnum

# Unix-specific imports for terminal control
if os.name != 'nt':
    import tty
    import termios

# Import CFFI directly and minimal wrapper for callbacks
from manus_sdk import lib, ffi, ManusSDK
from manus_sdk.generated._enums import *


class ClientState(IntEnum):
    """Current state of the client"""
    Starting = 0
    LookingForHosts = 1
    NoHostsFound = 2
    PickingHost = 3
    ConnectingToCore = 4
    DisplayingData = 5
    Disconnected = 6


class ConnectionType(IntEnum):
    """Type of connection to Core"""
    Invalid = 0
    Integrated = 1
    Local = 2
    Remote = 3


@dataclass
class ClientSkeleton:
    """Container for skeleton data"""
    info: any  # SkeletonInfo CFFI cdata
    nodes: List[any]  # List of SkeletonNode CFFI cdata


class SDKClient:
    """Interactive SDK Client with menu system"""
    
    def __init__(self):
        # State
        self.state = ClientState.Starting
        self.connection_type = ConnectionType.Invalid
        self.running = True
        
        # SDK wrapper for callbacks
        self.sdk_wrapper = ManusSDK()
        
        # Data storage
        self.hosts = []
        self.num_hosts = 0
        self.selected_host_index = -1
        
        # Skeleton data
        self.skeletons: List[ClientSkeleton] = []
        self.next_skeletons = None
        self.skeleton_mutex = threading.Lock()
        
        # Landscape data
        self.landscape = None
        self.next_landscape = None
        self.landscape_mutex = threading.Lock()
        
        # Ergonomics data - store by glove ID
        self.ergonomics_data = {}  # {glove_id: ergonomics_data}
        self.next_ergonomics_data = None
        self.ergonomics_mutex = threading.Lock()
        
        # Raw skeleton data - store by glove ID (callbacks return one glove at a time)
        self.raw_skeleton_data = {}  # {glove_id: skeleton_data}
        self.next_raw_skeleton_data = None
        self.raw_skeleton_data_mutex = threading.Lock()
        
        # Raw device data - store sensor data from devices
        self.raw_device_data = {}  # {device_id: device_data}
        self.next_raw_device_data = None
        self.raw_device_data_mutex = threading.Lock()

        # Tracker data - live stream from TrackerStream callback, keyed by tracker ID string
        self.tracker_data = {}       # {tracker_id_str: dict of position/rotation/type/quality/user_id}
        self.next_tracker_data = None
        self.tracker_mutex = threading.Lock()
        # Tracker menu interaction state
        self.show_trackers_per_user = False
        self.test_tracker_enabled = False

        # System messages
        self.system_messages = []
        self.system_mutex = threading.Lock()
        
        # Log messages for display
        self.log_messages = []
        self.log_mutex = threading.Lock()
        
        # Throttle data callback logging - only log every N callbacks
        self.callback_counter = {
            'raw_skeleton': 0,
            'skeleton': 0,
            'ergonomics': 0,
            'landscape': 0,
            'tracker': 0,
        }
        self.log_every_n_callbacks = 30  # Log every 30th callback (~1 per second at 30fps)
        
        # Current menu state
        self.current_menu = None
        
        # Frame rate limiting for display updates
        self.last_display_time = 0
        self.min_display_interval = 0.1  # 10 fps (100ms between redraws)
        
        # Calibration state
        self.calibrate_left_hand = True
        self.calibration_step = 0
        self.calibration_in_progress = False
        self.calibration_message = ""
        self.number_of_calibration_steps = 0
        self.calibration_glove_id = 0
        self.calibration_step_data = None  # Dictionary with title, description, time
        self.calibration_started = False  # Flag to track if calibration has been started
        
        # Skeleton management
        self.loaded_skeletons = []  # List of loaded skeleton IDs
        self.temporary_skeletons = []  # List of temporary skeleton indices
        self.skeleton_metadata = {}  # Maps skeleton_id -> {node_id -> chain_type}
        
        # Haptics state - track active fingers for hold-to-vibrate
        self.haptic_left_powers = [0.0] * 5   # Thumb, Index, Middle, Ring, Pinky
        self.haptic_right_powers = [0.0] * 5  # Thumb, Index, Middle, Ring, Pinky
        self.haptic_last_key_time = 0
        self.haptic_timeout = 0.15  # Stop haptics 150ms after last key press

        # Tracking settings menu state
        self._selected_tracker_system_index = -1
        self._selected_tracker_system_setting_index = -1
        
        # Terminal settings for Unix
        self.old_terminal_settings = None
        if os.name != 'nt':
            try:
                self.old_terminal_settings = termios.tcgetattr(sys.stdin)
                # Set terminal to raw mode for non-blocking input
                tty.setcbreak(sys.stdin.fileno())
            except:
                pass
    
    def log(self, level: str, message: str):
        """Add a log message to the display"""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {level}: {message}"
        
        with self.log_mutex:
            self.log_messages.append(log_line)
            # Keep only last 5 messages
            if len(self.log_messages) > 5:
                self.log_messages.pop(0)
    
    def display_logs(self):
        """Display log messages at the bottom of the screen"""
        print("\n" + "="*60)
        print("LOGS:")
        with self.log_mutex:
            if self.log_messages:
                for log_line in self.log_messages:
                    print(log_line)
            else:
                print("(No log messages)")
        
    def initialize(self):
        """Initialize the SDK"""
        print("="*60)
        print("Manus SDK Client (Python)")
        print("="*60)
        print()
        
        # Determine connection type
        self.connection_type = self.get_connection_type()
        
        # Initialize SDK based on connection type
        if self.connection_type == ConnectionType.Integrated:
            self.log("INFO", "Initializing SDK in Integrated mode...")
            result = lib.CoreSdk_InitializeIntegrated()
        else:
            self.log("INFO", f"Initializing SDK in {self.connection_type.name} mode...")
            result = lib.CoreSdk_InitializeCore()
        
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to initialize SDK: {SDKReturnCode(result).name}")
            print(f"Failed to initialize: {result}")
            return False
        
        print(f"SDK initialized successfully (Type: {self.connection_type.name})")
        self.log("INFO", f"SDK initialized ({self.connection_type.name})")
        
        # Set up coordinate system
        coord_system = ffi.new("CoordinateSystemVUH*")
        coord_system.view = AxisView.XFromViewer
        coord_system.up = AxisPolarity.PositiveZ
        coord_system.handedness = Side.Right
        coord_system.unitScale = 1.0
        
        result = lib.CoreSdk_InitializeCoordinateSystemWithVUH(coord_system[0], True)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to set coordinate system: {result.name}")
            print(f"Failed to set coordinate system: {result}")
            return False
        
        self.log("INFO", "Coordinate system configured")
        
        # Register callbacks
        self.register_all_callbacks()
        self.log("INFO", "All callbacks registered")
        
        # Change state - even Integrated mode needs to go through connection logic
        print("\n✓ SDK initialized successfully")
        if self.connection_type == ConnectionType.Integrated:
            print("  Mode: Integrated (standalone)")
            self.state = ClientState.LookingForHosts  # Still need to "connect" even in integrated mode
        else:
            self.state = ClientState.LookingForHosts
        
        return True
    
    def get_connection_type(self):
        """Ask user for connection type"""
        print("Select connection type:")
        print("  [1] Integrated Mode (no Core needed)")
        print("  [2] Local Mode (Core on localhost)")
        print("  [3] Remote Mode (search network for Core)")
        print()
        
        while True:
            try:
                choice = input("Enter choice [1-3]: ").strip()
                if choice == '1':
                    return ConnectionType.Integrated
                elif choice == '2':
                    return ConnectionType.Local
                elif choice == '3':
                    return ConnectionType.Remote
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
            except KeyboardInterrupt:
                print("\nCancelled.")
                sys.exit(0)
    
    def register_all_callbacks(self):
        """Register all SDK callbacks"""
        result = self.sdk_wrapper.register_log_callback(self.on_log_callback)
        print(f"Log callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_raw_skeleton_callback(self.on_raw_skeleton_callback)
        print(f"Raw skeleton callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_skeleton_callback(self.on_skeleton_callback)
        print(f"Skeleton callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_landscape_callback(self.on_landscape_callback)
        print(f"Landscape callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_ergonomics_callback(self.on_ergonomics_callback)
        print(f"Ergonomics callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_raw_device_data_callback(self.on_raw_device_data_callback)
        print(f"Raw device data callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        result = self.sdk_wrapper.register_system_callback(self.on_system_callback)
        print(f"System callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")

        result = self.sdk_wrapper.register_tracker_callback(self.on_tracker_callback)
        print(f"Tracker callback registered: {SDKReturnCode(result).name if result == 0 else f'Error {result}'}")
        
        print("All callbacks registered")
    
    def on_log_callback(self, severity, log_message, length):
        """Callback for SDK logging"""
        try:
            # Convert C string to Python string
            log_str = ffi.string(log_message, length).decode('utf-8')
            
            # Map severity to level name
            severity_map = {
                0: "DEBUG",  # LogSeverity_Debug
                1: "INFO",   # LogSeverity_Info
                2: "WARN",   # LogSeverity_Warn
                3: "ERROR"   # LogSeverity_Error
            }
            level = severity_map.get(severity, "UNKNOWN")
            
            # Add to log display
            self.log(f"SDK-{level}", log_str)
        except Exception as e:
            print(f"Error in log callback: {e}")
    
    # --8<-- [start:raw-skeleton-callback]
    def on_raw_skeleton_callback(self, stream_info):
        """Callback for raw skeleton data - caches by glove ID since callbacks return one glove at a time"""
        try:
            skeletons_count = stream_info.skeletonsCount
            next_data = {}

            for i in range(skeletons_count):
                # Get skeleton info (metadata such as glove ID and node count)
                info = ffi.new("RawSkeletonInfo*")
                result = lib.CoreSdk_GetRawSkeletonInfo(i, info)
                if result != SDKReturnCode.Success:
                    continue

                # Get the skeleton nodes (transforms) for this glove
                nodes_array = ffi.new("SkeletonNode[]", info.nodesCount)
                result = lib.CoreSdk_GetRawSkeletonData(i, nodes_array, info.nodesCount)
                if result != SDKReturnCode.Success:
                    continue

                # Get node info array for this glove (hierarchy and chain information)
                node_info_array = ffi.new("NodeInfo[]", info.nodesCount)
                result = lib.CoreSdk_GetRawSkeletonNodeInfoArray(info.gloveId, node_info_array, info.nodesCount)

                # Make deep copies of the data to avoid CFFI memory reuse issues
                skeleton_data = {
                    'glove_id': info.gloveId,
                    'nodes_count': info.nodesCount,
                    'publish_time': info.publishTime,
                    'nodes': []
                }

                for j in range(info.nodesCount):
                    node = nodes_array[j]
                    node_data = {
                        'id': node.id,
                        'position': {
                            'x': node.transform.position.x,
                            'y': node.transform.position.y,
                            'z': node.transform.position.z
                        },
                        'rotation': {
                            'w': node.transform.rotation.w,
                            'x': node.transform.rotation.x,
                            'y': node.transform.rotation.y,
                            'z': node.transform.rotation.z
                        },
                        'scale': {
                            'x': node.transform.scale.x,
                            'y': node.transform.scale.y,
                            'z': node.transform.scale.z
                        }
                    }

                    # Add node info if available
                    if result == SDKReturnCode.Success:
                        node_info = node_info_array[j]
                        node_data['node_info'] = {
                            'node_id': node_info.nodeId,
                            'parent_id': node_info.parentId,
                            'chain_type': node_info.chainType,
                            'side': node_info.side,
                            'finger_joint_type': node_info.fingerJointType
                        }

                    skeleton_data['nodes'].append(node_data)

                next_data[info.gloveId] = skeleton_data

            # Hand the data over to the main thread instead of processing it here,
            # blocking the callback thread would delay incoming data
            with self.raw_skeleton_data_mutex:
                self.next_raw_skeleton_data = next_data

        except Exception as e:
            self.log("ERROR", f"Raw skeleton callback error: {e}")
            print(f"Error in raw skeleton callback: {e}")
    # --8<-- [end:raw-skeleton-callback]
    
    # --8<-- [start:skeleton-callback]
    def on_skeleton_callback(self, stream_info):
        """Callback for processed skeleton data"""
        try:
            skeletons_count = stream_info.skeletonsCount
            new_skeletons = []
            
            for i in range(skeletons_count):
                # Get skeleton info (skeleton ID and node count)
                info = ffi.new("SkeletonInfo*")
                result = lib.CoreSdk_GetSkeletonInfo(i, info)
                if result != SDKReturnCode.Success:
                    continue
                
                # Get the skeleton nodes with their animation transforms
                nodes_array = ffi.new("SkeletonNode[]", info.nodesCount)
                result = lib.CoreSdk_GetSkeletonData(i, nodes_array, info.nodesCount)
                if result != SDKReturnCode.Success:
                    continue
                
                # Make deep copies of the data, the CFFI buffers are reused by the SDK
                skeleton_data = {
                    'skeleton_id': info.id,
                    'nodes_count': info.nodesCount,
                    'publish_time': info.publishTime,
                    'nodes': []
                }
                
                for j in range(info.nodesCount):
                    node = nodes_array[j]
                    node_data = {
                        'id': node.id,
                        'position': {
                            'x': node.transform.position.x,
                            'y': node.transform.position.y,
                            'z': node.transform.position.z
                        },
                        'rotation': {
                            'w': node.transform.rotation.w,
                            'x': node.transform.rotation.x,
                            'y': node.transform.rotation.y,
                            'z': node.transform.rotation.z
                        },
                        'scale': {
                            'x': node.transform.scale.x,
                            'y': node.transform.scale.y,
                            'z': node.transform.scale.z
                        }
                    }
                    
                    # Add node_info from the skeleton setup metadata if available
                    if info.id in self.skeleton_metadata and node.id in self.skeleton_metadata[info.id]:
                        chain_info = self.skeleton_metadata[info.id][node.id]
                        node_data['node_info'] = chain_info
                    
                    skeleton_data['nodes'].append(node_data)
                
                new_skeletons.append(skeleton_data)
            
            # Hand the data over to the main thread instead of processing it here
            with self.skeleton_mutex:
                self.next_skeletons = new_skeletons
        except Exception as e:
            self.log("ERROR", f"Skeleton callback error: {e}")
            print(f"Error in skeleton callback: {e}")
    # --8<-- [end:skeleton-callback]
    
    # --8<-- [start:landscape-callback]
    def on_landscape_callback(self, landscape):
        """Callback for landscape data"""
        try:
            # Quick validation before storing - check if counts are reasonable
            glove_count = landscape.gloveDevices.gloveCount
            dongle_count = landscape.gloveDevices.dongleCount
            user_count = landscape.users.userCount
            skeleton_count = landscape.skeletons.skeletonCount
            tracker_count = landscape.trackers.trackerCount
            
            # Only process if counts are valid
            if not (0 <= glove_count <= 32 and 
                    0 <= dongle_count <= 32 and 
                    0 <= user_count <= 10 and 
                    0 <= skeleton_count <= 32 and 
                    0 <= tracker_count <= 32):
                return  # Skip invalid data
    # --8<-- [end:landscape-callback]
            
            # Make a deep copy of landscape data
            landscape_copy = {
                'glove_count': glove_count,
                'dongle_count': dongle_count,
                'user_count': user_count,
                'skeleton_count': skeleton_count,
                'tracker_count': tracker_count,
                'dongles': [],
                'gloves': [],
                'users': [],
                'skeletons': [],
                'trackers': [],
                'settings': {}
            }
            
            # Copy dongles
            for i in range(dongle_count):
                try:
                    d = landscape.gloveDevices.dongles[i]
                    landscape_copy['dongles'].append({
                        'id': d.id,
                        'channel': d.channel,
                        'leftGloveID': d.leftGloveID,
                        'rightGloveID': d.rightGloveID,
                        'firmwareVersion': {
                            'major': d.firmwareVersion.major,
                            'minor': d.firmwareVersion.minor,
                            'patch': d.firmwareVersion.patch
                        }
                    })
                except Exception:
                    pass
            
            # Copy gloves
            for i in range(glove_count):
                try:
                    g = landscape.gloveDevices.gloves[i]
                    landscape_copy['gloves'].append({
                        'id': g.id,
                        'dongleID': g.dongleID,
                        'side': g.side,
                        'pairedState': g.pairedState,
                        'batteryPercentage': g.batteryPercentage,
                        'transmissionStrength': g.transmissionStrength,
                        'isHaptics': g.isHaptics,
                        'firmwareVersion': {
                            'major': g.firmwareVersion.major,
                            'minor': g.firmwareVersion.minor,
                            'patch': g.firmwareVersion.patch
                        }
                    })
                except Exception:
                    pass
            
            # Copy users
            for i in range(user_count):
                try:
                    u = landscape.users.users[i]
                    user_name = ffi.string(u.name).decode('utf-8') if u.name else ""
                    landscape_copy['users'].append({
                        'id': u.id,
                        'name': user_name,
                        'dongleID': u.dongleID,
                        'leftGloveID': u.leftGloveID,
                        'rightGloveID': u.rightGloveID,
                        'profileType': u.profile.profileType
                    })
                except Exception:
                    pass
            
            # Copy skeletons
            for i in range(skeleton_count):
                try:
                    s = landscape.skeletons.skeletons[i]
                    session = ffi.string(s.session).decode('utf-8') if s.session else ""
                    root_bone = ffi.string(s.rootBoneName).decode('utf-8') if s.rootBoneName else ""
                    landscape_copy['skeletons'].append({
                        'id': s.id,
                        'userId': s.userId,
                        'type': s.type,
                        'session': session,
                        'rootBoneName': root_bone,
                        'scaled': s.scaled
                    })
                except Exception:
                    pass
            
            # Copy trackers
            for i in range(tracker_count):
                try:
                    t = landscape.trackers.trackers[i]
                    tracker_id = ffi.string(t.id).decode('utf-8') if t.id else ""
                    manufacturer = ffi.string(t.manufacturer).decode('utf-8') if t.manufacturer else ""
                    product = ffi.string(t.productName).decode('utf-8') if t.productName else ""
                    landscape_copy['trackers'].append({
                        'id': tracker_id,
                        'manufacturer': manufacturer,
                        'productName': product,
                        'user': t.user,
                        'isHMD': t.isHMD
                    })
                except Exception:
                    pass
            
            # Copy settings
            try:
                s = landscape.settings
                landscape_copy['settings'] = {
                    'manusCoreVersion': {
                        'major': s.manusCoreVersion.major,
                        'minor': s.manusCoreVersion.minor,
                        'patch': s.manusCoreVersion.patch
                    },
                    'playbackMode': s.playbackMode,
                    'recordingMode': s.recordingMode,
                    'isNetDevice': s.isNetDevice,
                    'isConnectedAsNetDevice': s.isConnectedAsNetDevice,
                    'license': {
                        'maxGlovePairs': s.license.maxGlovePairs,
                        'recording': s.license.recording,
                        'exporting': s.license.exporting,
                        'advancedExporting': s.license.advancedExporting,
                        'unitySession': s.license.unitySession,
                        'unrealSession': s.license.unrealSession,
                        'openXRSession': s.license.openXRSession,
                        'sdk': s.license.sdk,
                        'raw': s.license.raw,
                        'mobuSession': s.license.mobuSession,
                        'xsensSession': s.license.xsensSession,
                        'optitrackSession': s.license.optitrackSession,
                        'qualisysSession': s.license.qualisysSession,
                        'viconSession': s.license.viconSession,
                        'nokovSession': s.license.nokovSession,
                        'icidoSession': s.license.icidoSession,
                        'siemensSession': s.license.siemensSession,
                        'vredSession': s.license.vredSession,
                        'integrated': s.license.integrated,
                        'cortexSession': s.license.cortexSession,
                        'fzMotionSession': s.license.fzMotionSession,
                        'worldVizSession': s.license.worldVizSession,
                        'noraxonSession': s.license.noraxonSession,
                        'noitomSession': s.license.noitomSession
                    }
                }
            except Exception:
                pass
            
            with self.landscape_mutex:
                self.next_landscape = landscape_copy
                
        except Exception as e:
            self.log("ERROR", f"Landscape callback error: {e}")
            print(f"Error in landscape callback: {e}")
    
    # --8<-- [start:ergonomics-callback]
    def on_ergonomics_callback(self, ergonomics_stream):
        """Callback for ergonomics data"""
        try:
            # Update cached ergonomics data by glove ID
            count = ergonomics_stream.dataCount
            next_ergonomics_data = {}

            for i in range(count):
                data = ergonomics_stream.data[i]
                glove_id = data.id

                # Make a deep copy of the data since CFFI structures may be reused
                data_copy = {
                    'id': data.id,
                    'isUserID': data.isUserID,
                    'data': list(data.data)  # Convert CFFI array to Python list
                }

                next_ergonomics_data[glove_id] = data_copy

            # Hand the data over to the main thread instead of processing it here
            with self.ergonomics_mutex:
                self.next_ergonomics_data = next_ergonomics_data
        except Exception as e:
            self.log("ERROR", f"Ergonomics callback error: {e}")
            print(f"Error in ergonomics callback: {e}")
    # --8<-- [end:ergonomics-callback]
    
    # --8<-- [start:raw-device-callback]
    def on_raw_device_data_callback(self, raw_device_info):
        """Callback for raw device sensor data"""
        try:
            raw_device_data_count = raw_device_info.rawDeviceDataCount

            # Track callback invocation count
            self.raw_device_callback_count = getattr(self, 'raw_device_callback_count', 0) + 1
            self.last_raw_device_data_count = raw_device_data_count

            next_raw_device_data = {}
            for i in range(raw_device_data_count):
                raw_device = ffi.new("RawDeviceData*")
                result = lib.CoreSdk_GetRawDeviceData(i, raw_device)
                if result != SDKReturnCode.Success:
                    continue

                device_id = raw_device.id
                sensor_count = raw_device.sensorCount

                # Deep copy the sensor transforms (position, rotation, scale)
                sensors = []
                for sensor_idx in range(sensor_count):
                    sensor_transform = raw_device.sensorData[sensor_idx]
                    sensor_data = {
                        'position': {
                            'x': sensor_transform.position.x,
                            'y': sensor_transform.position.y,
                            'z': sensor_transform.position.z
                        },
                        'rotation': {
                            'w': sensor_transform.rotation.w,
                            'x': sensor_transform.rotation.x,
                            'y': sensor_transform.rotation.y,
                            'z': sensor_transform.rotation.z
                        },
                        'scale': {
                            'x': sensor_transform.scale.x,
                            'y': sensor_transform.scale.y,
                            'z': sensor_transform.scale.z
                        }
                    }
                    sensors.append(sensor_data)

                # Cache device data by device ID
                device_data = {
                    'id': device_id,
                    'sensor_count': sensor_count,
                    'sensors': sensors,
                    'rotation': {
                        'w': raw_device.rotation.w,
                        'x': raw_device.rotation.x,
                        'y': raw_device.rotation.y,
                        'z': raw_device.rotation.z
                    }
                }

                next_raw_device_data[device_id] = device_data

            # Hand the data over to the main thread instead of processing it here
            with self.raw_device_data_mutex:
                self.next_raw_device_data = next_raw_device_data
        except Exception as e:
            self.log("ERROR", f"Raw device data callback error: {e}")
            print(f"Error in raw device data callback: {e}")
    # --8<-- [end:raw-device-callback]
    
    def on_system_callback(self, system_message):
        """Callback for system messages"""
        try:
            msg_type = system_message.type
            msg_str = ffi.string(system_message.infoString).decode('utf-8')
            
            with self.system_mutex:
                self.system_messages.append((msg_type, msg_str))
                # Keep only last 10 messages
                if len(self.system_messages) > 10:
                    self.system_messages.pop(0)
            
            self.log("SYSTEM", msg_str)
        except Exception as e:
            self.log("ERROR", f"System callback error: {e}")
            print(f"Error in system callback: {e}")
    
    def on_tracker_callback(self, stream_info):
        try:
            tracker_count = stream_info.trackerCount
            if tracker_count == 0:
                return

            next_tracker_data = {}
            for i in range(tracker_count):
                data = ffi.new("TrackerData*")
                result = lib.CoreSdk_GetTrackerData(i, data)
                if result != SDKReturnCode.Success:
                    continue
                tracker_id = ffi.string(data.trackerId.id).decode('utf-8', errors='replace')
                next_tracker_data[tracker_id] = {
                    'tracker_type': int(data.trackerType),
                    'user_id': int(data.userId),
                    'is_hmd': bool(data.isHmd),
                    'position': (data.position.x, data.position.y, data.position.z),
                    'rotation': (data.rotation.x, data.rotation.y, data.rotation.z, data.rotation.w),
                    'quality': int(data.quality),
                }

            with self.tracker_mutex:
                self.next_tracker_data = next_tracker_data

            self.callback_counter['tracker'] += 1
        except Exception as e:
            self.log("ERROR", f"Tracker callback error: {e}")

    def get_glove_side(self, glove_id):
        """Get the Side enum value for a glove ID from landscape data"""
        if not self.landscape:
            return None
        
        try:
            # Work with dictionary format
            gloves = self.landscape.get('gloves', [])
            for glove in gloves:
                if glove['id'] == glove_id:
                    return glove['side']  # Returns Side enum (1=Left, 2=Right, etc.)
        except Exception:
            pass
        
        return None
    
    def get_node_name(self, node):
        """Get a friendly name for a skeleton node using NodeInfo"""
        from manus_sdk.generated._enums import ChainType, FingerJointType, Side
        
        # If node has node_info, use it to build a descriptive name
        if 'node_info' in node:
            info = node['node_info']
            chain_type = info['chain_type']
            side = info['side']
            joint_type = info['finger_joint_type']
            
            # Side prefix
            side_prefix = ""
            if side == Side.Left:
                side_prefix = "L_"
            elif side == Side.Right:
                side_prefix = "R_"
            elif side == Side.Center:
                side_prefix = "C_"
            
            # Chain name
            chain_names = {
                ChainType.Hand: "Hand",
                ChainType.FingerThumb: "Thumb",
                ChainType.FingerIndex: "Index",
                ChainType.FingerMiddle: "Middle",
                ChainType.FingerRing: "Ring",
                ChainType.FingerPinky: "Pinky",
                ChainType.Arm: "Arm",
                ChainType.Leg: "Leg",
                ChainType.Neck: "Neck",
                ChainType.Spine: "Spine",
                ChainType.Pelvis: "Pelvis",
                ChainType.Head: "Head",
                ChainType.Shoulder: "Shoulder",
                ChainType.Foot: "Foot",
                ChainType.Toe: "Toe",
            }
            
            # Joint type name
            joint_names = {
                FingerJointType.Metacarpal: "Metacarpal",
                FingerJointType.Proximal: "Proximal",
                FingerJointType.Intermediate: "Intermediate",
                FingerJointType.Distal: "Distal",
                FingerJointType.Tip: "Tip",
            }
            
            chain_name = chain_names.get(chain_type, f"Chain{chain_type}")
            joint_name = joint_names.get(joint_type, f"Joint{joint_type}") if joint_type != FingerJointType.Invalid else ""
            
            if joint_name:
                return f"{side_prefix}{chain_name}_{joint_name}"
            else:
                return f"{side_prefix}{chain_name}"
        
        # Fallback to node ID
        return f"Node_{node['id']}"
    
    def format_skeleton_nodes(self, nodes, show_all=False):
        """Format skeleton nodes for display"""
        lines = []
        
        if not nodes:
            return ["  No nodes available"]
        
        # Show total node count
        lines.append(f"  Total Nodes: {len(nodes)}")
        
        # In detailed view, show all nodes
        if show_all:
            lines.append("  All Nodes:")
            for node in nodes:
                name = self.get_node_name(node)
                pos = node['position']
                lines.append(f"    Node {node['id']:2d} ({name:25s}): ({pos['x']:7.3f}, {pos['y']:7.3f}, {pos['z']:7.3f})")
        
        return lines
    
    def format_ergonomics_data(self, ergo_data, is_left_hand=True):
        """Format ergonomics data for display showing finger joint angles"""
        if not ergo_data:
            return []
        
        lines = []
        try:
            # Ergonomics data indices based on ErgonomicsDataType enum
            # Left hand: indices 0-19, Right hand: indices 20-39
            offset = 0 if is_left_hand else 20
            
            fingers = [
                ("Thumb", 0),
                ("Index", 4),
                ("Middle", 8),
                ("Ring", 12),
                ("Pinky", 16)
            ]
            
            # Handle both dict (copied data) and CFFI struct
            if isinstance(ergo_data, dict):
                data_array = ergo_data['data']
            else:
                data_array = ergo_data.data
            
            for finger_name, base_idx in fingers:
                idx = offset + base_idx
                spread = data_array[idx + 0]      # MCP Spread
                mcp_stretch = data_array[idx + 1] # MCP Stretch (bend)
                pip_stretch = data_array[idx + 2] # PIP Stretch (bend)
                dip_stretch = data_array[idx + 3] # DIP Stretch (bend)
                
                lines.append(f"  {finger_name:6s}: Spread={spread:6.2f}°  MCP={mcp_stretch:6.2f}°  PIP={pip_stretch:6.2f}°  DIP={dip_stretch:6.2f}°")
        except Exception as e:
            lines.append(f"  [Error reading data: {e}]")
        
        return lines
    
    def get_glove_side_name(self, glove_id):
        """Get the side name (Left/Right) for a glove ID from landscape data"""
        if not self.landscape:
            return "Unknown"
        
        try:
            # Work with dictionary format
            gloves = self.landscape.get('gloves', [])
            for glove in gloves:
                if glove['id'] == glove_id:
                    # Side field: 0=Invalid, 1=Left, 2=Right, 3=Center
                    side = glove['side']
                    if side == 1:
                        return "Left"
                    elif side == 2:
                        return "Right"
                    elif side == 3:
                        return "Center"
                    else:
                        return f"Unknown (side={side})"
        except Exception as e:
            return f"Error: {e}"
        
        return "Not Found"
    
    def run(self):
        """Main client loop"""
        print("\nStarting client main loop...")
        print("Press Ctrl+C to exit\n")
        
        try:
            while self.running:
                # State machine
                if self.state == ClientState.LookingForHosts:
                    self.looking_for_hosts()
                elif self.state == ClientState.NoHostsFound:
                    self.no_hosts_found()
                elif self.state == ClientState.PickingHost:
                    self.picking_host()
                elif self.state == ClientState.ConnectingToCore:
                    self.connecting_to_core()
                elif self.state == ClientState.DisplayingData:
                    self.update_before_displaying_data()
                    if self.smart_clear():
                        if self.current_menu is None:
                            self.display_main_menu()
                        else:
                            self.current_menu()
                elif self.state == ClientState.Disconnected:
                    self.disconnected_from_core()

                time.sleep(0.03)  # 30ms update rate
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            self.running = False
    
    def update_before_displaying_data(self):
        with self.skeleton_mutex:
            if self.next_skeletons is not None:
                self.skeletons = self.next_skeletons
                self.next_skeletons = None

        with self.raw_skeleton_data_mutex:
            if self.next_raw_skeleton_data is not None:
                self.raw_skeleton_data.update(self.next_raw_skeleton_data)
                self.next_raw_skeleton_data = None

        with self.raw_device_data_mutex:
            if self.next_raw_device_data is not None:
                self.raw_device_data.update(self.next_raw_device_data)
                self.next_raw_device_data = None

        with self.tracker_mutex:
            if self.next_tracker_data is not None:
                self.tracker_data = self.next_tracker_data
                self.next_tracker_data = None

        with self.ergonomics_mutex:
            if self.next_ergonomics_data is not None:
                self.ergonomics_data.update(self.next_ergonomics_data)
                self.next_ergonomics_data = None

        with self.landscape_mutex:
            if self.next_landscape is not None:
                self.landscape = self.next_landscape
                self.next_landscape = None

    def looking_for_hosts(self):
        """Look for available Manus Core hosts"""
        # Only look for hosts once when entering this state
        if hasattr(self, '_looking_for_hosts_done') and self._looking_for_hosts_done:
            return  # Already processed, waiting for state to change
        
        print("Looking for Manus Core hosts...")
        self.log("INFO", "Looking for Manus Core hosts...")
        
        loopback_only = (self.connection_type == ConnectionType.Local)
        wait_s = 1 if loopback_only else 3

        print(f"Calling CoreSdk_LookForHosts (wait={wait_s}s, loopback_only={loopback_only})...")
        result = lib.CoreSdk_LookForHosts(wait_s, loopback_only)
        print(f"CoreSdk_LookForHosts returned: {result}")
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to look for hosts: {SDKReturnCode(result).name}")
            print(f"Failed to look for hosts: {result}")
            self.state = ClientState.NoHostsFound
            self._looking_for_hosts_done = True
            return
        
        num_hosts = ffi.new("uint32_t*")
        result = lib.CoreSdk_GetNumberOfAvailableHostsFound(num_hosts)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to get host count: {SDKReturnCode(result).name}")
            print(f"Failed to get host count: {result}")
            self.state = ClientState.NoHostsFound
            self._looking_for_hosts_done = True
            return
        
        self.num_hosts = num_hosts[0]
        
        print(f"Number of hosts found: {self.num_hosts}")
        
        if self.num_hosts == 0:
            self.log("WARN", "No hosts found")
            print("No hosts found.")
            self.state = ClientState.NoHostsFound
        else:
            self.log("INFO", f"Found {self.num_hosts} host(s)")
            print(f"Found {self.num_hosts} host(s)")
            
            hosts_array = ffi.new("ManusHost[]", self.num_hosts)
            result = lib.CoreSdk_GetAvailableHostsFound(hosts_array, self.num_hosts)
            if result == SDKReturnCode.Success:
                self.hosts = [hosts_array[i] for i in range(self.num_hosts)]
                
                # In Integrated mode or if only one host, auto-select first host
                if self.connection_type == ConnectionType.Integrated or self.num_hosts == 1:
                    self.selected_host_index = 0
                    self.state = ClientState.ConnectingToCore
                    self._connecting_done = False  # Reset for connection
                else:
                    self.state = ClientState.PickingHost
            else:
                print(f"Failed to get host list: {result}")
                self.state = ClientState.NoHostsFound
        
        self._looking_for_hosts_done = True
    
    def no_hosts_found(self):
        """Handle no hosts found"""
        # Only show the menu once when entering this state
        if not hasattr(self, '_no_hosts_shown') or not self._no_hosts_shown:
            print("\nNo Manus Core hosts found.")
            print("  [R] Retry searching")
            print("  [Q] Quit")
            self._no_hosts_shown = True
        
        # Check for input non-blocking style
        if self.has_input():
            ch = self.get_char()
            if ch == 'R':
                self.state = ClientState.LookingForHosts
                self._no_hosts_shown = False
                self._looking_for_hosts_done = False  # Reset the flag for retry
            elif ch == 'Q':
                self.running = False
    
    def picking_host(self):
        """Let user pick a host to connect to"""
        # Only show the menu once when entering this state
        if not hasattr(self, '_picking_host_shown') or not self._picking_host_shown:
            print("\nAvailable hosts:")
            for i, host in enumerate(self.hosts):
                hostname = ffi.string(host.hostName).decode('utf-8')
                ip = ffi.string(host.ipAddress).decode('utf-8')
                version = host.manusCoreVersion
                print(f"  [{i+1}] {hostname} ({ip}) v{version.major}.{version.minor}.{version.patch}")
            
            print()
            self._picking_host_shown = True
        
        # Check for input non-blocking style
        if self.has_input():
            try:
                ch = self.get_char()
                if ch and ch.isdigit():
                    index = int(ch) - 1
                    if 0 <= index < self.num_hosts:
                        self.selected_host_index = index
                        self.state = ClientState.ConnectingToCore
                        self._picking_host_shown = False
                        self._connecting_done = False  # Reset for connection attempt
                    else:
                        print("Invalid selection")
                        self._picking_host_shown = False
            except (ValueError, AttributeError):
                pass
    
    def connecting_to_core(self):
        """Connect to selected host"""
        # Only connect once when entering this state
        if hasattr(self, '_connecting_done') and self._connecting_done:
            return  # Already processed, waiting for state to change
        
        if self.selected_host_index < 0 or self.selected_host_index >= self.num_hosts:
            print("Invalid host selection")
            self.state = ClientState.LookingForHosts
            self._connecting_done = True
            return
        
        host = self.hosts[self.selected_host_index]
        hostname = ffi.string(host.hostName).decode('utf-8')
        print(f"\nConnecting to {hostname}...")
        
        result = lib.CoreSdk_ConnectToHost(host)
        if result != SDKReturnCode.Success:
            print(f"Failed to connect: {result}")
            self.state = ClientState.PickingHost
            self._picking_host_shown = False  # Reset to show menu again
        else:
            print("Connected successfully!")
            
            # Get version info
            sdk_version = ffi.new("ManusVersion*")
            core_version = ffi.new("ManusVersion*")
            compatible = ffi.new("bool*")
            result = lib.CoreSdk_GetVersionsAndCheckCompatibility(sdk_version, core_version, compatible)
            if result == SDKReturnCode.Success:
                sdk_ver = ffi.string(sdk_version.versionInfo).decode('utf-8')
                core_ver = ffi.string(core_version.versionInfo).decode('utf-8')
                print(f"SDK version: {sdk_ver}")
                print(f"Core version: {core_ver}")
                print(f"Compatible: {compatible[0]}")
            
            self.state = ClientState.DisplayingData
        
        self._connecting_done = True
    
    def disconnected_from_core(self):
        """Handle disconnection from Core"""
        # Only show the menu once when entering this state
        if not hasattr(self, '_disconnected_shown') or not self._disconnected_shown:
            print("\nDisconnected from Manus Core")
            print("  [R] Reconnect")
            print("  [Q] Quit")
            self._disconnected_shown = True
        
        # Check for input non-blocking style
        if self.has_input():
            ch = self.get_char()
            if ch == 'R':
                self.state = ClientState.LookingForHosts
                self._disconnected_shown = False
                self._looking_for_hosts_done = False  # Reset the flag for reconnect
            elif ch == 'Q':
                self.running = False
    
    def display_main_menu(self):
        """Display main menu"""
        print("="*60)
        print("MAIN MENU")
        print("="*60)
        print("  [G] Gloves & Ergonomics Data")
        print("  [S] Skeleton Data")
        print("  [R] Raw Skeleton Data")
        print("  [D] Raw Device Data (Sensors)")
        print("  [L] Landscape Data")
        print("  [C] Glove Calibration")
        print("  [P] Pairing / Unpairing")
        print("  [K] Skeleton Management")
        print("  [T] Trackers")
        print("  [Y] Tracking Settings")
        print("  [U] Users")
        print("  [Q] Quit")
        print("="*60)
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'G':
                self.current_menu = self.display_gloves_menu
            elif ch == 'S':
                self.current_menu = self.display_skeleton_menu
            elif ch == 'R':
                self.current_menu = self.display_raw_skeleton_menu
            elif ch == 'D':
                self.current_menu = self.display_raw_device_data_menu
            elif ch == 'L':
                self.current_menu = self.display_landscape_menu
            elif ch == 'C':
                self.current_menu = self.display_calibration_menu
            elif ch == 'P':
                self.current_menu = self.display_pairing_menu
            elif ch == 'K':
                self.current_menu = self.display_skeleton_management_menu
            elif ch == 'T':
                self.current_menu = self.display_tracker_menu
            elif ch == 'Y':
                self.current_menu = self.display_tracking_settings_menu
            elif ch == 'U':
                self.current_menu = self.display_users_menu
            elif ch == 'Q':
                self.running = False
    
    def display_gloves_menu(self):
        """Display gloves and ergonomics data"""
        # Update haptics state (check for timeout and send commands)
        self.update_haptics()
        
        print("="*60)
        print("GLOVES & ERGONOMICS DATA")
        print("="*60)
        print("Haptics (HOLD): [1-5] Left (pinky-thumb)  [6-0] Right (thumb-pinky)")
        print("="*60)
        
        # Get current connected glove IDs from landscape (only paired gloves)
        connected_glove_ids = set()
        if self.landscape:
            gloves = self.landscape.get('gloves', [])
            for glove in gloves:
                try:
                    # Only include paired gloves (pairedState == 1)
                    from manus_sdk.generated._enums import DevicePairedState
                    state = glove.get('pairedState', 0)
                    if state == DevicePairedState.Paired or state == 1:
                        connected_glove_ids.add(glove['id'])
                except Exception:
                    pass  # Skip gloves we can't read
        
        # Clean up cached data for disconnected gloves
        # Remove data for gloves that are no longer connected
        disconnected_ids = set(self.ergonomics_data.keys()) - connected_glove_ids
        for glove_id in disconnected_ids:
            del self.ergonomics_data[glove_id]
        
        # Separate gloves by side and get full glove info
        left_glove_data = None
        right_glove_data = None
        left_glove_info = None
        right_glove_info = None
        
        if self.landscape:
            for glove in self.landscape.get('gloves', []):
                glove_id = glove['id']
                if glove_id in connected_glove_ids:
                    side = glove.get('side', 0)
                    ergo_data = self.ergonomics_data.get(glove_id)
                    if side == Side.Left or side == 1:
                        left_glove_data = (glove_id, ergo_data)
                        left_glove_info = glove
                    elif side == Side.Right or side == 2:
                        right_glove_data = (glove_id, ergo_data)
                        right_glove_info = glove
        
        # Display Left Glove
        print("\nLeft Glove:")
        if left_glove_data:
            glove_id, ergo_data = left_glove_data
            haptic_str = " [HAPTIC]" if left_glove_info and left_glove_info.get('isHaptics') else ""
            print(f"  Glove ID: {glove_id} (0x{glove_id:X}){haptic_str}")
            if ergo_data:
                print(f"  Joint Angles (degrees):")
                for line in self.format_ergonomics_data(ergo_data, is_left_hand=True):
                    print(line)
            else:
                print("  (Connected, waiting for ergonomics data...)")
        else:
            print("  (Not connected)")
        
        # Display Right Glove
        print("\nRight Glove:")
        if right_glove_data:
            glove_id, ergo_data = right_glove_data
            haptic_str = " [HAPTIC]" if right_glove_info and right_glove_info.get('isHaptics') else ""
            print(f"  Glove ID: {glove_id} (0x{glove_id:X}){haptic_str}")
            if ergo_data:
                print(f"  Joint Angles (degrees):")
                for line in self.format_ergonomics_data(ergo_data, is_left_hand=False):
                    print(line)
            else:
                print("  (Connected, waiting for ergonomics data...)")
        else:
            print("  (Not connected)")
        
        if not left_glove_data and not right_glove_data:
            print("\nNo gloves connected")
            print("(Connect Manus gloves to see live data)")
        
        print("\n[B] Back to main menu")
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                # Stop all haptics when leaving menu
                self.stop_all_haptics()
                self.current_menu = None
            elif ch in '12345':
                # Left hand haptics: 1=pinky, 2=ring, 3=middle, 4=index, 5=thumb
                self.set_haptic_finger_left(ch, 1.0)
            elif ch in '67890':
                # Right hand haptics: 6=thumb, 7=index, 8=middle, 9=ring, 0=pinky
                self.set_haptic_finger_right(ch, 1.0)
    
    def set_haptic_finger_left(self, key, power):
        """Set haptic power for a left hand finger"""
        key_to_finger = {'1': 4, '2': 3, '3': 2, '4': 1, '5': 0}
        finger_idx = key_to_finger.get(key)
        if finger_idx is not None:
            self.haptic_left_powers[finger_idx] = power
            self.haptic_last_key_time = time.time()
    
    def set_haptic_finger_right(self, key, power):
        """Set haptic power for a right hand finger"""
        key_to_finger = {'6': 0, '7': 1, '8': 2, '9': 3, '0': 4}
        finger_idx = key_to_finger.get(key)
        if finger_idx is not None:
            self.haptic_right_powers[finger_idx] = power
            self.haptic_last_key_time = time.time()
    
    def update_haptics(self):
        """Update haptics - send commands and handle timeout"""
        current_time = time.time()
        
        # Check if we should stop haptics (no key pressed for timeout duration)
        if current_time - self.haptic_last_key_time > self.haptic_timeout:
            # Clear all powers if any are active
            if any(p > 0 for p in self.haptic_left_powers) or any(p > 0 for p in self.haptic_right_powers):
                self.haptic_left_powers = [0.0] * 5
                self.haptic_right_powers = [0.0] * 5
        
        # Send haptic commands to gloves
        self.send_haptic_commands()
    
    def stop_all_haptics(self):
        """Stop all haptic feedback"""
        self.haptic_left_powers = [0.0] * 5
        self.haptic_right_powers = [0.0] * 5
        self.send_haptic_commands()
    
    def send_haptic_commands(self):
        """Send current haptic power levels to gloves"""
        if not self.landscape:
            return
        
        for glove in self.landscape.get('gloves', []):
            glove_id = glove['id']
            side = glove.get('side', 0)
            
            powers = ffi.new("float[5]")
            if side == Side.Left or side == 1:
                for i in range(5):
                    powers[i] = self.haptic_left_powers[i]
            elif side == Side.Right or side == 2:
                for i in range(5):
                    powers[i] = self.haptic_right_powers[i]
            else:
                continue
            
            lib.CoreSdk_VibrateFingersForGlove(glove_id, powers)
    
    def trigger_haptic_left(self, key):
        """Trigger haptic feedback on left glove finger
        Keys: 1=pinky, 2=ring, 3=middle, 4=index, 5=thumb
        Powers array order: Thumb, Index, Middle, Ring, Pinky
        """
        # Map key to finger index in powers array (Thumb=0, Index=1, Middle=2, Ring=3, Pinky=4)
        key_to_finger = {'1': 4, '2': 3, '3': 2, '4': 1, '5': 0}  # 1=pinky(4), 5=thumb(0)
        finger_idx = key_to_finger.get(key)
        if finger_idx is None:
            self.log("DEBUG", f"Invalid key for left haptic: {repr(key)}")
            return
        
        # Get left glove ID from landscape
        left_glove_id = None
        if self.landscape:
            for glove in self.landscape.get('gloves', []):
                side = glove.get('side', 0)
                if side == Side.Left or side == 1:
                    left_glove_id = glove['id']
                    break
        
        if left_glove_id is None:
            self.log("WARN", "No left glove connected for haptics")
            return
        
        # Create powers array with 1.0 for the target finger, 0.0 for others
        powers = ffi.new("float[5]")
        for i in range(5):
            powers[i] = 1.0 if i == finger_idx else 0.0
        
        finger_names = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
        self.log("INFO", f"Sending haptic: Left {finger_names[finger_idx]}, GloveID=0x{left_glove_id:X}")
        
        result = lib.CoreSdk_VibrateFingersForGlove(left_glove_id, powers)
        if result == SDKReturnCode.Success:
            self.log("INFO", f"Haptic OK: Left {finger_names[finger_idx]}")
        else:
            self.log("ERROR", f"Haptic failed: {SDKReturnCode(result).name} ({result})")
    
    def trigger_haptic_right(self, key):
        """Trigger haptic feedback on right glove finger
        Keys: 6=thumb, 7=index, 8=middle, 9=ring, 0=pinky
        Powers array order: Thumb, Index, Middle, Ring, Pinky
        """
        # Map key to finger index in powers array (Thumb=0, Index=1, Middle=2, Ring=3, Pinky=4)
        key_to_finger = {'6': 0, '7': 1, '8': 2, '9': 3, '0': 4}  # 6=thumb(0), 0=pinky(4)
        finger_idx = key_to_finger.get(key)
        if finger_idx is None:
            self.log("DEBUG", f"Invalid key for right haptic: {repr(key)}")
            return
        
        # Get right glove ID from landscape
        right_glove_id = None
        if self.landscape:
            for glove in self.landscape.get('gloves', []):
                side = glove.get('side', 0)
                if side == Side.Right or side == 2:
                    right_glove_id = glove['id']
                    break
        
        if right_glove_id is None:
            self.log("WARN", "No right glove connected for haptics")
            return
        
        # Create powers array with 1.0 for the target finger, 0.0 for others
        powers = ffi.new("float[5]")
        for i in range(5):
            powers[i] = 1.0 if i == finger_idx else 0.0
        
        finger_names = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
        self.log("INFO", f"Sending haptic: Right {finger_names[finger_idx]}, GloveID=0x{right_glove_id:X}")
        
        result = lib.CoreSdk_VibrateFingersForGlove(right_glove_id, powers)
        if result == SDKReturnCode.Success:
            self.log("INFO", f"Haptic OK: Right {finger_names[finger_idx]}")
        else:
            self.log("ERROR", f"Haptic failed: {SDKReturnCode(result).name} ({result})")

    def display_skeleton_menu(self):
        """Display skeleton data"""
        print("="*60)
        print("SKELETON DATA (Processed)")
        print("="*60)
        print("[D] Toggle detailed view  |  [B] Back to main menu")
        print("="*60)
        
        if self.skeletons:
            print(f"\nReceived {len(self.skeletons)} skeleton(s):\n")
            
            for i, skeleton in enumerate(self.skeletons):
                skeleton_id = skeleton['skeleton_id']
                nodes_count = skeleton['nodes_count']
                
                print(f"Skeleton #{i+1}:")
                print(f"  Skeleton ID: {skeleton_id}")
                print(f"  Node Count: {nodes_count}")
                
                # Show detailed view if enabled
                show_all = hasattr(self, 'show_skeleton_details') and self.show_skeleton_details
                for line in self.format_skeleton_nodes(skeleton['nodes'], show_all=show_all):
                    print(line)
                
                print()  # Blank line between skeletons
                
        else:
            print("\nNo skeleton data available")
        
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'D':
                # Toggle detailed view
                if not hasattr(self, 'show_skeleton_details'):
                    self.show_skeleton_details = False
                self.show_skeleton_details = not self.show_skeleton_details
    
    def display_raw_skeleton_menu(self):
        """Display raw skeleton data"""
        # Initialize hand selection if not set
        if not hasattr(self, 'show_raw_skeleton_hand'):
            self.show_raw_skeleton_hand = 'left'
        
        current_hand = self.show_raw_skeleton_hand.upper()
        print("="*60)
        print(f"RAW SKELETON DATA - {current_hand} HAND")
        print("="*60)
        print("[H] Toggle hand  |  [D] Toggle detail  |  [B] Back")
        print("="*60)
        
        # Get current connected glove IDs from landscape
        connected_glove_ids = set()
        if self.landscape:
            gloves = self.landscape.get('gloves', [])
            for glove in gloves:
                try:
                    connected_glove_ids.add(glove['id'])
                except Exception:
                    pass
        
        # Clean up cached data for disconnected gloves
        disconnected_ids = set(self.raw_skeleton_data.keys()) - connected_glove_ids
        for glove_id in disconnected_ids:
            del self.raw_skeleton_data[glove_id]
        
        # Filter by selected hand
        target_side = 1 if self.show_raw_skeleton_hand == 'left' else 2
        skeleton_for_hand = None
        
        # Find the skeleton data for the selected hand
        for glove_id, skeleton in self.raw_skeleton_data.items():
            if skeleton['nodes'] and 'node_info' in skeleton['nodes'][0]:
                side = skeleton['nodes'][0]['node_info']['side']
                if side == target_side:
                    skeleton_for_hand = skeleton
                    break
        
        if skeleton_for_hand:
            glove_id = skeleton_for_hand['glove_id']
            nodes_count = skeleton_for_hand['nodes_count']
            
            # Determine side name
            side_name = "Left" if target_side == 1 else "Right"
            
            print(f"\n{side_name} Hand Skeleton:")
            print(f"  Glove ID: {glove_id} (0x{glove_id:X})")
            print(f"  Node Count: {nodes_count}")
            
            # Show detailed view if enabled
            show_all = hasattr(self, 'show_skeleton_details') and self.show_skeleton_details
            for line in self.format_skeleton_nodes(skeleton_for_hand['nodes'], show_all=show_all):
                print(line)
            
            print()  # Blank line
        else:
            if self.raw_skeleton_data:
                print(f"\nNo {current_hand} hand data available")
            else:
                print("\nNo raw skeleton data available")
        
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'D':
                # Toggle detailed view
                if not hasattr(self, 'show_skeleton_details'):
                    self.show_skeleton_details = False
                self.show_skeleton_details = not self.show_skeleton_details
            elif ch == 'H':
                # Toggle between left and right hand
                self.show_raw_skeleton_hand = 'right' if self.show_raw_skeleton_hand == 'left' else 'left'
    
    def format_landscape_tree(self, compact=True, max_width=80):
        """Format landscape data as a tree structure"""
        lines = []
        
        if not self.landscape:
            return ["No landscape data available"]
        
        # Read counts - now from dictionary
        try:
            glove_count = self.landscape['glove_count']
            dongle_count = self.landscape['dongle_count']
            user_count = self.landscape['user_count']
            skeleton_count = self.landscape['skeleton_count']
            tracker_count = self.landscape['tracker_count']
        except Exception as e:
            return [f"Error reading landscape counts: {e}"]
        
        # Sanity check counts (should already be validated, but double-check)
        if (glove_count < 0 or glove_count > 32 or 
            dongle_count < 0 or dongle_count > 32 or 
            user_count < 0 or user_count > 10 or 
            skeleton_count < 0 or skeleton_count > 32 or 
            tracker_count < 0 or tracker_count > 32):
            return [
                "Invalid landscape data (counts out of range)",
                f"  Gloves: {glove_count} (max 32)",
                f"  Dongles: {dongle_count} (max 32)",
                f"  Users: {user_count} (max 10)",
                f"  Skeletons: {skeleton_count} (max 32)",
                f"  Trackers: {tracker_count} (max 32)"
            ]
        
        def truncate(line, width=max_width):
            """Truncate line to max width"""
            if len(line) > width:
                return line[:width-3] + "..."
            return line
        
        lines.append(truncate("╔═══ Landscape ═══"))
        
        # DEVICES - compact view
        lines.append(truncate("║"))
        lines.append(truncate("╠═ Devices"))
        
        # Dongles
        if dongle_count > 0:
            lines.append(truncate(f"║  ├─ Dongles: {dongle_count}"))
            dongles = self.landscape.get('dongles', [])
            for i in range(min(len(dongles), 3 if compact else len(dongles))):
                d = dongles[i]
                fw = d['firmwareVersion']
                # Show basic info without channel
                lines.append(truncate(f"║  │  • ID:0x{d['id']:X} FW:{fw['major']}.{fw['minor']}.{fw['patch']}"))
            if compact and len(dongles) > 3:
                lines.append(truncate(f"║  │  ... and {len(dongles) - 3} more"))
        
        # Gloves
        if glove_count > 0:
            lines.append(truncate(f"║  └─ Gloves: {glove_count}"))
            gloves = self.landscape.get('gloves', [])
            for i in range(min(len(gloves), 4 if compact else len(gloves))):
                g = gloves[i]
                from manus_sdk.generated._enums import Side
                side = "L" if g['side'] == Side.Left else "R"
                # Signal strength is a percentage (0-100)
                signal_pct = g['transmissionStrength']
                lines.append(truncate(f"║     • {side}-Hand ID:0x{g['id']:X} Batt:{g['batteryPercentage']}% Sig:{signal_pct}%"))
            if compact and len(gloves) > 4:
                lines.append(truncate(f"║     ... and {len(gloves) - 4} more"))
        
        # USERS
        lines.append(truncate("║"))
        if user_count > 0:
            lines.append(truncate(f"╠═ Users: {user_count}"))
            users = self.landscape.get('users', [])
            for i in range(min(len(users), 2 if compact else len(users))):
                u = users[i]
                user_name = u['name'] if u['name'] else f"User{i}"
                has_left = "L" if u['leftGloveID'] else "-"
                has_right = "R" if u['rightGloveID'] else "-"
                
                if compact:
                    # Compact: just name, ID, and gloves
                    lines.append(truncate(f"║  • {user_name} (ID:{u['id']}) Gloves:[{has_left}{has_right}]"))
                else:
                    # Detailed: show more properties
                    from manus_sdk.generated._enums import ProfileType
                    profile_name = "Hands" if u['profileType'] == ProfileType.Hands else "FullBody"
                    
                    lines.append(truncate(f"║  ├─ {user_name}"))
                    lines.append(truncate(f"║  │  • ID: {u['id']}"))
                    lines.append(truncate(f"║  │  • Dongle: 0x{u['dongleID']:X}"))
                    
                    if u['leftGloveID']:
                        lines.append(truncate(f"║  │  • Left Glove: 0x{u['leftGloveID']:X}"))
                    else:
                        lines.append(truncate(f"║  │  • Left Glove: None"))
                    
                    if u['rightGloveID']:
                        lines.append(truncate(f"║  │  • Right Glove: 0x{u['rightGloveID']:X}"))
                    else:
                        lines.append(truncate(f"║  │  • Right Glove: None"))
                
                    
            if compact and len(users) > 2:
                lines.append(truncate(f"║  ... and {len(users) - 2} more"))
        else:
            lines.append(truncate("╠═ Users: 0"))
        
        # SKELETONS
        lines.append(truncate("║"))
        if skeleton_count > 0:
            lines.append(truncate(f"╠═ Skeletons: {skeleton_count}"))
            skeletons = self.landscape.get('skeletons', [])
            for i in range(min(len(skeletons), 2 if compact else len(skeletons))):
                s = skeletons[i]
                from manus_sdk.generated._enums import SkeletonType
                skel_type = "Hand" if s['type'] == SkeletonType.Hand else "Body"
                lines.append(truncate(f"║  • Skeleton {s['id']} ({skel_type}) User:{s['userId']}"))
            if compact and len(skeletons) > 2:
                lines.append(truncate(f"║  ... and {len(skeletons) - 2} more"))
        else:
            lines.append(truncate("╠═ Skeletons: 0"))
        
        # TRACKERS
        lines.append(truncate("║"))
        if tracker_count > 0:
            lines.append(truncate(f"╠═ Trackers: {tracker_count}"))
            trackers = self.landscape.get('trackers', [])
            for i in range(min(len(trackers), 2 if compact else len(trackers))):
                t = trackers[i]
                tracker_id = t['id'] if t['id'] else f"T{i}"
                product = t['productName'] if t['productName'] else "Unknown"
                lines.append(truncate(f"║  • {tracker_id} ({product}) User:{t['user']}"))
            if compact and len(trackers) > 2:
                lines.append(truncate(f"║  ... and {len(trackers) - 2} more"))
        else:
            lines.append(truncate("╠═ Trackers: 0"))
        
        # SETTINGS
        lines.append(truncate("║"))
        lines.append(truncate("╚═ Settings"))
        try:
            settings = self.landscape.get('settings', {})
            if settings and 'manusCoreVersion' in settings:
                ver = settings['manusCoreVersion']
                lines.append(truncate(f"   • Manus Core: v{ver['major']}.{ver['minor']}.{ver['patch']}"))
                # Display mode info
                modes = []
                if settings.get('playbackMode'):
                    modes.append("Playback")
                if settings.get('recordingMode'):
                    modes.append("Recording")
                if settings.get('isNetDevice'):
                    modes.append("NetDevice")
                mode_str = ", ".join(modes) if modes else "Live"
                lines.append(truncate(f"   • Mode: {mode_str}"))
                # Display license info
                license_info = settings.get('license', {})
                max_pairs = license_info.get('maxGlovePairs', 0)
                lines.append(truncate(f"   • Max Glove Pairs: {max_pairs}"))
                # Collect all enabled features
                features = []
                if license_info.get('sdk'):
                    features.append("SDK")
                if license_info.get('raw'):
                    features.append("Raw")
                if license_info.get('recording'):
                    features.append("Recording")
                if license_info.get('exporting'):
                    features.append("Export")
                if license_info.get('advancedExporting'):
                    features.append("Adv.Export")
                if license_info.get('integrated'):
                    features.append("Integrated")
                if license_info.get('unitySession'):
                    features.append("Unity")
                if license_info.get('unrealSession'):
                    features.append("Unreal")
                if license_info.get('openXRSession'):
                    features.append("OpenXR")
                if license_info.get('mobuSession'):
                    features.append("MotionBuilder")
                if license_info.get('xsensSession'):
                    features.append("Xsens")
                if license_info.get('optitrackSession'):
                    features.append("OptiTrack")
                if license_info.get('qualisysSession'):
                    features.append("Qualisys")
                if license_info.get('viconSession'):
                    features.append("Vicon")
                if license_info.get('nokovSession'):
                    features.append("Nokov")
                if license_info.get('icidoSession'):
                    features.append("ICIDO")
                if license_info.get('siemensSession'):
                    features.append("Siemens")
                if license_info.get('vredSession'):
                    features.append("VRED")
                if license_info.get('cortexSession'):
                    features.append("Cortex")
                if license_info.get('fzMotionSession'):
                    features.append("FZMotion")
                if license_info.get('worldVizSession'):
                    features.append("WorldViz")
                if license_info.get('noraxonSession'):
                    features.append("Noraxon")
                if license_info.get('noitomSession'):
                    features.append("Noitom")
                if features:
                    if compact:
                        lines.append(truncate(f"   • Features: {', '.join(features)}"))
                    else:
                        lines.append(f"   • Features: {', '.join(features)}")
            else:
                lines.append(truncate("   • Settings unavailable"))
        except Exception:
            lines.append(truncate("   • Settings unavailable"))
        
        return lines

    def display_raw_device_data_menu(self):
        """Display raw device sensor data"""
        print("="*60)
        print("RAW DEVICE DATA - Sensor Information")
        print("="*60)
        print("[B] Back to main menu")
        print("="*60)
        
        if not self.raw_device_data:
            print("\nNo raw device data available")
            print("(Connect devices with sensors to see data)")
        else:
            print(f"\nConnected Devices: {len(self.raw_device_data)}\n")
            
            for device_id, device_data in self.raw_device_data.items():
                print(f"Device ID: 0x{device_id:X}")
                print(f"  Sensor Count: {device_data['sensor_count']}")
                
                if device_data['sensor_count'] > 0:
                    print("  Sensors:")
                    for idx, sensor in enumerate(device_data['sensors']):
                        pos = sensor['position']
                        rot = sensor['rotation']
                        print(f"    Sensor {idx + 1}:")
                        print(f"      Position: ({pos['x']:7.3f}, {pos['y']:7.3f}, {pos['z']:7.3f})")
                        print(f"      Rotation: (W:{rot['w']:6.3f}, X:{rot['x']:6.3f}, Y:{rot['y']:6.3f}, Z:{rot['z']:6.3f})")
                
                device_rot = device_data['rotation']
                print(f"  Device Rotation: (W:{device_rot['w']:6.3f}, X:{device_rot['x']:6.3f}, Y:{device_rot['y']:6.3f}, Z:{device_rot['z']:6.3f})")
                print()
        
        self.display_logs()
        
        # Check for key press
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None

    def display_landscape_menu(self):
        """Display landscape data"""
        # Check if we should show detailed view
        show_detailed = hasattr(self, 'show_landscape_details') and self.show_landscape_details
        view_mode = "DETAILED" if show_detailed else "COMPACT"
        
        print("="*60)
        print(f"LANDSCAPE DATA - System Overview ({view_mode})")
        print("="*60)
        print("[D] Toggle detailed view  |  [B] Back to main menu")
        print("="*60)
        
        if self.landscape:
            print()
            for line in self.format_landscape_tree(compact=not show_detailed):
                print(line)
        else:
            print("\nNo landscape data available")
            print("(Waiting for Manus Core connection...)")
        
        print()
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'D':
                # Toggle detailed view
                if not hasattr(self, 'show_landscape_details'):
                    self.show_landscape_details = False
                self.show_landscape_details = not self.show_landscape_details
    
    def display_calibration_menu(self):
        """Display glove calibration menu"""
        print("="*60)
        print("GLOVE CALIBRATION")
        print("="*60)
        
        hand_name = "Left" if self.calibrate_left_hand else "Right"
        glove_id = self.get_calibration_glove_id()
        
        if not self.calibration_started:
            # Before calibration starts - show hand selection
            print("[H] Toggle Hand  | [B] Back to main menu")
            print("[K] Save Calibration | [L] Load Calibration")
            print("="*60)
            print(f"\nSelected Hand: {hand_name}")
            
            if glove_id:
                print(f"Glove ID: {glove_id} (0x{glove_id:X})")
                print(f"\nReady to calibrate {hand_name} hand")
                print(f"Press [S] to START calibration")
            else:
                print(f"\nNo {hand_name} glove connected")
                print("Please connect a glove and try again")
        else:
            # During/after calibration - show step information
            print("[P] Next Step  |  [M] Prev Step  |  [C] Cancel  |  [F] Finish")
            print("[E] Execute Step  |  [B] Back to main menu")
            print("="*60)
            print(f"\nCalibrating: {hand_name} Hand")
            print(f"Glove ID: {glove_id} (0x{glove_id:X})")
            print(f"Calibration Step: {self.calibration_step + 1}/{self.number_of_calibration_steps}")
            
            if self.calibration_in_progress:
                print(f"Status: Executing step...")
            else:
                print(f"Status: {self.calibration_message if self.calibration_message else 'Ready'}")
            
            # Display step information
            if self.calibration_step_data is None:
                self.update_current_step_data(glove_id)
            
            if self.calibration_step_data:
                print(f"\nStep Instructions:")
                title = self.calibration_step_data.get('title', '')
                description = self.calibration_step_data.get('description', '')
                duration = self.calibration_step_data.get('time', 0)
                
                if title and title.strip():
                    print(f"  Title: {title}")
                if description and description.strip():
                    print(f"  Description: {description}")
                if duration > 0:
                    print(f"  Hold Position For: {duration} seconds")
                
                print(f"\nPress [E] to execute this step")
            else:
                print(f"\nStep Information: (Loading...)")
        
        print()
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'H' and not self.calibration_started:
                self.calibrate_left_hand = not self.calibrate_left_hand
                self.calibration_step = 0
            elif ch == 'P' and self.calibration_started and self.calibration_step < self.number_of_calibration_steps - 1:
                self.calibration_step += 1
                self.calibration_step_data = None
            elif ch == 'M' and self.calibration_started and self.calibration_step > 0:
                self.calibration_step -= 1
                self.calibration_step_data = None
            elif ch == 'S' and not self.calibration_started:
                self.start_glove_calibration()
            elif ch == 'C' and self.calibration_started:
                self.cancel_glove_calibration()
            elif ch == 'F' and self.calibration_started:
                self.finish_glove_calibration()
            elif ch == 'E' and self.calibration_started:
                self.execute_calibration_step()
            elif ch == 'K' and not self.calibration_started:
                self.save_glove_calibration()
            elif ch == 'L' and not self.calibration_started:
                self.load_glove_calibration()
    
    def retrieve_license(self):
        """Retrieve the newest license for the first connected dongle.

        Core reads the dongle's current license itself and exchanges it with the license service
        (Core must have a licenseServiceUrl configured).
        """
        dongles = self.landscape.get('dongles', []) if self.landscape else []
        if not dongles:
            self.log("WARN", "No dongle available to retrieve a license for")
            return

        dongle_id = dongles[0]['id']
        response = ffi.new("Response*")
        result = lib.CoreSdk_RetrieveLicense(dongle_id, response)
        msg = ffi.string(response.message.message).decode('utf-8', errors='replace')
        if result == SDKReturnCode.Success and response.result:
            self.log("INFO", f"License retrieved for dongle {dongle_id}: {msg}")
        elif result == SDKReturnCode.Success:
            self.log("ERROR", f"Retrieve license failed for dongle {dongle_id}: {msg or 'no details, check the Core log'}")
        else:
            detail = f": {msg}" if msg else ""
            self.log("ERROR", f"Retrieve license failed: {SDKReturnCode(result).name}{detail}")

    def display_pairing_menu(self):
        """Display glove pairing/unpairing menu"""
        print("="*60)
        print("GLOVE PAIRING / UNPAIRING")
        print("="*60)
        print("[P] Pair first available unpaired glove")
        print("[U] Unpair first available paired glove")
        print("[R] Retrieve first dongle's license")
        print("[B] Back to main menu")
        print("="*60)
        
        # Display pairing status
        paired_count = 0
        unpaired_count = 0
        
        if self.landscape:
            gloves = self.landscape.get('gloves', [])
            for glove in gloves:
                try:
                    from manus_sdk.generated._enums import DevicePairedState
                    state = glove['pairedState']
                    if state == DevicePairedState.Paired or state == 1:  # 1 = Paired
                        paired_count += 1
                    elif state == DevicePairedState.Unpaired or state == 2:  # 2 = Unpaired
                        unpaired_count += 1
                except Exception:
                    pass
        
        print(f"\nPairing Status:")
        print(f"  Paired Gloves: {paired_count}")
        print(f"  Unpaired Gloves: {unpaired_count}")
        
        if unpaired_count > 0:
            print(f"\n  Press [P] to pair the first available unpaired glove")
        
        if paired_count > 0:
            print(f"  Press [U] to unpair the first available paired glove")
        
        if paired_count == 0 and unpaired_count == 0:
            print(f"\n  No gloves available")
        
        print()
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'P':
                self.pair_glove()
            elif ch == 'U':
                self.unpair_glove()
            elif ch == 'R':
                self.retrieve_license()
    
    def display_skeleton_management_menu(self):
        """Display skeleton loading/unloading menu"""
        print("="*60)
        print("SKELETON MANAGEMENT")
        print("="*60)
        print("[L] Load Left Hand Skeleton")
        print("[R] Load Right Hand Skeleton")
        print("[U] Unload Skeleton")
        print("[B] Back to main menu")
        print("="*60)
        
        print(f"\nLoaded Skeletons: {len(self.loaded_skeletons)}")
        if self.loaded_skeletons:
            for i, skeleton_id in enumerate(self.loaded_skeletons):
                print(f"  {i+1}. Skeleton ID: {skeleton_id}")
        else:
            print(f"  (None)")
        
        print(f"\nActions:")
        print(f"  [L] - Creates and loads a left hand skeleton")
        print(f"  [R] - Creates and loads a right hand skeleton")
        print(f"  [U] - Unloads the first loaded skeleton")
        
        print()
        self.display_logs()
        
        # Check for key press (non-blocking)
        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'L':
                self.load_test_skeleton('left')
            elif ch == 'R':
                self.load_test_skeleton('right')
            elif ch == 'U':
                self.unload_test_skeleton()

    def _make_tracker_id(self, id_str):
        """Build a TrackerId CFFI value from a string."""
        tracker_id = ffi.new("TrackerId*")
        encoded = id_str.encode('utf-8')
        # Use memmove to copy bytes into the char array
        ffi.memmove(tracker_id.id, encoded, len(encoded))
        tracker_id.id[len(encoded)] = b'\x00'  # Null terminate
        return tracker_id[0]

    def assign_tracker(self):
        """Assign the first available tracker to the first user and give it a LeftHand role."""
        trackers = self.landscape.get('trackers', []) if self.landscape else []
        users = self.landscape.get('users', []) if self.landscape else []

        if not trackers:
            self.log("INFO", "No trackers in landscape")
            return
        
        if not users:
            self.log("ERROR", "No users in landscape")
            return

        tid_str = trackers[0]['id']
        first_user_id = users[0].get('id', 0)
        tracker_id = self._make_tracker_id(tid_str)

        result = lib.CoreSdk_AssignTrackerToUser(tracker_id, first_user_id)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"AssignTrackerToUser failed: {SDKReturnCode(result).name if isinstance(result, int) else result}")
            return

        result = lib.CoreSdk_AssignRoleToTracker(tracker_id, TrackerType.LeftHand)
        if result != SDKReturnCode.Success:
            self.log("WARN", f"AssignRoleToTracker failed: {SDKReturnCode(result).name if isinstance(result, int) else result}")
        else:
            self.log("INFO", f"Tracker '{tid_str}' assigned to user {first_user_id} as LeftHand")

    def unassign_tracker(self):
        """Unassign the first assigned tracker from its user (assigns to userId=0)."""
        trackers = self.landscape.get('trackers', []) if self.landscape else []

        if not trackers:
            self.log("INFO", "No trackers in landscape")
            return

        tid_str = trackers[0]['id']
        tracker_id = self._make_tracker_id(tid_str)

        result = lib.CoreSdk_AssignTrackerToUser(tracker_id, 0)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"UnassignTracker failed: {result}")
        else:
            self.log("INFO", f"Tracker '{tid_str}' unassigned")

    def set_tracker_offset(self):
        """Set the tracker offset for the first user's left-hand tracker to the
        MANUS Universal mount center point.
        """
        first_user_id = 0
        users = self.landscape.get('users', []) if self.landscape else []
        if users:
            first_user_id = users[0].get('id', 0)

        offset = ffi.new("TrackerOffset*")
        offset.entryType = TrackerOffsetType.LeftHandTrackerToWrist
        offset.translation.x = 0.0
        offset.translation.y = 0.0
        offset.translation.z = 0.0
        offset.rotation.w = 1.0
        offset.rotation.x = 0.0
        offset.rotation.y = 0.0
        offset.rotation.z = 0.0

        result = lib.CoreSdk_SetTrackerOffset(first_user_id, offset)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"SetTrackerOffset failed: {result}")
        else:
            self.log("INFO", f"Tracker offset set for user {first_user_id}")

    def toggle_test_tracker(self):
        """Toggle a virtual test tracker sent to Core.
        When enabled, sends a TrackerData with a fixed position each display cycle.
        """
        self.test_tracker_enabled = not self.test_tracker_enabled
        state = "ON" if self.test_tracker_enabled else "OFF"
        self.log("INFO", f"Test tracker: {state}")

    def _send_test_tracker(self):
        """Send a single virtual TrackerData to Core."""
        data = ffi.new("TrackerData*")
        # Write tracker ID string into the fixed-size char array
        tid = b"test_tracker"
        ffi.memmove(data.trackerId.id, tid, len(tid))
        data.trackerId.id[len(tid)] = b'\x00'
        data.trackerType = TrackerType.Head
        data.userId = 0
        data.isHmd = False
        data.position.x = 0.0
        data.position.y = 1.0
        data.position.z = 0.0
        data.rotation.w = 1.0
        data.rotation.x = 0.0
        data.rotation.y = 0.0
        data.rotation.z = 0.0
        data.quality = TrackingQuality.Trackable
        lib.CoreSdk_SendDataForTrackers(data, 1)

    def display_tracker_menu(self):
        """Display tracker menu."""
        # Send test tracker every cycle if enabled
        if self.test_tracker_enabled:
            self._send_test_tracker()

        test_str = "ON" if self.test_tracker_enabled else "OFF"
        view_str = "Per-User" if self.show_trackers_per_user else "Global"
        print("="*60)
        print("TRACKERS")
        print("="*60)
        print(f"[O] Toggle Test Tracker ({test_str})  [G] Toggle View ({view_str})")
        print("[A] Assign Tracker  [U] Unassign Tracker  [T] Set Offset")
        print("[B] Back to main menu")
        print("="*60)

        # --- Live tracker data ---
        print()
        if not self.tracker_data:
            print("Tracker data: (none received yet)")
        elif not self.show_trackers_per_user:
            # Global view
            print(f"Tracker count: {len(self.tracker_data)}")
            for tid, t in self.tracker_data.items():
                try:
                    type_name = TrackerType(t['tracker_type']).name
                except Exception:
                    type_name = str(t['tracker_type'])
                try:
                    quality_name = TrackingQuality(t['quality']).name
                except Exception:
                    quality_name = str(t['quality'])
                px, py, pz = t['position']
                print(f"  [{tid}]  type={type_name}  user={t['user_id']}"
                      f"  pos=({px:.3f}, {py:.3f}, {pz:.3f})  quality={quality_name}")
        else:
            # Per-user view
            users = self.landscape.get('users', []) if self.landscape else []
            if not users:
                print("  (No users in landscape)")
            else:
                for user in users:
                    user_id = user.get('id', 0)
                    user_trackers = {tid: t for tid, t in self.tracker_data.items()
                                     if t['user_id'] == user_id}
                    print(f"\n  User {user_id}: {len(user_trackers)} tracker(s)")
                    for tid, t in user_trackers.items():
                        try:
                            type_name = TrackerType(t['tracker_type']).name
                        except Exception:
                            type_name = str(t['tracker_type'])
                        px, py, pz = t['position']
                        print(f"    [{tid}]  type={type_name}"
                              f"  pos=({px:.3f}, {py:.3f}, {pz:.3f})")

        print()
        self.display_logs()

        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'O':
                self.toggle_test_tracker()
            elif ch == 'G':
                self.show_trackers_per_user = not self.show_trackers_per_user
            elif ch == 'A':
                self.assign_tracker()
            elif ch == 'U':
                self.unassign_tracker()
            elif ch == 'T':
                self.set_tracker_offset()

    # ------------------------------------------------------------------
    # Users menu
    # ------------------------------------------------------------------

    def display_users_menu(self):
        """Display the Users management menu."""
        from manus_sdk.generated._enums import Side
        print("="*60)
        print("USERS")
        print("="*60)
        print("[Z] Disable Auto-Assignment  [X] Enable Auto-Assignment")
        print("[A] Add User   [R] Remove User")
        print("[D] Assign Dongle  [U] Unassign Dongle")
        print("[G] Assign Glove   [W] Unassign Glove")
        print("[I] Move User Up   [K] Move User Down")
        print("[N] Change Username")
        print("[B] Back to main menu")
        print("="*60)

        self._print_users_landscape_data()
        print()
        self.display_logs()

        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'Z':
                if lib.CoreSdk_SetAutoUserAssignment(False) == SDKReturnCode.Success:
                    self.log("INFO", "Disabled Auto Assignment")
                else:
                    self.log("WARN", "Something went wrong disabling Auto Assignment")
            elif ch == 'X':
                if lib.CoreSdk_SetAutoUserAssignment(True) == SDKReturnCode.Success:
                    self.log("INFO", "Enabled Auto Assignment")
                else:
                    self.log("WARN", "Something went wrong enabling Auto Assignment")
            elif ch == 'A':
                self._add_user()
            elif ch == 'R':
                self._remove_user()
            elif ch == 'D':
                self._assign_dongle()
            elif ch == 'U':
                self._unassign_dongle()
            elif ch == 'G':
                self._assign_glove_to_user()
            elif ch == 'W':
                self._unassign_glove()
            elif ch == 'I':
                self._move_user_up()
            elif ch == 'K':
                self._move_user_down()
            elif ch == 'N':
                self._rename_user()

    def _print_users_landscape_data(self):
        """Print all users from the current landscape."""
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            print("  (No users)")
            return
        for u in users:
            print(f"  User: {u['name']}, ID: {u['id']}, "
                  f"Dongle ID: {u['dongleID']}, "
                  f"Left Glove ID: {u['leftGloveID']}, "
                  f"Right Glove ID: {u['rightGloveID']}")

    def _add_user(self):
        user_id_ptr = ffi.new("uint32_t*")
        username = ffi.new("char[]", b"")
        if lib.CoreSdk_AddUser(username, user_id_ptr) != SDKReturnCode.Success:
            self.log("WARN", "Something went wrong creating a new user.")
            return
        self.log("INFO", f"User created with ID {user_id_ptr[0]}")

    def _remove_user(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not remove user, no users were found.")
            return
        # Remove the last user in the list.
        user = users[-1]
        if lib.CoreSdk_RemoveUser(user['id']) == SDKReturnCode.Success:
            self.log("INFO", f"Removed user {user['name']}")
        else:
            self.log("WARN", f"Something went wrong removing user {user['name']}")

    def _get_first_available_dongle_id(self):
        """Return the first dongle ID not already assigned to a user, or None."""
        if not self.landscape:
            return None
        assigned = {u['dongleID'] for u in self.landscape.get('users', []) if u['dongleID'] != 0}
        for d in self.landscape.get('dongles', []):
            if d['id'] not in assigned:
                return d['id']
        return None

    def _get_first_available_glove(self):
        """Return the first GloveLandscapeData dict not assigned to any user, or None."""
        if not self.landscape:
            return None
        assigned = set()
        for u in self.landscape.get('users', []):
            if u['leftGloveID'] != 0:
                assigned.add(u['leftGloveID'])
            if u['rightGloveID'] != 0:
                assigned.add(u['rightGloveID'])
        for g in self.landscape.get('gloves', []):
            if g['id'] not in assigned:
                return g
        return None

    def _assign_dongle(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not assign dongle, no users were found.")
            return
        dongle_id = self._get_first_available_dongle_id()
        if dongle_id is None:
            self.log("WARN", "Could not assign dongle, no available dongle was found.")
            return
        # Find a user with no dongle assigned
        user_id = next((u['id'] for u in users if u['dongleID'] == 0), None)
        if user_id is None:
            self.log("WARN", "Could not assign dongle, no available user was found.")
            return
        if lib.CoreSdk_AssignDongleToUser(user_id, dongle_id) == SDKReturnCode.Success:
            self.log("INFO", f"Assigned dongle {dongle_id} to user {user_id}.")
        else:
            self.log("WARN", f"Something went wrong assigning dongle {dongle_id} to user {user_id}.")

    def _unassign_dongle(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not unassign dongle, no users were found.")
            return
        # Find the first user with a dongle assigned
        user = next((u for u in users if u['dongleID'] != 0), None)
        if user is None:
            self.log("WARN", "Could not unassign dongle, no user with an assigned dongle was found.")
            return
        if lib.CoreSdk_AssignDongleToUser(user['id'], 0) == SDKReturnCode.Success:
            self.log("INFO", f"Unassigned dongle from user {user['id']}.")
        else:
            self.log("WARN", f"Something went wrong unassigning dongle from user {user['id']}.")

    def _assign_glove_to_user(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not assign glove, no users were found.")
            return
        glove = self._get_first_available_glove()
        if glove is None:
            self.log("WARN", "Could not assign glove, no available glove was found.")
            return
        side = glove['side']
        user_id = 0
        for u in users:
            if side == Side.Left and u['leftGloveID'] == 0:
                user_id = u['id']
                break
            elif side == Side.Right and u['rightGloveID'] == 0:
                user_id = u['id']
                break
        if user_id == 0:
            self.log("WARN", "Could not assign glove, no available user was found.")
            return
        if lib.CoreSdk_AssignGloveToUser(user_id, glove['id'], side) == SDKReturnCode.Success:
            self.log("INFO", f"Assigned glove {glove['id']} to user {user_id}.")
        else:
            self.log("WARN", f"Something went wrong assigning glove {glove['id']} to user {user_id}.")

    def _unassign_glove(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not unassign glove, no users were found.")
            return
        user_id = 0
        side = None
        for u in users:
            if u['leftGloveID'] != 0:
                user_id = u['id']
                side = Side.Left
                break
            elif u['rightGloveID'] != 0:
                user_id = u['id']
                side = Side.Right
                break
        if user_id == 0:
            self.log("WARN", "No glove to unassign was found.")
            return
        side_str = "left" if side == Side.Left else "right"
        if lib.CoreSdk_AssignGloveToUser(user_id, 0, side) == SDKReturnCode.Success:
            self.log("INFO", f"Unassigned {side_str} glove from user {user_id}.")
        else:
            self.log("WARN", f"Something went wrong unassigning {side_str} glove from user {user_id}.")

    def _move_user_up(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not move user, no users were found.")
            return
        # Move the user with the highest ID (most recently created)
        highest_id = max(u['id'] for u in users)
        if lib.CoreSdk_MoveUserUp(highest_id) == SDKReturnCode.Success:
            self.log("INFO", f"Moved user {highest_id} up.")
        else:
            self.log("WARN", f"Something went wrong moving user {highest_id} up.")

    def _move_user_down(self):
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not move user, no users were found.")
            return
        # Move the user with the highest ID (most recently created)
        highest_id = max(u['id'] for u in users)
        if lib.CoreSdk_MoveUserDown(highest_id) == SDKReturnCode.Success:
            self.log("INFO", f"Moved user {highest_id} down.")
        else:
            self.log("WARN", f"Something went wrong moving user {highest_id} down.")

    def _rename_user(self):
        MAX_NUM_CHARS_IN_USERNAME = 64
        users = self.landscape.get('users', []) if self.landscape else []
        if not users:
            self.log("WARN", "Could not rename user, no users were found.")
            return
        # Append a suffix to the first user's name.
        new_name = users[0]['name'] + " but different"
        if len(new_name) > MAX_NUM_CHARS_IN_USERNAME - 1:
            new_name = new_name[:MAX_NUM_CHARS_IN_USERNAME - 1]
        user_id = users[0]['id']
        name_bytes = new_name.encode('utf-8') + b'\x00'
        c_name = ffi.new("char[]", name_bytes)
        if lib.CoreSdk_SetUserName(user_id, c_name) == SDKReturnCode.Success:
            self.log("INFO", f"Renamed user {user_id}.")
        else:
            self.log("WARN", f"Something went wrong renaming user {user_id}.")

    # ------------------------------------------------------------------
    def display_tracking_settings_menu(self):
        """Display tracking timeout controls and tracker system selection."""
        print("="*60)
        print("TRACKING SETTINGS")
        print("="*60)
        print("[T] Toggle Tracker Timeouts")
        print("[L] Cycle Timeout Duration (10s / 30s)")
        print("[0-5] Open Tracker System  |  [B] Back")
        print("="*60)

        timeout_enabled = self._get_tracker_timeout_enabled()
        timeout_duration = self._get_tracker_timeout_duration()
        enabled_text = "Enabled" if timeout_enabled else "Disabled"
        print(f"\nTracker Timeouts: {enabled_text}  (Duration: {timeout_duration:.1f}s)")
        print("\nPress the corresponding number key to navigate to the relevant tracking system")

        print()
        self._print_tracker_systems()

        print()
        self.display_logs()

        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self.current_menu = None
            elif ch == 'T':
                self._toggle_tracker_timeout_enabled()
            elif ch == 'L':
                self._cycle_tracker_timeout_duration()
            elif ch.isdigit():
                self._select_tracker_system(int(ch))

    def display_tracker_system_menu(self):
        """Display the selected tracker system and its available settings."""
        if self._selected_tracker_system_setting_index >= 0:
            self._print_selected_tracker_system_setting()
            self._handle_selected_tracker_system_setting_input()
            return

        print("="*60)
        print("TRACKER SYSTEM")
        print("="*60)
        print("[A] Toggle Active")
        print("[0-9] Select Setting")
        print("[B] Back to tracking settings")
        print("="*60)
        print()

        self._print_tracker_system_settings()

        print()
        self.display_logs()

        if self.has_input():
            ch = self.get_char()
            if ch == 'B':
                self._selected_tracker_system_setting_index = -1
                self.current_menu = self.display_tracking_settings_menu
            elif ch == 'A':
                self._toggle_selected_tracker_system_active()
            elif ch.isdigit():
                self._select_tracker_system_setting(int(ch))

    # --- Tracking settings helpers ---

    def _get_tracker_timeout_enabled(self):
        """Query whether tracker timeouts are currently enabled."""
        enabled_ptr = ffi.new("bool*")
        result = lib.CoreSdk_GetTrackerTimeOutEnabled(enabled_ptr)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"GetTrackerTimeOutEnabled failed: {result}")
            return False
        return enabled_ptr[0]

    def _get_tracker_timeout_duration(self):
        """Query the current tracker timeout duration in seconds."""
        timeout_ptr = ffi.new("float*")
        result = lib.CoreSdk_GetTrackerTimeOut(timeout_ptr)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"GetTrackerTimeOut failed: {result}")
            return 0.0
        return timeout_ptr[0]

    def _toggle_tracker_timeout_enabled(self):
        """Toggle tracker timeouts on/off."""
        current = self._get_tracker_timeout_enabled()
        result = lib.CoreSdk_SetTrackerTimeOutEnabled(not current)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"SetTrackerTimeOutEnabled failed: {result}")
        else:
            state = "enabled" if not current else "disabled"
            self.log("INFO", f"Tracker timeouts {state}")

    def _cycle_tracker_timeout_duration(self):
        """Cycle the tracker timeout between 10s and 30s."""
        current = self._get_tracker_timeout_duration()
        new_duration = 10.0 if current == 30.0 else 30.0
        result = lib.CoreSdk_SetTrackerTimeOut(new_duration)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"SetTrackerTimeOut failed: {result}")
        else:
            self.log("INFO", f"Tracker timeout set to {new_duration:.0f}s")

    def _get_tracker_systems(self):
        """Retrieve all tracker systems and their settings from the SDK.

        Returns a list of dicts, or None on failure:
            [{'id': str, 'active': bool, 'settings': [{'id': str, 'type': str, 'value': ...}]}]
        """
        MAX_SYSTEMS = 6
        systems_array = ffi.new(f"TrackerSystem[{MAX_SYSTEMS}]")
        count_ptr = ffi.new("uint32_t*")

        result = lib.CoreSdk_GetTrackerSystemsSettings(systems_array, count_ptr)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"GetTrackerSystemsSettings failed: {result}")
            return None

        systems = []
        for i in range(count_ptr[0]):
            sys_data = systems_array[i]
            system_id = ffi.string(sys_data.id).decode('utf-8')
            settings = []

            for j in range(sys_data.currentSettingsCount):
                setting = sys_data.trackerSystemSettings[j]
                setting_id = ffi.string(setting.id).decode('utf-8')
                setting_type = setting.settingtype

                # Extract value based on type
                from manus_sdk.generated._enums import TrackerSystemSettingType
                if setting_type == TrackerSystemSettingType.SettingBool:
                    value = setting.settingBool.value
                    type_name = "bool"
                elif setting_type == TrackerSystemSettingType.SettingInt:
                    value = f"{setting.settingInt.value} (range {setting.settingInt.min}-{setting.settingInt.max})"
                    type_name = "int"
                elif setting_type == TrackerSystemSettingType.SettingFile:
                    value = ffi.string(setting.settingFile.value).decode('utf-8')
                    type_name = "file"
                elif setting_type == TrackerSystemSettingType.SettingIp:
                    value = ffi.string(setting.settingIp.value).decode('utf-8')
                    type_name = "ip"
                else:
                    value = "(unknown)"
                    type_name = "undefined"

                settings.append({'id': setting_id, 'type': type_name, 'value': value})

            systems.append({'id': system_id, 'active': sys_data.active, 'settings': settings})

        return systems

    def _print_tracker_systems(self):
        """Print all available tracker systems."""
        tracker_systems = self._get_tracker_systems()
        if tracker_systems is None:
            print("  (Could not retrieve tracker systems)")
            return
        if not tracker_systems:
            print("  No tracker systems available")
            return
        for i, system in enumerate(tracker_systems):
            print(f"  [{i}] {system['id']}")

    def _print_tracker_system_settings(self):
        """Print all settings for the selected tracker system."""
        selected = self._selected_tracker_system_index
        tracker_systems = self._get_tracker_systems()
        if tracker_systems is None:
            return
        if selected < 0 or selected >= len(tracker_systems):
            self.log("WARN", "Selected tracker system is out of range")
            self.current_menu = self.display_tracking_settings_menu
            self._selected_tracker_system_index = -1
            return

        system = tracker_systems[selected]
        active_str = "True" if system['active'] else "False"
        print(f"[A] Active: {active_str}")
        print()

        for i, setting in enumerate(system['settings']):
            print(f"[{i}] {setting['id']}")
            if setting['type'] == 'int':
                value_text = str(setting['value'])
                if ' (range ' in value_text:
                    value_only, range_part = value_text.split(' (range ', 1)
                    range_part = range_part.rstrip(')')
                    min_value, max_value = range_part.split('-', 1)
                    print(f"    Value: {value_only}")
                    print(f"    Min: {min_value}")
                    print(f"    Max: {max_value}")
                else:
                    print(f"    Value: {value_text}")
            elif setting['type'] == 'file':
                print(f"    Value: {setting['value']}")
            elif setting['type'] == 'bool':
                print(f"    Value: {setting['value']}")
            elif setting['type'] == 'ip':
                print(f"    Value: {setting['value']}")
            else:
                print(f"    Value: {setting['value']}")
            print()

    def _print_selected_tracker_system_setting(self):
        """Print the selected tracker system setting and its prompt."""
        selected_system = self._selected_tracker_system_index
        selected_setting = self._selected_tracker_system_setting_index
        tracker_systems = self._get_tracker_systems()
        if tracker_systems is None:
            return
        if selected_system < 0 or selected_system >= len(tracker_systems):
            self.log("WARN", "Selected tracker system is out of range")
            self._selected_tracker_system_setting_index = -1
            self.current_menu = self.display_tracking_settings_menu
            return

        system = tracker_systems[selected_system]
        if selected_setting < 0 or selected_setting >= len(system['settings']):
            self.log("WARN", "Selected tracker system setting is out of range")
            self._selected_tracker_system_setting_index = -1
            return

        setting = system['settings'][selected_setting]
        print("="*60)
        print(system['id'])
        print("="*60)
        if setting['type'] == 'int':
            value_text = str(setting['value'])
            if ' (range ' in value_text:
                value_only, range_part = value_text.split(' (range ', 1)
                range_part = range_part.rstrip(')')
                min_value, max_value = range_part.split('-', 1)
                print(f"Value: {value_only}")
                print(f"Min: {min_value}")
                print(f"Max: {max_value}")
            else:
                print(f"Value: {value_text}")
            print('Enter "back" to cancel or enter new value:')
        elif setting['type'] == 'file':
            print(f"Value: {setting['value']}")
            print('Enter "back" to cancel or enter new file path (without extension):')
        elif setting['type'] == 'bool':
            print(f"Value: {setting['value']}")
            print('Enter "back" to cancel or enter new value ([true] for true, [false] for false):')
        elif setting['type'] == 'ip':
            print(f"Value: {setting['value']}")
            print('Enter "back" to cancel or enter new IP:')
        else:
            print(f"Value: {setting['value']}")
            print('Enter "back" to cancel:')

    def _select_tracker_system(self, index):
        """Open the selected tracker system submenu."""
        systems = self._get_tracker_systems()
        if systems and 0 <= index < len(systems):
            self._selected_tracker_system_index = index
            self._selected_tracker_system_setting_index = -1
            self.current_menu = self.display_tracker_system_menu
        else:
            self.log("WARN", f"Invalid tracker system index: {index}")

    def _select_tracker_system_setting(self, index):
        """Select a setting inside the currently selected tracker system."""
        selected = self._selected_tracker_system_index
        systems = self._get_tracker_systems()
        if not systems or selected < 0 or selected >= len(systems):
            self.log("WARN", "No tracker system selected")
            return
        settings = systems[selected]['settings']
        if 0 <= index < len(settings):
            self._selected_tracker_system_setting_index = index
        else:
            self.log("WARN", f"Invalid tracker setting index: {index}")

    def _handle_selected_tracker_system_setting_input(self):
        """Read and apply a new value for the selected tracker system setting."""
        selected = self._selected_tracker_system_index
        setting_idx = self._selected_tracker_system_setting_index
        if selected < 0 or setting_idx < 0:
            self.log("WARN", "No tracker system setting selected")
            return

        from manus_sdk.generated._enums import TrackerSystemSettingType

        MAX_SYSTEMS = 6
        systems_array = ffi.new(f"TrackerSystem[{MAX_SYSTEMS}]")
        count_ptr = ffi.new("uint32_t*")

        result = lib.CoreSdk_GetTrackerSystemsSettings(systems_array, count_ptr)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"GetTrackerSystemsSettings failed: {result}")
            return

        if selected >= count_ptr[0]:
            self.log("WARN", "Selected system index out of range")
            self._selected_tracker_system_setting_index = -1
            return

        system = systems_array[selected]
        num_settings = system.currentSettingsCount
        if setting_idx >= num_settings:
            self.log("WARN", "Selected setting index out of range")
            self._selected_tracker_system_setting_index = -1
            return

        user_input = input().strip()
        if user_input.lower() == 'back':
            self._selected_tracker_system_setting_index = -1
            return

        setting = system.trackerSystemSettings[setting_idx]
        stype = setting.settingtype

        # Prompt for new value based on type
        if stype == TrackerSystemSettingType.SettingInt:
            try:
                int_val = int(user_input)
            except ValueError:
                self.log("ERROR", "Invalid input: not a valid integer")
                return
            system.trackerSystemSettings[setting_idx].settingInt.value = int_val

        elif stype == TrackerSystemSettingType.SettingFile:
            buf = setting.settingFile.value
            encoded = user_input.encode('utf-8')
            for k in range(min(len(encoded), 255)):
                buf[k] = encoded[k:k + 1]
            buf[min(len(encoded), 255)] = b'\x00'

        elif stype == TrackerSystemSettingType.SettingBool:
            value = user_input.lower()
            if value == 'true':
                system.trackerSystemSettings[setting_idx].settingBool.value = True
            elif value == 'false':
                system.trackerSystemSettings[setting_idx].settingBool.value = False
            else:
                self.log("ERROR", "Invalid input: not a valid boolean")
                return

        elif stype == TrackerSystemSettingType.SettingIp:
            buf = setting.settingIp.value
            encoded = user_input.encode('utf-8')
            for k in range(min(len(encoded), 39)):
                buf[k] = encoded[k:k + 1]
            buf[min(len(encoded), 39)] = b'\x00'

        else:
            self.log("WARN", "Cannot edit setting of unknown type")
            self._selected_tracker_system_setting_index = -1
            return

        # Push the modified system settings back to the SDK.
        systems_array[selected] = system
        result = lib.CoreSdk_SetTrackerSystemsSettings(systems_array)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"SetTrackerSystemsSettings failed: {result}")
        else:
            name = ffi.string(setting.id).decode()
            self.log("INFO", f"Setting '{name}' updated successfully")
        self._selected_tracker_system_setting_index = -1

    def _toggle_selected_tracker_system_active(self):
        """Toggle the 'active' flag of the currently selected tracker system."""
        selected = getattr(self, '_selected_tracker_system_index', None)
        if selected is None:
            self.log("WARN", "No tracker system selected. Press [0-5] first.")
            return

        MAX_SYSTEMS = 6
        systems_array = ffi.new(f"TrackerSystem[{MAX_SYSTEMS}]")
        count_ptr = ffi.new("uint32_t*")

        result = lib.CoreSdk_GetTrackerSystemsSettings(systems_array, count_ptr)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"GetTrackerSystemsSettings failed: {result}")
            return

        if selected >= count_ptr[0]:
            self.log("WARN", "Selected index out of range")
            return

        # Toggle active state and push back to Core
        systems_array[selected].active = not systems_array[selected].active
        result = lib.CoreSdk_SetTrackerSystemsSettings(systems_array)
        if result != SDKReturnCode.Success:
            self.log("ERROR", f"SetTrackerSystemsSettings failed: {result}")
        else:
            name = ffi.string(systems_array[selected].id).decode('utf-8')
            state = "active" if systems_array[selected].active else "inactive"
            self.log("INFO", f"Tracker system '{name}' set to {state}")

    # ========== CALIBRATION METHODS ==========
    def update_calibration_steps(self, glove_id):
        """Update calibration step information for the current glove"""
        try:
            self.calibration_glove_id = glove_id
            
            # Get number of calibration steps
            args = ffi.new("GloveCalibrationArgs*")
            args.gloveId = glove_id
            num_steps_out = ffi.new("uint32_t*")
            
            result = lib.CoreSdk_GloveCalibrationGetNumberOfSteps(args[0], num_steps_out)
            
            if result != SDKReturnCode.Success or num_steps_out[0] == 0:
                self.number_of_calibration_steps = 0
                self.calibration_step_data = None
                return
            
            self.number_of_calibration_steps = num_steps_out[0]
            
            # Clamp step to valid range
            if self.calibration_step >= self.number_of_calibration_steps:
                self.calibration_step = self.number_of_calibration_steps - 1
            
            # Get current step data
            self.update_current_step_data(glove_id)
            
        except Exception as e:
            self.log("ERROR", f"Error updating calibration steps: {e}")
            self.number_of_calibration_steps = 0
            self.calibration_step_data = None
    
    def update_current_step_data(self, glove_id):
        """Get step data for current calibration step"""
        try:
            step_args = ffi.new("GloveCalibrationStepArgs*")
            step_args.gloveId = glove_id
            step_args.stepIndex = self.calibration_step
            
            step_data = ffi.new("GloveCalibrationStepData*")
            result = lib.CoreSdk_GloveCalibrationGetStepData(step_args[0], step_data)
            
            if result != SDKReturnCode.Success:
                self.calibration_step_data = None
                return
            
            # Extract step data
            try:
                title = ffi.string(step_data.title).decode('utf-8') if step_data.title else ""
                description = ffi.string(step_data.description).decode('utf-8') if step_data.description else ""
            except:
                title = ""
                description = ""
            
            self.calibration_step_data = {
                'title': title,
                'description': description,
                'time': step_data.time
            }
            
        except Exception as e:
            self.log("ERROR", f"Error updating step data: {e}")
            self.calibration_step_data = None
    
    def start_glove_calibration(self):
        """Start glove calibration"""
        glove_id = self.get_calibration_glove_id()
        if glove_id == 0:
            self.calibration_message = "No glove connected"
            return
        
        try:
            # First, get the number of steps for this glove
            args = ffi.new("GloveCalibrationArgs*")
            args.gloveId = glove_id
            num_steps_out = ffi.new("uint32_t*")
            
            result = lib.CoreSdk_GloveCalibrationGetNumberOfSteps(args[0], num_steps_out)
            
            if result != SDKReturnCode.Success or num_steps_out[0] == 0:
                self.calibration_message = "Failed to get calibration steps"
                self.log("ERROR", "Could not get number of calibration steps")
                return
            
            self.number_of_calibration_steps = num_steps_out[0]
            self.calibration_step = 0
            self.calibration_step_data = None
            
            # Now call the start function
            result_out = ffi.new("bool*")
            result = lib.CoreSdk_GloveCalibrationStart(args[0], result_out)
            
            if result == SDKReturnCode.Success and result_out[0]:
                self.calibration_started = True
                self.calibration_message = f"Glove calibration started ({self.number_of_calibration_steps} steps)"
                self.log("INFO", f"Started calibration for glove 0x{glove_id:X} with {self.number_of_calibration_steps} steps")
            else:
                self.calibration_message = "Failed to start calibration"
                self.log("ERROR", f"Failed to start calibration: {result}")
        except Exception as e:
            self.calibration_message = f"Error: {e}"
            self.log("ERROR", f"Calibration start error: {e}")
    
    def cancel_glove_calibration(self):
        """Cancel glove calibration"""
        glove_id = self.get_calibration_glove_id()
        if glove_id == 0:
            self.calibration_message = "No glove connected"
            return
        
        try:
            args = ffi.new("GloveCalibrationArgs*")
            args.gloveId = glove_id
            result_out = ffi.new("bool*")
            
            result = lib.CoreSdk_GloveCalibrationStop(args[0], result_out)
            
            if result == SDKReturnCode.Success and result_out[0]:
                self.calibration_started = False
                self.calibration_step = 0
                self.calibration_step_data = None
                self.number_of_calibration_steps = 0
                self.calibration_message = "Glove calibration cancelled"
                self.log("INFO", f"Cancelled calibration for glove 0x{glove_id:X}")
            else:
                self.calibration_message = "Failed to cancel calibration"
                self.log("ERROR", f"Failed to cancel calibration: {result}")
        except Exception as e:
            self.calibration_message = f"Error: {e}"
            self.log("ERROR", f"Calibration cancel error: {e}")
    
    def finish_glove_calibration(self):
        """Finish glove calibration"""
        glove_id = self.get_calibration_glove_id()
        if glove_id == 0:
            self.calibration_message = "No glove connected"
            return
        
        try:
            args = ffi.new("GloveCalibrationArgs*")
            args.gloveId = glove_id
            result_out = ffi.new("bool*")
            
            result = lib.CoreSdk_GloveCalibrationFinish(args[0], result_out)
            
            if result == SDKReturnCode.Success and result_out[0]:
                self.calibration_started = False
                self.calibration_step = 0
                self.calibration_step_data = None
                self.number_of_calibration_steps = 0
                self.calibration_message = "Glove calibration finished"
                self.log("INFO", f"Finished calibration for glove 0x{glove_id:X}")
            else:
                self.calibration_message = "Failed to finish calibration"
                self.log("ERROR", f"Failed to finish calibration: {result}")
        except Exception as e:
            self.calibration_message = f"Error: {e}"
            self.log("ERROR", f"Calibration finish error: {e}")
    
    def execute_calibration_step(self):
        """Execute current calibration step"""
        glove_id = self.get_calibration_glove_id()
        if glove_id == 0:
            self.calibration_message = "No glove connected"
            return
        
        if self.calibration_in_progress:
            self.calibration_message = "Calibration step already in progress"
            return
        
        try:
            args = ffi.new("GloveCalibrationStepArgs*")
            args.gloveId = glove_id
            args.stepIndex = self.calibration_step
            result_out = ffi.new("bool*")
            
            result = lib.CoreSdk_GloveCalibrationStartStep(args[0], result_out)
            
            if result == SDKReturnCode.Success:
                if result_out[0]:
                    self.calibration_message = f"Step {self.calibration_step} finished"
                    self.log("INFO", f"Completed calibration step {self.calibration_step}")
                else:
                    self.calibration_message = f"Step {self.calibration_step} failed"
                    self.log("WARN", f"Calibration step {self.calibration_step} did not complete")
            else:
                self.calibration_message = f"Error executing step: {result}"
                self.log("ERROR", f"Calibration step error: {result}")
        except Exception as e:
            self.calibration_message = f"Error: {e}"
            self.log("ERROR", f"Calibration step execution error: {e}")
    
    def get_calibration_glove_id(self):
        """Get the glove ID for the current calibration selection"""
        if not self.landscape or self.landscape['user_count'] == 0:
            return 0
        
        users = self.landscape.get('users', [])
        if not users:
            return 0
        
        user = users[0]
        if self.calibrate_left_hand:
            return user.get('leftGloveID', 0)
        else:
            return user.get('rightGloveID', 0)

    def save_glove_calibration(self):
        try:
            glove_id = self.get_calibration_glove_id()
            if glove_id == 0:
                self.log("ERROR", "No glove connected")
                return
            
            size = ffi.new("uint32_t*")
            result = lib.CoreSdk_GetGloveCalibrationSize(glove_id, size)
            if result != SDKReturnCode.Success or size[0] == 0:
                self.log("ERROR", f"Failed to get calibration size: {SDKReturnCode(result).name}")
                return

            calibration_bytes = ffi.new(f"unsigned char [{size[0]}]")
            result = lib.CoreSdk_GetGloveCalibration(calibration_bytes, size[0])
            if result != SDKReturnCode.Success:
                self.log("ERROR", f"Failed to get calibration data: {SDKReturnCode(result).name}")
                return
            
            side = "left" if self.calibrate_left_hand else "right"
            filename = f"{side}_0x{glove_id:0x}.mcal"
            with open(filename, "wb") as f:
                f.write(bytes(ffi.buffer(calibration_bytes, size[0])))
            self.log("INFO", f"Calibration saved: {filename}")

        except Exception as e:
            self.log("ERROR", f"Error saving glove calibration: {e}")

    def load_glove_calibration(self):
        try:
            glove_id = self.get_calibration_glove_id()
            if glove_id == 0:
                self.log("ERROR", "No glove connected")
                return
            
            side = "left" if self.calibrate_left_hand else "right"
            filename = f"{side}_0x{glove_id:0x}.mcal"

            try:
                with open(filename, "rb") as f:
                    data = f.read()
            except FileNotFoundError:
                self.log("ERROR", f"File not found: {filename}")
                return

            calibration_bytes = ffi.new(f"unsigned char[{len(data)}]")
            ffi.memmove(calibration_bytes, data, len(data))

            result_code = ffi.new("SetGloveCalibrationReturnCode*")
            result = lib.CoreSdk_SetGloveCalibration(glove_id, calibration_bytes, len(data), result_code)
            if result == SDKReturnCode.Success:
                self.log("INFO", f"Loaded from {filename}")
            else:
                self.log("ERROR", f"Load failed: {SDKReturnCode(result).name}")

        except Exception as e:
            self.log("ERROR", f"Error loading glove calibration: {e}")
    
    # ========== PAIRING METHODS ==========
    def pair_glove(self):
        """Pair the first available unpaired glove"""
        glove_to_pair_id = None
        
        if not self.landscape:
            self.log("WARN", "No landscape data available")
            return
        
        gloves = self.landscape.get('gloves', [])
        from manus_sdk.generated._enums import DevicePairedState
        
        for glove in gloves:
            try:
                if glove['pairedState'] == DevicePairedState.Unpaired or glove['pairedState'] == 0:
                    glove_to_pair_id = glove['id']
                    break
            except Exception:
                pass
        
        if glove_to_pair_id is None:
            self.log("WARN", "No unpaired glove available for pairing")
            return
        
        try:
            paired_out = ffi.new("bool*")
            result = lib.CoreSdk_PairGlove(glove_to_pair_id, paired_out)
            
            if result == SDKReturnCode.Success and paired_out[0]:
                self.log("INFO", f"Successfully paired glove 0x{glove_to_pair_id:X}")
            else:
                self.log("ERROR", f"Failed to pair glove 0x{glove_to_pair_id:X}")
        except Exception as e:
            self.log("ERROR", f"Pairing error: {e}")
    
    def unpair_glove(self):
        """Unpair the first available paired glove"""
        glove_to_unpair_id = None
        
        if not self.landscape:
            self.log("WARN", "No landscape data available")
            return
        
        gloves = self.landscape.get('gloves', [])
        from manus_sdk.generated._enums import DevicePairedState
        
        for glove in gloves:
            try:
                # Skip dongle-paired gloves (where ID == dongleID)
                if glove['id'] == glove['dongleID']:
                    continue
                
                if glove['pairedState'] == DevicePairedState.Paired or glove['pairedState'] == 1:
                    glove_to_unpair_id = glove['id']
                    break
            except Exception:
                pass
        
        if glove_to_unpair_id is None:
            self.log("WARN", "No paired glove available for unpairing")
            return
        
        try:
            unpaired_out = ffi.new("bool*")
            result = lib.CoreSdk_UnpairGlove(glove_to_unpair_id, unpaired_out)
            
            if result == SDKReturnCode.Success and unpaired_out[0]:
                self.log("INFO", f"Successfully unpaired glove 0x{glove_to_unpair_id:X}")
            else:
                self.log("ERROR", f"Failed to unpair glove 0x{glove_to_unpair_id:X}")
        except Exception as e:
            self.log("ERROR", f"Unpairing error: {e}")
    
    # ========== SKELETON METHODS ==========
    # --8<-- [start:create-node-setup]
    def _create_node_setup(self, node_id, parent_id, x, y, z, name=""):
        """Helper: create and initialize a NodeSetup cdata value and return it (by-value).

        Args:
            node_id: Unique identifier for this node
            parent_id: ID of the parent node in the hierarchy
            x, y, z: Position coordinates
            name: Optional name for the node (UTF-8, up to 64 bytes)

        Returns:
            NodeSetup cdata value with all fields initialized:
            position at (x, y, z), identity rotation, unit scale,
            type Joint and no special settings (IK, Foot, Leaf, etc.)
        """
        from manus_sdk.generated._enums import NodeType, NodeSettingsFlag

        node = ffi.new("NodeSetup*")
        # Manual zero initialization since _Init functions aren't exported
        node.id = node_id
        node.parentID = parent_id
        node.type = NodeType.Joint
        node.settings.usedSettings = NodeSettingsFlag.None_
        node.transform.position.x = x
        node.transform.position.y = y
        node.transform.position.z = z
        node.transform.rotation.w = 1.0
        node.transform.rotation.x = 0.0
        node.transform.rotation.y = 0.0
        node.transform.rotation.z = 0.0
        node.transform.scale.x = 1.0
        node.transform.scale.y = 1.0
        node.transform.scale.z = 1.0
        if name:
            name_bytes = name.encode('utf-8')
            ffi.memmove(node.name, name_bytes, min(len(name_bytes), 64))
        return node[0]
    # --8<-- [end:create-node-setup]

    # --8<-- [start:setup-hand-nodes]
    def _setup_hand_nodes(self, setup_index, side_enum):
        """Create nodes for a simple hand skeleton (root + 5 fingers x 4 joints).

        Args:
            setup_index: Skeleton setup index from CoreSdk_CreateSkeletonSetup
            side_enum: Side.Left or Side.Right

        Returns:
            True if successful, False otherwise

        Node structure:
            Node 0: Hand (root)
            Nodes 1-4: Thumb metacarpal -> distal
            Nodes 5-8: Index metacarpal -> distal
            Nodes 9-12: Middle metacarpal -> distal
            Nodes 13-16: Ring metacarpal -> distal
            Nodes 17-20: Pinky metacarpal -> distal
        """
        # Finger and joint counts
        t_NumFingers = 5
        t_NumJoints = 4

        # Left and right hand node positions
        s_LeftHandPositions = [
            (0.025320, -0.024950, 0.0),
            (0.025320 + 0.032742, -0.024950, 0.0),
            (0.025320 + 0.032742 + 0.028739, -0.024950, 0.0),
            (0.025320 + 0.032742 + 0.028739 + 0.028739, -0.024950, 0.0),

            (0.052904, -0.011181, 0.0),
            (0.052904 + 0.038257, -0.011181, 0.0),
            (0.052904 + 0.038257 + 0.020884, -0.011181, 0.0),
            (0.052904 + 0.038257 + 0.020884 + 0.018759, -0.011181, 0.0),

            (0.051287, 0.0, 0.0),
            (0.051287 + 0.041861, 0.0, 0.0),
            (0.051287 + 0.041861 + 0.024766, 0.0, 0.0),
            (0.051287 + 0.041861 + 0.024766 + 0.019683, 0.0, 0.0),

            (0.049802, 0.011274, 0.0),
            (0.049802 + 0.039736, 0.011274, 0.0),
            (0.049802 + 0.039736 + 0.023564, 0.011274, 0.0),
            (0.049802 + 0.039736 + 0.023564 + 0.019868, 0.011274, 0.0),

            (0.047309, 0.020145, 0.0),
            (0.047309 + 0.033175, 0.020145, 0.0),
            (0.047309 + 0.033175 + 0.018020, 0.020145, 0.0),
            (0.047309 + 0.033175 + 0.018020 + 0.019129, 0.020145, 0.0),
        ]

        s_RightHandPositions = [
            (0.025320, 0.024950, 0.0),
            (0.025320 + 0.032742, 0.024950, 0.0),
            (0.025320 + 0.032742 + 0.028739, 0.024950, 0.0),
            (0.025320 + 0.032742 + 0.028739 + 0.028739, 0.024950, 0.0),

            (0.052904, 0.011181, 0.0),
            (0.052904 + 0.038257, 0.011181, 0.0),
            (0.052904 + 0.038257 + 0.020884, 0.011181, 0.0),
            (0.052904 + 0.038257 + 0.020884 + 0.018759, 0.011181, 0.0),

            (0.051287, 0.0, 0.0),
            (0.051287 + 0.041861, 0.0, 0.0),
            (0.051287 + 0.041861 + 0.024766, 0.0, 0.0),
            (0.051287 + 0.041861 + 0.024766 + 0.019683, 0.0, 0.0),

            (0.049802, -0.011274, 0.0),
            (0.049802 + 0.039736, -0.011274, 0.0),
            (0.049802 + 0.039736 + 0.023564, -0.011274, 0.0),
            (0.049802 + 0.039736 + 0.023564 + 0.019868, -0.011274, 0.0),

            (0.047309, -0.020145, 0.0),
            (0.047309 + 0.033175, -0.020145, 0.0),
            (0.047309 + 0.033175 + 0.018020, -0.020145, 0.0),
            (0.047309 + 0.033175 + 0.018020 + 0.019129, -0.020145, 0.0),
        ]

        from manus_sdk.generated._enums import Side
        fingers = s_LeftHandPositions if side_enum == Side.Left else s_RightHandPositions

        # Add root hand node (ID 0)
        root_node = self._create_node_setup(0, 0, 0.0, 0.0, 0.0, "Hand")
        res = lib.CoreSdk_AddNodeToSkeletonSetup(setup_index, root_node)
        if res != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to add root Hand node to skeleton setup: {res}")
            return False

        # Add finger joints
        finger_id = 0
        for i in range(t_NumFingers):
            parent_id = 0
            for j in range(t_NumJoints):
                idx = i * t_NumJoints + j
                x, y, z = fingers[idx]
                node_id = 1 + finger_id + j
                node = self._create_node_setup(node_id, parent_id, x, y, z, "fingerdigit")
                res = lib.CoreSdk_AddNodeToSkeletonSetup(setup_index, node)
                if res != SDKReturnCode.Success:
                    self.log("ERROR", f"Failed to add finger node to skeleton setup: {res}")
                    return False
                parent_id = node_id
            finger_id += t_NumJoints
        return True
    # --8<-- [end:setup-hand-nodes]

    # --8<-- [start:setup-hand-chains]
    def _setup_hand_chains(self, setup_index, side_enum):
        """Create hand and finger chains for the skeleton (1 hand + 5 finger chains).

        Args:
            setup_index: Skeleton setup index from CoreSdk_CreateSkeletonSetup
            side_enum: Side.Left or Side.Right

        Returns:
            True if successful, False otherwise

        Chain structure:
            Chain 0: Hand (wrist) - contains all finger chain IDs
            Chain 1: Thumb - nodes 1-4
            Chain 2: Index - nodes 5-8
            Chain 3: Middle - nodes 9-12
            Chain 4: Ring - nodes 13-16
            Chain 5: Pinky - nodes 17-20

        Settings:
            - Hand motion: IMU (Inertial Measurement Unit)
            - All finger chains linked to the hand chain
            - Leaf nodes disabled (chains extend to the finger tips)
        """
        from manus_sdk.generated._enums import ChainType, HandMotion

        # Hand chain settings
        cs = ffi.new("ChainSettings*")
        # Manual initialization - set default values
        cs.usedSettings = ChainType.Hand
        cs.hand.handMotion = HandMotion.IMU
        cs.hand.fingerChainIdsUsed = 5
        cs.hand.fingerChainIds[0] = 1
        cs.hand.fingerChainIds[1] = 2
        cs.hand.fingerChainIds[2] = 3
        cs.hand.fingerChainIds[3] = 4
        cs.hand.fingerChainIds[4] = 5

        chain = ffi.new("ChainSetup*")
        # Manual initialization
        chain.id = 0
        chain.type = ChainType.Hand
        chain.dataType = ChainType.Hand
        chain.side = side_enum
        chain.dataIndex = 0
        chain.nodeIdCount = 1
        chain.nodeIds[0] = 0
        chain.settings = cs[0]

        res = lib.CoreSdk_AddChainToSkeletonSetup(setup_index, chain[0])
        if res != SDKReturnCode.Success:
            self.log("ERROR", f"Failed to add Hand chain to skeleton setup: {res}")
            return False

        # Finger chains
        finger_types = [ChainType.FingerThumb, ChainType.FingerIndex, ChainType.FingerMiddle, ChainType.FingerRing, ChainType.FingerPinky]
        for i in range(5):
            cs2 = ffi.new("ChainSettings*")
            # Manual initialization
            cs2.usedSettings = finger_types[i]
            cs2.finger.handChainId = 0
            cs2.finger.metacarpalBoneId = -1
            cs2.finger.useLeafAtEnd = False

            ch = ffi.new("ChainSetup*")
            # Manual initialization
            ch.id = i + 1
            ch.type = finger_types[i]
            ch.dataType = finger_types[i]
            ch.side = side_enum
            ch.dataIndex = 0
            ch.nodeIdCount = 4
            if i == 0:
                ch.nodeIds[0] = 1
                ch.nodeIds[1] = 2
                ch.nodeIds[2] = 3
                ch.nodeIds[3] = 4
            else:
                ch.nodeIds[0] = (i * 4) + 1
                ch.nodeIds[1] = (i * 4) + 2
                ch.nodeIds[2] = (i * 4) + 3
                ch.nodeIds[3] = (i * 4) + 4
            ch.settings = cs2[0]

            res = lib.CoreSdk_AddChainToSkeletonSetup(setup_index, ch[0])
            if res != SDKReturnCode.Success:
                self.log("ERROR", f"Failed to add finger chain to skeleton setup: {res}")
                return False

        return True
    # --8<-- [end:setup-hand-chains]

    # --8<-- [start:load-test-skeleton]
    def load_test_skeleton(self, side):
        """Load a test skeleton for the specified side (left or right).

        Creates a fully configured hand skeleton matching the C++ SDK sample:
        - 1 root hand node
        - 20 finger joint nodes (5 fingers x 4 joints)
        - 6 chains (1 hand chain + 5 finger chains)

        Nodes and chains are created before loading the skeleton so callbacks
        will see a fully populated hand skeleton.

        Args:
            side: 'left' or 'right' to specify which hand to load

        After loading, the skeleton will:
        - Generate skeleton callbacks with animation data
        - Be visible in the Skeleton Data view
        - Be animated by connected glove data
        - Keep streaming until unload_test_skeleton() is called
        """
        try:
            from manus_sdk.generated._enums import SkeletonType, SkeletonTargetType, Side

            # Determine which side
            side_enum = Side.Left if side == 'left' else Side.Right
            side_name = "Left" if side == 'left' else "Right"

            # Create skeleton setup
            setup = ffi.new("SkeletonSetupInfo*")
            # Manual initialization - zero out and set defaults
            setup.type = SkeletonType.Hand
            setup.settings.scaleToTarget = True
            setup.settings.useEndPointApproximations = True
            setup.settings.targetType = SkeletonTargetType.UserIndexData
            setup.settings.skeletonTargetUserIndexData.userIndex = 0            # Set skeleton name
            name = f"{side_name}Hand"
            name_bytes = name.encode('utf-8')
            ffi.memmove(setup.name, name_bytes, min(len(name_bytes), 64))

            # Create skeleton setup
            setup_index_out = ffi.new("uint32_t*")
            result = lib.CoreSdk_CreateSkeletonSetup(setup[0], setup_index_out)

            if result != SDKReturnCode.Success:
                self.log("ERROR", f"Failed to create skeleton setup: {result}")
                return

            setup_index = setup_index_out[0]
            self.temporary_skeletons.append(setup_index)

            # Add nodes and chains for a hand skeleton
            # Note: functions return False on failure and will cleanup the temporary list below
            from manus_sdk.generated._enums import Side as _SideEnum
            if not self._setup_hand_nodes(setup_index, side_enum):
                if setup_index in self.temporary_skeletons:
                    self.temporary_skeletons.remove(setup_index)
                return

            if not self._setup_hand_chains(setup_index, side_enum):
                if setup_index in self.temporary_skeletons:
                    self.temporary_skeletons.remove(setup_index)
                return

            # Load the skeleton
            skeleton_id_out = ffi.new("uint32_t*")
            result = lib.CoreSdk_LoadSkeleton(setup_index, skeleton_id_out)

            if result != SDKReturnCode.Success:
                self.log("ERROR", f"Failed to load skeleton: {result}")
                if setup_index in self.temporary_skeletons:
                    self.temporary_skeletons.remove(setup_index)
                return

            skeleton_id = skeleton_id_out[0]
            if skeleton_id == 0:
                self.log("ERROR", "Failed to assign skeleton ID")
                if setup_index in self.temporary_skeletons:
                    self.temporary_skeletons.remove(setup_index)
                return

            # Build skeleton metadata by reading chains from setup
            try:
                from manus_sdk.generated._enums import ChainType
                
                # Get the number of chains in the setup
                setup_sizes = ffi.new("SkeletonSetupArraySizes*")
                result = lib.CoreSdk_GetSkeletonSetupArraySizes(setup_index, setup_sizes)
                
                if result == SDKReturnCode.Success and setup_sizes.chainsCount > 0:
                    # Allocate array for chains
                    chains_array = ffi.new("ChainSetup[]", setup_sizes.chainsCount)
                    result = lib.CoreSdk_GetSkeletonSetupChainsArray(setup_index, chains_array, setup_sizes.chainsCount)
                    
                    if result == SDKReturnCode.Success:
                        # Build node -> chain_type mapping
                        node_to_chain = {}
                        for chain_idx in range(setup_sizes.chainsCount):
                            chain = chains_array[chain_idx]
                            chain_type = chain.type
                            side = chain.side
                            
                            # Add each node in this chain to the mapping
                            for node_idx in range(chain.nodeIdCount):
                                node_id = chain.nodeIds[node_idx]
                                node_to_chain[node_id] = {
                                    'chain_type': chain_type,
                                    'side': side,
                                    'node_id': node_id,
                                    'parent_id': 0,  # We'd need to look this up from NodeSetup if needed
                                    'finger_joint_type': 0  # Default, would need to look up if needed
                                }
                        
                        # Store the metadata for this skeleton
                        self.skeleton_metadata[skeleton_id] = node_to_chain
            except Exception as e:
                self.log("WARN", f"Could not build skeleton metadata: {e}")

            self.loaded_skeletons.append(skeleton_id)
            self.log("INFO", f"Loaded {side_name} hand skeleton (ID: {skeleton_id})")

        except Exception as e:
            self.log("ERROR", f"Error loading skeleton: {e}")
    # --8<-- [end:load-test-skeleton]
    
    # --8<-- [start:unload-test-skeleton]
    def unload_test_skeleton(self):
        """Unload the first loaded skeleton from the system.

        Removes the skeleton from the animation pipeline and cleans up:
        - Skeleton data streaming
        - Internal metadata cache
        - Resources allocated by the SDK

        After calling this, no more skeleton callbacks are received for this
        skeleton and the Skeleton Data view will be empty.
        """
        if not self.loaded_skeletons:
            self.log("WARN", "No loaded skeleton to unload")
            return
        
        try:
            skeleton_id = self.loaded_skeletons[0]
            result = lib.CoreSdk_UnloadSkeleton(skeleton_id)
            
            if result == SDKReturnCode.Success:
                self.loaded_skeletons.pop(0)
                # Clean up metadata
                if skeleton_id in self.skeleton_metadata:
                    del self.skeleton_metadata[skeleton_id]
                self.log("INFO", f"Unloaded skeleton (ID: {skeleton_id})")
            else:
                self.log("ERROR", f"Failed to unload skeleton: {result}")
        except Exception as e:
            self.log("ERROR", f"Error unloading skeleton: {e}")
    # --8<-- [end:unload-test-skeleton]
    
    def clear_screen(self):
        """Clear the console screen - use sparingly as it causes flicker"""
        os.system('cls' if os.name == 'nt' else 'clear')
    def smart_clear(self):
        """Clear screen intelligently with frame rate limiting to reduce flicker"""
        current_time = time.time()
        
        # Check if enough time has passed since last display update
        if current_time - self.last_display_time >= self.min_display_interval:
            self.clear_screen()
            self.last_display_time = current_time
            return True  # Display was cleared, should redraw
        
        return False  # Not time to redraw yet, skip this frame
    
    def reset_cursor(self):
        """Move cursor to top-left without clearing (reduces flicker)"""
        # Use ANSI escape codes to move cursor to home position
        # Enable ANSI support on Windows 10+
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        print('\033[H', end='')
    
    def clear_line_to_end(self):
        """Clear from cursor to end of line"""
        print('\033[K', end='')
    
    def redraw_display(self):
        """Redraw the current display with minimal flicker"""
        # Move cursor to top instead of clearing entire screen
        self.reset_cursor()
        
        # Display current menu or main menu
        if self.current_menu:
            self.current_menu()
        else:
            self.display_main_menu()
    
    def has_input(self):
        """Check if input is available (non-blocking, cross-platform)"""
        if os.name == 'nt':
            # Windows: use msvcrt
            import msvcrt
            return msvcrt.kbhit()
        else:
            # Unix/Linux/Mac: use select
            try:
                return select.select([sys.stdin], [], [], 0)[0] != []
            except:
                return False
    
    def get_char(self):
        """Get a single character from input (non-blocking, cross-platform)"""
        if os.name == 'nt':
            # Windows: use msvcrt for non-blocking single char read
            import msvcrt
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                # Handle special keys
                if ch in (b'\x00', b'\xe0'):
                    msvcrt.getch()  # Skip second byte of special key
                    return None
                try:
                    return ch.decode('utf-8').upper()
                except:
                    return None
        else:
            # Unix/Linux/Mac: read single char from stdin
            # Terminal is already in raw mode from __init__
            if self.has_input():
                try:
                    ch = sys.stdin.read(1).upper()
                    return ch
                except:
                    return None
        return None
    
    def shutdown(self):
        """Shutdown the SDK"""
        # Restore terminal settings on Unix
        if os.name != 'nt' and self.old_terminal_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_terminal_settings)
            except:
                pass
        
        print("\nShutting down SDK...")
        result = lib.CoreSdk_ShutDown()
        if result == SDKReturnCode.Success:
            print("SDK shutdown successfully!")
        else:
            print(f"Failed to shutdown: {result}")


def main():
    """Main entry point"""
    client = SDKClient()
    
    if not client.initialize():
        return 1
    
    try:
        client.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        client.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
