"""
Python implementation of SDKMinimalClient
Demonstrates basic usage of the Manus SDK with minimal wrapper (direct CFFI calls)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import threading
import select
from typing import Optional, List

# Unix-specific imports for terminal control
if os.name != 'nt':
    import tty
    import termios

# Import CFFI directly and minimal wrapper for callbacks
from manus_sdk import lib, ffi, ManusSDK
from manus_sdk.generated._enums import SDKReturnCode, AxisView, AxisPolarity, Side, HandMotion
from enum import IntEnum


# Simple connection type enum for client (not in SDK)
class ConnectionType(IntEnum):
    Invalid = 0
    Local = 1
    Remote = 2
    Integrated = 3



class ClientRawSkeleton:
    """Client raw skeleton data - simple container"""
    def __init__(self):
        self.info = None  # CFFI cdata
        self.nodes = []   # List of CFFI cdata


class SDKMinimalClient:
    """Minimal Python client for Manus SDK"""
    
    def __init__(self):
        self.sdk = ManusSDK()
        self.connection_type = ConnectionType.Invalid
        self.running = True
        self.printed_node_info = False
        self.frame_counter = 0
        
        # Thread-safe skeleton data
        self.skeleton_mutex = threading.Lock()
        self.next_raw_skeleton: Optional[List[ClientRawSkeleton]] = None
        self.raw_skeleton: Optional[List[ClientRawSkeleton]] = None
    
    def has_input(self) -> bool:
        """Check if input is available (non-blocking, cross-platform)"""
        if os.name == 'nt':
            # Windows: use msvcrt
            import msvcrt
            return msvcrt.kbhit()
        else:
            # Unix/Linux/Mac: use select
            try:
                return select.select([sys.stdin], [], [], 0)[0] != []
            except (OSError, ValueError):
                return False
    
    def get_key(self) -> Optional[str]:
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
                except UnicodeDecodeError:
                    return None
        else:
            # Unix/Linux/Mac: read single char from stdin
            # Terminal must already be in cbreak mode (see run()), otherwise
            # select() only reports input after Enter is pressed.
            if self.has_input():
                try:
                    return sys.stdin.read(1).upper()
                except (OSError, ValueError):
                    return None
        return None

    def initialize(self) -> bool:
        """Initialize the SDK client"""
        print("Starting minimal client!")
        
        if not self.initialize_sdk():
            print("Failed to initialize the SDK. Are you sure the correct ManusSDK library is available?")
            return False
        
        print("Minimal client is initialized.")
        return True

    # --8<-- [start:initialize-sdk]
    def initialize_sdk(self) -> bool:
        """Initialize the SDK and set up connection"""
        # Ask user for connection type
        print("Select what mode you would like to start in (and press enter to submit)")
        print("[1] Core Integrated - This will run standalone without the need for a MANUS Core connection")
        print("[2] Core Local - This will connect to a MANUS Core running locally on your machine")
        print("[3] Core Remote - This will search for a MANUS Core running locally on your network")
        
        choice = input("Enter choice: ").strip()
        
        if choice == '1':
            self.connection_type = ConnectionType.Integrated
        elif choice == '2':
            self.connection_type = ConnectionType.Local
        elif choice == '3':
            self.connection_type = ConnectionType.Remote
        else:
            print("Invalid input, try again")
            return self.initialize_sdk()
        
        # Initialize the SDK - Direct CFFI call
        if self.connection_type == ConnectionType.Integrated:
            result = lib.CoreSdk_InitializeIntegrated()
        else:
            result = lib.CoreSdk_InitializeCore()
        
        if result != SDKReturnCode.Success:
            print(f"Failed to initialize SDK: {SDKReturnCode(result).name}")
            return False
        
        # Register callbacks (use wrapper for this)
        if not self.register_all_callbacks():
            return False
        
        # --8<-- [start:coordinate-system]
        # Set up coordinate system - Direct CFFI call
        coord_system = ffi.new("CoordinateSystemVUH*")
        coord_system.view = AxisView.XFromViewer
        coord_system.up = AxisPolarity.PositiveZ
        coord_system.handedness = Side.Right
        coord_system.unitScale = 1.0
        
        result = lib.CoreSdk_InitializeCoordinateSystemWithVUH(coord_system[0], True)
        
        if result != SDKReturnCode.Success:
            print(f"Failed to initialize coordinate system: {SDKReturnCode(result).name}")
            return False
        # --8<-- [end:coordinate-system]
        
        return True
    # --8<-- [end:initialize-sdk]

    # --8<-- [start:register-callbacks]
    def register_all_callbacks(self) -> bool:
        """Register SDK callbacks"""
        # Register raw skeleton stream callback (use wrapper)
        result = self.sdk.register_raw_skeleton_callback(self.on_raw_skeleton_stream_callback)

        if result != SDKReturnCode.Success:
            print(f"Failed to register raw skeleton callback: {SDKReturnCode(result).name}")
            return False

        return True
    # --8<-- [end:register-callbacks]

    # --8<-- [start:run]
    def run(self):
        """Main loop"""
        # First connect to Core
        if self.connection_type == ConnectionType.Integrated:
            print("Minimal client is running in integrated mode.")
        else:
            print("Minimal client is connecting to MANUS Core. (make sure it is running)")
        
        # Try to connect
        while not self.connect():
            print("Minimal client could not connect. Trying again in a second.")
            time.sleep(1.0)
        
        if self.connection_type != ConnectionType.Integrated:
            print("Minimal client is connected, setting up skeletons.")
        
        # Set hand motion mode - Direct CFFI call
        result = lib.CoreSdk_SetRawSkeletonHandMotion(HandMotion.Auto)
        if result != SDKReturnCode.Success:
            print(f"Failed to set hand motion mode: {SDKReturnCode(result).name}")
        
        print("Press SPACE to exit...")

        # Unix: switch the terminal to cbreak mode for the duration of the main
        # loop so single keypresses are visible to select() without Enter.
        old_terminal_settings = None
        keyboard_available = True
        if os.name != 'nt':
            try:
                old_terminal_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except termios.error as e:
                # Without cbreak the terminal stays line-buffered and SPACE can
                # never be detected - say so instead of silently not working.
                keyboard_available = False
                print(f"Warning: could not enable single-key input ({e}). "
                      "Is stdin a terminal? Press Ctrl+C to exit instead.")

        try:
            # Main loop
            while self.running:
                # Check for new skeleton data
                with self.skeleton_mutex:
                    if self.next_raw_skeleton is not None:
                        self.raw_skeleton = self.next_raw_skeleton
                        self.next_raw_skeleton = None

                # Process skeleton data
                if self.raw_skeleton and len(self.raw_skeleton) > 0:
                    print(f"Raw skeleton data obtained for frame: {self.frame_counter}")
                    self.print_raw_skeleton_node_info()
                    self.frame_counter += 1

                # Sleep ~30 FPS
                time.sleep(0.033)

                # Check for space key press (cross-platform)
                if keyboard_available:
                    key = self.get_key()
                    if key == ' ':
                        self.running = False
        finally:
            # Restore terminal settings on Unix
            if old_terminal_settings is not None:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_terminal_settings)
                except termios.error as e:
                    print(f"Warning: failed to restore terminal settings: {e}")
    # --8<-- [end:run]

    # --8<-- [start:connect]
    def connect(self) -> bool:
        """Connect to Manus Core"""
        loopback_only = self.connection_type == ConnectionType.Local
        
        # Look for hosts - Direct CFFI call
        result = lib.CoreSdk_LookForHosts(1, loopback_only)
        if result != SDKReturnCode.Success:
            return False
        
        # Get number of hosts - Direct CFFI call
        count = ffi.new("uint32_t*")
        result = lib.CoreSdk_GetNumberOfAvailableHostsFound(count)
        num_hosts = count[0]
        if result != SDKReturnCode.Success or num_hosts == 0:
            return False
        
        # Get host list - Direct CFFI call
        hosts_array = ffi.new("ManusHost[]", num_hosts)
        result = lib.CoreSdk_GetAvailableHostsFound(hosts_array, num_hosts)
        if result != SDKReturnCode.Success:
            return False
        
        # Select host
        host_selection = 0
        if not loopback_only and num_hosts > 1:
            print("Select which host you want to connect to (and press enter to submit)")
            for i in range(num_hosts):
                host = hosts_array[i]
                host_name = ffi.string(host.hostName).decode('utf-8')
                ip = ffi.string(host.ipAddress).decode('utf-8')
                print(f"[{i+1}] {host_name} ({ip})")
            
            try:
                choice = int(input("Enter choice: "))
                if choice < 1 or choice > num_hosts:
                    return False
                host_selection = choice - 1
            except ValueError:
                return False
        
        # Connect to selected host - Direct CFFI call
        result = lib.CoreSdk_ConnectToHost(hosts_array[host_selection])
        return result == SDKReturnCode.Success
    # --8<-- [end:connect]

    # --8<-- [start:print-node-info]
    def print_raw_skeleton_node_info(self):
        """Print skeleton node information"""
        if not self.raw_skeleton or len(self.raw_skeleton) == 0:
            return
        
        skeleton = self.raw_skeleton[0]
        
        # Print first node position and rotation
        if skeleton.nodes and len(skeleton.nodes) > 0:
            node = skeleton.nodes[0]
            pos = node.transform.position
            rot = node.transform.rotation
            print(f"  Node 0 Position: x={pos.x:.3f} y={pos.y:.3f} z={pos.z:.3f} "
                  f"Rotation: x={rot.x:.3f} y={rot.y:.3f} z={rot.z:.3f} w={rot.w:.3f}")
        
        # Print node info once
        if not self.printed_node_info and skeleton.info:
            glove_id = skeleton.info.gloveId  # Use C field name
            node_count = skeleton.info.nodesCount  # Use C field name
            
            # Get node info array - Direct CFFI call
            node_info_array = ffi.new("NodeInfo[]", node_count)
            result = lib.CoreSdk_GetRawSkeletonNodeInfoArray(glove_id, node_info_array, node_count)
            
            if result == SDKReturnCode.Success:
                print(f"\nReceived Skeleton glove data from Core.")
                print(f"Skeletons: {len(self.raw_skeleton)}, First skeleton glove id: {glove_id}")
                print("Printing Node Info:")
                
                for i in range(node_count):
                    node_info = node_info_array[i]
                    # NodeInfo fields: nodeId, parentId, side, chainType, fingerJointType
                    print(f"  Node {node_info.nodeId}: parent={node_info.parentId}, side={node_info.side}")
                
                self.printed_node_info = True
    # --8<-- [end:print-node-info]

    # --8<-- [start:raw-skeleton-callback]
    def on_raw_skeleton_stream_callback(self, stream_info):
        """Callback for raw skeleton stream data"""
        try:
            skeletons_count = stream_info.skeletonsCount
            publish_time = stream_info.publishTime
            
            new_skeletons = []
            
            for i in range(skeletons_count):
                # Get skeleton info - Direct CFFI call
                info = ffi.new("RawSkeletonInfo*")
                result = lib.CoreSdk_GetRawSkeletonInfo(i, info)
                if result != SDKReturnCode.Success:
                    continue
                
                # Get skeleton data - Direct CFFI call using C field names
                nodes_array = ffi.new("SkeletonNode[]", info.nodesCount)
                result = lib.CoreSdk_GetRawSkeletonData(i, nodes_array, info.nodesCount)
                if result != SDKReturnCode.Success:
                    continue
                
                # Create skeleton object
                skeleton = ClientRawSkeleton()
                skeleton.info = info[0]  # Dereference pointer
                skeleton.info.publishTime = publish_time  # Use C field name
                skeleton.nodes = [nodes_array[j] for j in range(info.nodesCount)]
                
                new_skeletons.append(skeleton)
            
            # Store new skeleton data (thread-safe)
            with self.skeleton_mutex:
                self.next_raw_skeleton = new_skeletons
                
        except Exception as e:
            print(f"Error in skeleton callback: {e}")
    # --8<-- [end:raw-skeleton-callback]

    def shutdown(self):
        """Shutdown the client"""
        print("Minimal client is done, shutting down.")
        result = lib.CoreSdk_ShutDown()
        if result != SDKReturnCode.Success:
            print(f"Failed to shutdown SDK: {result.name}")


def main():
    """Main entry point"""
    client = SDKMinimalClient()
    
    if not client.initialize():
        return -1
    
    try:
        client.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        client.shutdown()
    
    return 0


if __name__ == "__main__":
    exit(main())
