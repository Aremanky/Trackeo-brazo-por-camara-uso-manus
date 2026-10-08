#define NUM_FINGERS_ON_HAND 5
#define NUM_FLEX_SEGMENTS_PER_FINGER 2
#define MAX_NUM_IMUS_ON_GLOVE 6
#define MAX_USERS 16
#define MAX_NUM_CHARS_IN_USERNAME 64
#define MAX_NUM_CHARS_IN_MEASUREMENT 64
#define MAX_NUM_CHARS_IN_HOST_NAME 256
#define MAX_NUM_CHARS_IN_IP_ADDRESS 40
#define MAX_NUM_CHARS_IN_TRACKER_ID 256
#define MAX_NUM_CHARS_IN_TRACKER_MANUFACTURER 256
#define MAX_NUM_CHARS_IN_TRACKER_PRODUCTNAME 256
#define MAX_NUM_SETTINGS_IN_TRACKERS 4
#define MAX_NUM_TRACKER_SYSTEMS 6
#define MAX_NUM_CHARS_IN_TRACKERSYSTEM 64
#define MAX_NUM_CHARS_IN_TRACKERSYSTEM_FILE_PATH 256
#define MAX_NUM_CHARS_IN_TRACKERSYSTEM_FILE_EXTENSION 16
#define MAX_NUM_CHARS_IN_TARGET_ID 256
#define MAX_NUM_CHARS_IN_VERSION 16
#define UNINITIALIZED_ID 0
#define MAX_NUMBER_OF_HOSTS 100
#define MAX_NUMBER_OF_DONGLES 16
#define MAX_NUM_CHARS_IN_LICENSE_TYPE 64
#define MAX_NUM_CHARS_IN_CALIBRATION_TITLE 64
#define MAX_NUM_CHARS_IN_CALIBRATION_DESCRIPTION 256
#define MAX_NUM_CHARS_IN_CALIBRATION_FILE 65536
#define MAX_NUMBER_OF_GLOVES 32
#define MAX_NUMBER_OF_HAPTICS_DONGLES 16
#define MAX_NUMBER_OF_SKELETONS 32
#define MAX_NUMBER_OF_USERS 16
#define NUMBER_OF_TRACKERS_PER_POLYGON_SKELETON 8
#define MAX_NUMBER_OF_TRACKERS 128
#define MAX_NUM_CHARS_IN_NODE_NAME 256
#define MAX_CHAIN_LENGTH 32
#define MAX_NUM_FINGER_IDS 10
#define MAX_NUM_TOE_IDS 10
#define MAX_NUM_CHARS_IN_SYSTEM_ERROR_MESSAGE 256
#define MAX_NUM_CHAR_DEBUGGING_ID 64
#define MAX_NUMBER_OF_ERGONOMICS_DATA 32
#define MAX_RAW_DEVICE_DATA_SENSOR_SIZE 5
#define MAX_NUMBER_OF_SESSIONS 8
#define MAX_NUMBER_OF_SKELETONS_PER_SESSION 32
#define MAX_NUM_CHARS_IN_SKELETON_NAME 256
#define MAX_NUM_CHARS_IN_TIMECODE_INTERFACE_STRINGS 64
#define MAX_NUMBER_OF_AUDIO_INTERFACES 32
#define MAX_BONE_WEIGHTS_PER_VERTEX 4
#define MAX_NUMBER_OF_NODES_PER_ESTIMATION_SKELETON 40
#define MAX_GESTURE_DATA_CHUNK_SIZE 64
#define MAX_NUM_CHARS_IN_OPENXR_FEATURE_STRING 64
#define MAX_NUMBER_OF_NETDEVICES 16
#define MAX_NUM_CHARS_IN_LICENSE 4096
#define MAX_NUM_CHARS_IN_MESSAGE 256
#define SECONDS_TO_FIND_HOSTS 2
#define SECONDS_TO_FIND_LOCAL_HOSTS 2
#define DEFAULT_BUFFER_SIZE 512
typedef enum SDKReturnCode
{
	/// No issues occurred.
	SDKReturnCode_Success,

	/// Something went wrong, but no specific reason can be given.
	SDKReturnCode_Error,

	/// One of the arguments given had an invalid value.
	SDKReturnCode_InvalidArgument,

	/// The size of an argument given (e.g. an array) does not match the size
	/// of the data that it is intended to hold.
	SDKReturnCode_ArgumentSizeMismatch,

	/// A string of an unsupported size was encountered.
	SDKReturnCode_UnsupportedStringSizeEncountered,

	/// The Core SDK is not available.
	SDKReturnCode_SdkNotAvailable,

	/// The network host finder is not available.
	SDKReturnCode_HostFinderNotAvailable,

	/// The data requested is not available.
	SDKReturnCode_DataNotAvailable,

	/// Failed to allocate memory for something.
	SDKReturnCode_MemoryError,

	/// Something went wrong in the SDK internally.
	SDKReturnCode_InternalError,

	/// The function was not intended to be called at this time.
	SDKReturnCode_FunctionCalledAtWrongTime,

	/// No connection to Core was made.
	SDKReturnCode_NotConnected,

	/// The connection with Core timed out.
	SDKReturnCode_ConnectionTimeout,

	/// using an uninitialized ID is bad.
	SDKReturnCode_InvalidID,

	/// memory unallocated or just a null pointer passed where it wasn't supposed to be!
	SDKReturnCode_NullPointer,

	/// null sequence type for polygon calibration
	SDKReturnCode_InvalidSequence,

	/// don't forget to set the coordinate system type or there will be trouble
	SDKReturnCode_NoCoordinateSystemSet,

	/// if everything is being terminated. don't restart
	SDKReturnCode_SdkIsTerminating,

	/// the stub has been reset but someone is tryign to use it anyway. usually after a shutdown of the SDK.
	SDKReturnCode_StubNullPointer,

	/// Skeleton could not be loaded. usually when using more then the max skeletons per session (32).
	SDKReturnCode_SkeletonNotLoaded,
	
	/// Function not available for this version of the SDK
	SDKReturnCode_FunctionNotAvailable,

	SDKReturnCode_MAX_SIZE
} SDKReturnCode;
typedef enum LogSeverity
{
	LogSeverity_Debug,
	LogSeverity_Info,
	LogSeverity_Warn,
	LogSeverity_Error
} LogSeverity;
typedef enum SessionType
{
	SessionType_Unknown,
	SessionType_UnityPlugin,
	SessionType_UnrealPlugin,
	SessionType_CoreSDK
} SessionType;
typedef enum TrackerType
{
	TrackerType_Unknown,
	TrackerType_Head,
	TrackerType_Waist,
	TrackerType_LeftHand,
	TrackerType_RightHand,
	TrackerType_LeftFoot,
	TrackerType_RightFoot,
	TrackerType_LeftUpperArm,
	TrackerType_RightUpperArm,
	TrackerType_LeftUpperLeg,
	TrackerType_RightUpperLeg,
	TrackerType_Controller,
	TrackerType_Camera,

	TrackerType_MAX_SIZE
} TrackerType;
typedef enum TrackingQuality
{
	TrackingQuality_Untrackable,
	TrackingQuality_BadTracking,
	TrackingQuality_Trackable,
} TrackingQuality;
typedef enum TrackerSystemType
{
	TrackerSystemType_Unknown,
	TrackerSystemType_Antilatency,
	TrackerSystemType_ART,
	TrackerSystemType_OpenVR,
	TrackerSystemType_Optitrack,
	TrackerSystemType_Vicon,
	TrackerSystemType_OpenXR,
	
} TrackerSystemType;
typedef enum TrackerSystemSettingType
{
	TrackerSystemSettingType_Undefined,
	TrackerSystemSettingType_SettingInt,
	TrackerSystemSettingType_SettingFile,
	TrackerSystemSettingType_SettingBool,
	TrackerSystemSettingType_SettingIp,

	TrackerSystemSettingType_MAX_SIZE
} TrackerSystemSettingType;
typedef enum TrackedPoint
{
	TrackedPoint_Unknown,
	TrackedPoint_Casing,
	TrackedPoint_Joint
} TrackedPoint;
typedef enum DevicePairedState
{
	DevicePairedState_Unknown,
	DevicePairedState_Paired,
	DevicePairedState_Unpaired,
	DevicePairedState_Pairing,
} DevicePairedState;
typedef enum DeviceClassType
{
	DeviceClassType_Unknown,
	DeviceClassType_Dongle,
	DeviceClassType_Glove,
	DeviceClassType_Glongle
} DeviceClassType;
typedef enum DeviceFamilyType
{
	DeviceFamilyType_Unknown,
	DeviceFamilyType_Prime1,
	DeviceFamilyType_Prime2,
	DeviceFamilyType_PrimeX,
	DeviceFamilyType_Metaglove,
	DeviceFamilyType_Prime3,
	DeviceFamilyType_Virtual,
	DeviceFamilyType_MetaglovePro,
	DeviceFamilyType_MetagloveProPrecision,
	DeviceFamilyType_MetagloveProHaptics,
	DeviceFamilyType_MetagloveProPrecisionHaptics,
	DeviceFamilyType_MetagloveAir,
	DeviceFamilyType_MetagloveAirHaptic,
	DeviceFamilyType_MetagloveTopModule
} DeviceFamilyType;
typedef enum ProfileType
{
	ProfileType_Hands,
	ProfileType_FullBody,

	ProfileType_MAX_SIZE
} ProfileType;
typedef enum GloveProfileType
{
	GloveProfileType_Invalid,
	GloveProfileType_Metaglove,
	GloveProfileType_MetaglovePro,
} GloveProfileType;
typedef enum MeasurementType
{
	MeasurementType_Unknown,
	MeasurementType_PlayerHeight,
	MeasurementType_SpineLength,
	MeasurementType_NeckLength,
	MeasurementType_UpperArmLength,
	MeasurementType_LowerArmLength,
	MeasurementType_ArmLength,
	MeasurementType_ArmSpan,
	MeasurementType_UpperLegLength,
	MeasurementType_LowerLegLength,
	MeasurementType_LegLength,
	MeasurementType_HandLength,
	MeasurementType_FootLength,
	MeasurementType_HipWidth,
	MeasurementType_ShoulderWidth,
	MeasurementType_ShoulderHeight,
	MeasurementType_HeadLength,
	MeasurementType_Thickness,
	MeasurementType_ArmRatio,
	MeasurementType_LegRatio,

	MeasurementType_MAX_SIZE 
} MeasurementType;
typedef enum TrackerOffsetType
{
	TrackerOffsetType_Unknown,
	TrackerOffsetType_HeadTrackerToHead,
	TrackerOffsetType_HeadTrackerToTopOfHead,

	TrackerOffsetType_LeftHandTrackerToWrist,
	TrackerOffsetType_RightHandTrackerToWrist,
	TrackerOffsetType_LeftFootTrackerToAnkle,
	TrackerOffsetType_RightFootTrackerToAnkle,

	TrackerOffsetType_HipTrackerToHip,
	TrackerOffsetType_HipTrackerToLeftLeg,
	TrackerOffsetType_HipTrackerToRightLeg,

	TrackerOffsetType_LeftUpperArmTrackerToElbow,
	TrackerOffsetType_RightUpperArmTrackerToElbow,
	TrackerOffsetType_LeftUpperArmTrackerToShoulder,
	TrackerOffsetType_RightUpperArmTrackerToShoulder,

	TrackerOffsetType_LeftHandTrackerToCasing,
	TrackerOffsetType_RightHandTrackerToCasing,

	TrackerOffsetType_MAX_SIZE 
} TrackerOffsetType;
typedef enum ExtraTrackerOffsetType
{
	ExtraTrackerOffsetType_Unknown,
	ExtraTrackerOffsetType_HeadForward,
	ExtraTrackerOffsetType_HipForward,
	ExtraTrackerOffsetType_HipHeight,
	ExtraTrackerOffsetType_MAX_SIZE 
} ExtraTrackerOffsetType;
typedef enum MeasurementUnit
{
	MeasurementUnit_Meters,
	MeasurementUnit_Percentage,
} MeasurementUnit;
typedef enum MeasurementCategory
{
	MeasurementCategory_Misc,
	MeasurementCategory_Generic,
	MeasurementCategory_Arms,
	MeasurementCategory_Legs,
	MeasurementCategory_Body,
} MeasurementCategory;
typedef enum UpdateStatusEnum
{
	UpdateStatusEnum_Unknown,
	UpdateStatusEnum_NoUpdateAvailable,
	UpdateStatusEnum_UpdateAvailable,
	UpdateStatusEnum_MandatoryUpdateAvailable,
	UpdateStatusEnum_UpdatingInitializing,
	UpdateStatusEnum_UpdatingBootloader,
	UpdateStatusEnum_UpdatingFirmware,
	UpdateStatusEnum_UpdatingFinalizing,
	UpdateStatusEnum_UpdatingFailed,
	UpdateStatusEnum_UpdatingRestartRequired,
	UpdateStatusEnum_UpdatingTimedOut,
} UpdateStatusEnum;
typedef enum SkeletonType
{
	SkeletonType_Invalid,
	SkeletonType_Hand,
	SkeletonType_Body,
	SkeletonType_Both
} SkeletonType;
typedef enum SkeletonTargetType
{
	SkeletonTargetType_Invalid,
	SkeletonTargetType_UserData,
	SkeletonTargetType_UserIndexData,
	SkeletonTargetType_AnimationData,
	SkeletonTargetType_GloveData
} SkeletonTargetType;
typedef enum NodeType
{
	NodeType_Invalid,
	NodeType_Joint,
	NodeType_Mesh,
	NodeType_Leaf,
	NodeType_Collider
} NodeType;
typedef enum NodeSettingsFlag
{
	NodeSettingsFlag_None = 0,
	NodeSettingsFlag_IK = 1 << 0,
	NodeSettingsFlag_Foot = 1 << 1,
	NodeSettingsFlag_RotationOffset = 1 << 2,
	NodeSettingsFlag_Leaf = 1 << 3,
} NodeSettingsFlag;
typedef enum ChainType
{
	ChainType_Invalid,
	ChainType_Arm,
	ChainType_Leg,
	ChainType_Neck,
	ChainType_Spine,
	ChainType_FingerThumb,
	ChainType_FingerIndex,
	ChainType_FingerMiddle,
	ChainType_FingerRing,
	ChainType_FingerPinky,
	ChainType_Pelvis,
	ChainType_Head,
	ChainType_Shoulder,
	ChainType_Hand,
	ChainType_Foot,
	ChainType_Toe
} ChainType;
typedef enum CollisionType
{
	CollisionType_None,
	CollisionType_Discrete,
	CollisionType_Continuous,
} CollisionType;
typedef enum ColliderType
{
	ColliderType_Invalid,
	ColliderType_Sphere,
	ColliderType_Capsule,
	ColliderType_Box,
} ColliderType;
typedef enum Side
{
	Side_Invalid,
	Side_Left,
	Side_Right,
	Side_Center
} Side;
typedef enum HandMotion
{
	HandMotion_None,
	HandMotion_IMU,
	HandMotion_Tracker,
	HandMotion_Tracker_RotationOnly,
	HandMotion_Auto
} HandMotion;
typedef enum AxisDirection
{
	AxisDirection_Invalid,
	AxisDirection_Backward,
	AxisDirection_Left,
	AxisDirection_Down,
	AxisDirection_Up,
	AxisDirection_Right,
	AxisDirection_Forward
} AxisDirection;
typedef enum AxisView
{
	AxisView_Invalid,

	AxisView_ZFromViewer,
	AxisView_YFromViewer,
	AxisView_XFromViewer,

	AxisView_XToViewer,
	AxisView_YToViewer,
	AxisView_ZToViewer
} AxisView;
typedef enum AxisPolarity
{
	AxisPolarity_Invalid,

	AxisPolarity_NegativeZ,
	AxisPolarity_NegativeY,
	AxisPolarity_NegativeX,

	AxisPolarity_PositiveX,
	AxisPolarity_PositiveY,
	AxisPolarity_PositiveZ
} AxisPolarity;
typedef enum SystemMessageType
{
	SystemMessageType_Unknown,
	SystemMessageType_LibDebugReplugDongle,
	SystemMessageType_LibDebugRxStall,
	SystemMessageType_LibDebugTxStall,
	
	SystemMessageType_TrackerError,
	SystemMessageType_TrackerOk,
	SystemMessageType_TrackerSystemOutOfDate,
	
	SystemMessageType_GloveSanityErrorPSOCInit,
	SystemMessageType_GloveSanityErrorQCBatV,
	SystemMessageType_GloveSanityErrorQCLRACalib,
	SystemMessageType_GloveSanityErrorQCFlexInit,
	SystemMessageType_GloveSanityErrorQCIMUInit,
	SystemMessageType_GloveSanityErrorQCIMUCalib,
	SystemMessageType_GloveSanityErrorQCID,
	SystemMessageType_GloveSanityErrorQCInterCPU,
	
	SystemMessageType_SessionConnectionVersionMismatch,

	SystemMessageType_TemporarySkeletonModified,

	SystemMessageType_SessionRefusedDueToLicenseIssue,

	SystemMessageType_LaunchDevTools,

	SystemMessageType_MaxSeatMixing,
	SystemMessageType_DeprecatedLicense,

	SystemMessageType_LicenseSupportExpired,

	SystemMessageType_NetSeatsExhausted 

} SystemMessageType;
typedef enum ErgonomicsDataType
{

	ErgonomicsDataType_LeftFingerThumbCMCSpread,
	ErgonomicsDataType_LeftFingerThumbCMCStretch,
	ErgonomicsDataType_LeftFingerThumbMCPStretch,
	ErgonomicsDataType_LeftFingerThumbIPStretch,

	ErgonomicsDataType_LeftFingerIndexMCPSpread,
	ErgonomicsDataType_LeftFingerIndexMCPStretch,
	ErgonomicsDataType_LeftFingerIndexPIPStretch,
	ErgonomicsDataType_LeftFingerIndexDIPStretch,

	ErgonomicsDataType_LeftFingerMiddleMCPSpread,
	ErgonomicsDataType_LeftFingerMiddleMCPStretch,
	ErgonomicsDataType_LeftFingerMiddlePIPStretch,
	ErgonomicsDataType_LeftFingerMiddleDIPStretch,

	ErgonomicsDataType_LeftFingerRingMCPSpread,
	ErgonomicsDataType_LeftFingerRingMCPStretch,
	ErgonomicsDataType_LeftFingerRingPIPStretch,
	ErgonomicsDataType_LeftFingerRingDIPStretch,

	ErgonomicsDataType_LeftFingerPinkyMCPSpread,
	ErgonomicsDataType_LeftFingerPinkyMCPStretch,
	ErgonomicsDataType_LeftFingerPinkyPIPStretch,
	ErgonomicsDataType_LeftFingerPinkyDIPStretch,

	ErgonomicsDataType_RightFingerThumbCMCSpread,
	ErgonomicsDataType_RightFingerThumbCMCStretch,
	ErgonomicsDataType_RightFingerThumbMCPStretch,
	ErgonomicsDataType_RightFingerThumbIPStretch,

	ErgonomicsDataType_RightFingerIndexMCPSpread,
	ErgonomicsDataType_RightFingerIndexMCPStretch,
	ErgonomicsDataType_RightFingerIndexPIPStretch,
	ErgonomicsDataType_RightFingerIndexDIPStretch,

	ErgonomicsDataType_RightFingerMiddleMCPSpread,
	ErgonomicsDataType_RightFingerMiddleMCPStretch,
	ErgonomicsDataType_RightFingerMiddlePIPStretch,
	ErgonomicsDataType_RightFingerMiddleDIPStretch,

	ErgonomicsDataType_RightFingerRingMCPSpread,
	ErgonomicsDataType_RightFingerRingMCPStretch,
	ErgonomicsDataType_RightFingerRingPIPStretch,
	ErgonomicsDataType_RightFingerRingDIPStretch,

	ErgonomicsDataType_RightFingerPinkyMCPSpread,
	ErgonomicsDataType_RightFingerPinkyMCPStretch,
	ErgonomicsDataType_RightFingerPinkyPIPStretch,
	ErgonomicsDataType_RightFingerPinkyDIPStretch,

	ErgonomicsDataType_MAX_SIZE
} ErgonomicsDataType;
typedef enum LicenseType
{
	LicenseType_Undefined,
	LicenseType_Polygon,
	LicenseType_CoreXO,
	LicenseType_CorePro,
	LicenseType_CoreXOPro,

	LicenseType_CoreX,
	LicenseType_CoreO,
	LicenseType_CoreQ,
	LicenseType_CoreXPro,
	LicenseType_CoreOPro,
	LicenseType_CoreQPro,
	LicenseType_CoreXOQPro,
	LicenseType_CoreXR,
	LicenseType_CorePrimeThree,
	LicenseType_Feature,

} LicenseType;
typedef enum LicenseTermType
{
	LicenseTermType_Unknown,
	LicenseTermType_Recurring,
	LicenseTermType_Perpetual,

} LicenseTermType;
typedef enum LicenseStatus
{
	LicenseStatus_Unknown,			
	LicenseStatus_Valid,
	LicenseStatus_Invalid,			
	LicenseStatus_Expired,			
	LicenseStatus_SupportExpired,	

} LicenseStatus;
typedef enum NetSeatState
{
	NetSeatState_Unknown,			
	NetSeatState_SeatGranted,		
	NetSeatState_AllSeatsTaken,		
	NetSeatState_HostUnlicensed,	

} NetSeatState;
typedef enum TimecodeFPS
{
	TimecodeFPS_Undefined,
	TimecodeFPS_23_976,
	TimecodeFPS_24,
	TimecodeFPS_25,
	TimecodeFPS_29_97,
	TimecodeFPS_30,
	TimecodeFPS_48,
	TimecodeFPS_50,
	TimecodeFPS_59_94,
	TimecodeFPS_60,
	TimecodeFPS_29_97DF,
	TimecodeFPS_59_94DF,
} TimecodeFPS;
typedef enum FingerJointType
{
	FingerJointType_Invalid,
	FingerJointType_Metacarpal,
	FingerJointType_Proximal,
	FingerJointType_Intermediate,
	FingerJointType_Distal, 
	FingerJointType_Tip
}FingerJointType;
typedef enum SetGloveCalibrationReturnCode
{
	SetGloveCalibrationReturnCode_Error,
	SetGloveCalibrationReturnCode_Success,
	SetGloveCalibrationReturnCode_VersionError,
	SetGloveCalibrationReturnCode_WrongSideError,
	SetGloveCalibrationReturnCode_GloveNotFoundError,
	SetGloveCalibrationReturnCode_UserServiceError,
	SetGloveCalibrationReturnCode_DeserializationError,

	SetGloveCalibrationReturnCode_MAX_SIZE
} SetGloveCalibrationReturnCode;
typedef enum MessageType
{
	MessageType_Unknown,
	MessageType_Info,
	MessageType_Success,
	MessageType_Warning,
	MessageType_Error
} MessageType;
typedef struct ManusVec3
{
	float x; 
	float y; 
	float z; 
} ManusVec3;
typedef struct ManusVec2
{
	float x; 
	float y; 
} ManusVec2;
typedef struct ManusQuaternion
{
	float w; 
	float x; 
	float y; 
	float z; 
} ManusQuaternion;
typedef struct ManusTransform
{
	ManusVec3 position;
	ManusQuaternion rotation;
	ManusVec3 scale;
} ManusTransform;
typedef struct Color
{
	float r; 
	float g; 
	float b; 
	float a; 
}Color;
typedef struct ManusTimestampInfo
{
	uint16_t fraction; 
	uint8_t second;
	uint8_t minute;
	uint8_t hour;
	uint8_t day; 
	uint8_t month; 
	uint32_t year; 
	bool timecode;
} ManusTimestampInfo;
typedef struct ManusTimestamp
{
	uint64_t time;
} ManusTimestamp;
typedef struct IMUCalibrationInfo
{
	uint32_t mag;					
	uint32_t acc;					
	uint32_t gyr;					
	uint32_t sys;					
} IMUCalibrationInfo;
typedef struct Version
{
	uint32_t major;
	uint32_t minor;
	uint32_t patch;
	char label[MAX_NUM_CHARS_IN_VERSION];
	char sha[MAX_NUM_CHARS_IN_VERSION];
	char tag[MAX_NUM_CHARS_IN_VERSION];
} Version;
typedef struct FirmwareVersion
{
	int32_t version;
	ManusTimestamp timestamp;
} FirmwareVersion;
typedef struct ManusVersion 
{
	char versionInfo[MAX_NUM_CHARS_IN_VERSION];
} ManusVersion;
typedef struct ManusHost
{
	char hostName[MAX_NUM_CHARS_IN_HOST_NAME]; 
	char ipAddress[MAX_NUM_CHARS_IN_IP_ADDRESS];
	Version manusCoreVersion;
} ManusHost;
typedef struct Message
{
	MessageType type;
	char message[MAX_NUM_CHARS_IN_MESSAGE];
} Message;
typedef struct Response
{
	bool result;
	Message message;
} Response;
typedef struct TrackerId
{
	char id[MAX_NUM_CHARS_IN_TRACKER_ID]; 
} TrackerId;
typedef struct TrackerData
{
	ManusTimestamp lastUpdateTime; 

	TrackerId trackerId;

	uint32_t userId; 
	
	bool isHmd; 
	TrackerType trackerType; 

	ManusQuaternion rotation;
	ManusVec3 position;

	TrackingQuality quality; 

	TrackedPoint trackedPoint;
} TrackerData;
typedef struct TrackerStreamInfo
{
	ManusTimestamp publishTime; 
	uint32_t trackerCount; 
} TrackerStreamInfo;
typedef struct TrackingSystemInfo
{
	char name[MAX_NUM_CHARS_IN_TRACKERSYSTEM];
	char description[MAX_NUM_CHARS_IN_TRACKERSYSTEM];
} TrackingSystemInfo;
typedef struct TrackerSystemSettingBool
{
	bool value; 
} TrackerSystemSettingBool;
typedef struct TrackerSystemSettingFile
{
	char value[MAX_NUM_CHARS_IN_TRACKERSYSTEM_FILE_PATH];
	char extension[MAX_NUM_CHARS_IN_TRACKERSYSTEM_FILE_EXTENSION];
} TrackerSystemSettingFile;
typedef struct TrackerSystemSettingInt
{
	int32_t value; 
	int32_t min; 
	int32_t max; 
} TrackerSystemSettingInt;
typedef struct TrackerSystemSettingIp
{
	char value[MAX_NUM_CHARS_IN_IP_ADDRESS];
} TrackerSystemSettingIp;
typedef struct TrackerSystemSetting
{
	char id[MAX_NUM_CHARS_IN_TRACKERSYSTEM];

	TrackerSystemSettingInt settingInt;
	TrackerSystemSettingFile settingFile;
	TrackerSystemSettingBool settingBool;
	TrackerSystemSettingIp settingIp;

	TrackerSystemSettingType settingtype;
} TrackerSystemSetting;
typedef struct TrackerSystem
{
	char id[MAX_NUM_CHARS_IN_TRACKERSYSTEM];
	bool active; 
	TrackerSystemSetting trackerSystemSettings[MAX_NUM_SETTINGS_IN_TRACKERS];
	uint32_t currentSettingsCount; 
} TrackerSystem;
typedef struct GestureProbability
{
	uint32_t id;
	float percent;
} GestureProbability;
typedef struct GestureProbabilities
{
	uint32_t id; 
	bool isUserID; 
	uint32_t totalGestureCount; 
	GestureProbability gestureData[MAX_GESTURE_DATA_CHUNK_SIZE]; 
	uint32_t gestureCount; 
} GestureProbabilities;
typedef struct GestureStreamInfo
{
	ManusTimestamp publishTime; 
	uint32_t gestureProbabilitiesCount; 
} GestureStreamInfo;
typedef struct SkeletonNode
{
	uint32_t id;
	ManusTransform transform;
} SkeletonNode;
typedef struct SkeletonInfo
{
	uint32_t id; 
	uint32_t nodesCount; 
	ManusTimestamp publishTime; 
} SkeletonInfo;
typedef struct RawSkeletonInfo
{
	uint32_t gloveId; 
	uint32_t nodesCount; 
	ManusTimestamp publishTime; 
} RawSkeletonInfo;
typedef struct SkeletonStreamInfo
{
	ManusTimestamp publishTime; 
	uint32_t skeletonsCount; 
} SkeletonStreamInfo;
typedef struct RawDeviceData
{
	uint32_t id;
	uint32_t sensorCount; 
	ManusTransform sensorData[MAX_RAW_DEVICE_DATA_SENSOR_SIZE];
	ManusQuaternion rotation;
}RawDeviceData;
typedef struct RawDeviceDataInfo
{
	ManusTimestamp publishTime; 
	uint32_t rawDeviceDataCount; 
}RawDeviceDataInfo;
typedef struct ErgonomicsData
{
	uint32_t id; 
	bool isUserID; 
	float data[ErgonomicsDataType_MAX_SIZE]; 
} ErgonomicsData;
typedef struct ErgonomicsStream
{
	ManusTimestamp publishTime; 
	ErgonomicsData data[MAX_NUMBER_OF_ERGONOMICS_DATA];
	uint32_t dataCount; 
} ErgonomicsStream;
typedef struct DongleLandscapeData
{
	uint32_t id;
	DeviceClassType classType;
	DeviceFamilyType familyType;
	bool isHaptics;

	Version hardwareVersion;
	Version firmwareVersion;
	ManusTimestamp firmwareTimestamp;

	uint32_t chargingState;

	int32_t channel;

	UpdateStatusEnum updateStatus;

	char licenseType[MAX_NUM_CHARS_IN_LICENSE_TYPE];

	ManusTimestamp lastSeen; 

	uint32_t leftGloveID;
	uint32_t rightGloveID;

	LicenseType licenseLevel; 
	ManusTimestamp licenseExpiration;
	uint32_t licenseMaxNumberOfGlovePairs;

	uint32_t netDeviceID;

	char licenseName[MAX_NUM_CHARS_IN_LICENSE_TYPE]; 
	LicenseTermType licenseTermType; 
	LicenseStatus licenseStatus; 

} DongleLandscapeData;
typedef struct GloveLandscapeData
{
	uint32_t id;
	DeviceClassType classType;
	DeviceFamilyType familyType;
	Side side;
	bool isHaptics;

	DevicePairedState pairedState;
	uint32_t dongleID;

	Version hardwareVersion;
	Version firmwareVersion;
	ManusTimestamp firmwareTimestamp;

	UpdateStatusEnum updateStatus;

	uint32_t batteryPercentage;
	int32_t transmissionStrength;

	IMUCalibrationInfo iMUCalibrationInfo[MAX_NUM_IMUS_ON_GLOVE];

	ManusTimestamp lastSeen; 
	bool excluded;

	uint32_t netDeviceID;
} GloveLandscapeData;
typedef struct Measurement
{
	MeasurementType	entryType; 
	float value; 

	MeasurementUnit unit; 
	MeasurementCategory category; 
	char displayName[MAX_NUM_CHARS_IN_MEASUREMENT];
} Measurement;
typedef struct TrackerOffset
{
	TrackerOffsetType entryType;
	ManusVec3 translation;
	ManusQuaternion rotation;
} TrackerOffset;
typedef struct ExtraTrackerOffset
{
	ExtraTrackerOffsetType entryType; 
	float value; 
} ExtraTrackerOffset;
typedef struct TrackerLandscapeData
{
	char id[MAX_NUM_CHARS_IN_TRACKER_ID];
	TrackerType type; 
	TrackerSystemType systemType; 
	uint32_t user; 
	bool isHMD; 
	char manufacturer[MAX_NUM_CHARS_IN_TRACKER_MANUFACTURER]; 
	char productName[MAX_NUM_CHARS_IN_TRACKER_PRODUCTNAME]; 
	TrackedPoint trackedPoint;
} TrackerLandscapeData;
typedef struct UserProfileLandscapeData
{
	ProfileType profileType; 
	Measurement measurements[MeasurementType_MAX_SIZE];
	TrackerOffset trackerOffsets[TrackerOffsetType_MAX_SIZE];
	ExtraTrackerOffset extraTrackerOffsets[ExtraTrackerOffsetType_MAX_SIZE];
	ManusTimestamp leftGloveCalibrationTimestamp;
	ManusTimestamp rightGloveCalibrationTimestamp;
} UserProfileLandscapeData;
typedef struct UserLandscapeData
{
	uint32_t id; 
	char name[MAX_NUM_CHARS_IN_USERNAME];
	uint32_t dongleID; 
	uint32_t leftGloveID; 
	uint32_t rightGloveID; 
	UserProfileLandscapeData profile;
	uint32_t userIndex; 
} UserLandscapeData;
typedef struct SkeletonLandscapeData
{
	uint32_t id; 
	char session[MAX_NUM_CHARS_IN_HOST_NAME];
	uint32_t userId; 
	SkeletonType type; 
	char rootBoneName[MAX_NUM_CHARS_IN_NODE_NAME];
	bool scaled; 
} SkeletonLandscapeData;
typedef struct DeviceLandscape
{
	DongleLandscapeData dongles[MAX_NUMBER_OF_DONGLES];
	uint32_t dongleCount; 
	GloveLandscapeData gloves[MAX_NUMBER_OF_GLOVES];
	uint32_t gloveCount; 
} DeviceLandscape;
typedef struct UserLandscape
{
	UserLandscapeData users[MAX_USERS];
	uint32_t userCount; 
} UserLandscape;
typedef struct SkeletonLandscape
{
	SkeletonLandscapeData skeletons[MAX_NUMBER_OF_SKELETONS];
	uint32_t skeletonCount; 
} SkeletonLandscape;
typedef struct TrackerLandscape
{
	TrackerLandscapeData trackers[MAX_NUMBER_OF_TRACKERS];
	uint32_t trackerCount; 
} TrackerLandscape;
typedef struct LicenseInfo
{
	uint32_t maxGlovePairs; 
	bool recording; 
	bool exporting; 
	bool advancedExporting; 
	bool unitySession; 
	bool unrealSession; 
	bool openXRSession; 
	bool sdk; 
	bool raw; 
	bool mobuSession; 
	bool xsensSession; 
	bool optitrackSession; 
	bool qualisysSession; 
	bool viconSession; 
	bool nokovSession; 
	bool icidoSession; 
	bool siemensSession; 
	bool vredSession; 
	bool integrated; 
	bool cortexSession; 
	bool fzMotionSession; 
	bool worldVizSession; 
	bool noraxonSession; 
	bool noitomSession; 
	bool abletonSession; 
	bool linuxTarget; 
	uint32_t netSeats; 
} LicenseInfo;
typedef struct SettingsLandscape
{
	Version manusCoreVersion;
	LicenseInfo license;
	bool playbackMode; 
	bool ignoreSessionTimeOuts; 
	FirmwareVersion firmwareOne;
	FirmwareVersion firmwareTwo;
	bool recordingMode; 
	bool isNetDevice; 
	bool isConnectedAsNetDevice; 
}SettingsLandscape;
typedef struct TimecodeInterface
{
	char name[MAX_NUM_CHARS_IN_TIMECODE_INTERFACE_STRINGS];
	char api[MAX_NUM_CHARS_IN_TIMECODE_INTERFACE_STRINGS];
	int index; 
} TimecodeInterface;
typedef struct TimeLandscape
{
	TimecodeInterface interfaces[MAX_NUMBER_OF_AUDIO_INTERFACES];
	uint32_t interfaceCount; 
	TimecodeInterface currentInterface;
	TimecodeFPS fps; 
	bool fakeTimecode; 
	bool useSyncPulse; 
	bool deviceKeepAlive; 
	bool syncStatus; 
	bool timecodeStatus; 
	int32_t ltcChannel; 
} TimeLandscape;
typedef struct GestureLandscapeData
{
	uint32_t id; 
	char name[MAX_NUM_CHARS_IN_USERNAME];
} GestureLandscapeData;
typedef struct NetDeviceLandscapeData
{
	uint32_t netDeviceID;
	char hostname[MAX_NUM_CHARS_IN_HOST_NAME];
	char ip[MAX_NUM_CHARS_IN_IP_ADDRESS];

	NetSeatState netSeatState;	
	uint32_t netSeatsTotal;		
	uint32_t netSeatsUsed;		
} NetDeviceLandscapeData;
typedef struct NetDevicesLandscape
{
	uint32_t numberOfNetDevices; 
	NetDeviceLandscapeData netDevices[MAX_NUMBER_OF_NETDEVICES];
} NetDevicesLandscape;
typedef struct Landscape
{
	DeviceLandscape gloveDevices;
	UserLandscape users;
	SkeletonLandscape skeletons;
	TrackerLandscape trackers;
	SettingsLandscape settings;
	NetDevicesLandscape netDevices;
	TimeLandscape time;
	uint32_t gestureCount; 
} Landscape;
typedef struct NodeSettingsIK
{
	float ikAim;
} NodeSettingsIK;
typedef struct NodeSettingsFoot
{
	float heightFromGround;
} NodeSettingsFoot;
typedef struct NodeSettingsRotationOffset
{
	ManusQuaternion value;
} NodeSettingsRotationOffset;
typedef struct NodeSettingsLeaf
{
	ManusVec3 direction;
	float length;
} NodeSettingsLeaf;
typedef struct NodeSettings
{
	NodeSettingsFlag usedSettings;
	NodeSettingsIK ik;
	NodeSettingsFoot foot;
	NodeSettingsRotationOffset rotationOffset;
	NodeSettingsLeaf leaf;
} NodeSettings;
typedef struct NodeSetup
{
	uint32_t id; 
	char name[MAX_NUM_CHARS_IN_NODE_NAME]; 
	NodeType type; 
	ManusTransform transform;
	uint32_t parentID; 
	NodeSettings settings;
} NodeSetup;
typedef struct ChainSettingsPelvis
{
	float hipHeight; 
	float hipBendOffset; 
	float thicknessMultiplier; 
} ChainSettingsPelvis;
typedef struct ChainSettingsLeg
{
	bool reverseKneeDirection; 
	float kneeRotationOffset; 
	float footForwardOffset; 
	float footSideOffset; 
} ChainSettingsLeg;
typedef struct ChainSettingsSpine
{
	float spineBendOffset; 
} ChainSettingsSpine;
typedef struct ChainSettingsNeck
{
	float neckBendOffset; 
} ChainSettingsNeck;
typedef struct ChainSettingsHead
{
	float headPitchOffset; 
	float headYawOffset; 
	float headTiltOffset; 
	bool useLeafAtEnd; 
} ChainSettingsHead;
typedef struct ChainSettingsArm
{
	float armLengthMultiplier; 
	float elbowRotationOffset; 

	ManusVec3 armRotationOffset;

	ManusVec3 positionMultiplier;
	ManusVec3 positionOffset;
} ChainSettingsArm;
typedef struct ChainSettingsShoulder
{
	float forwardOffset; 
	float shrugOffset; 

	float forwardMultiplier; 
	float shrugMultiplier; 
} ChainSettingsShoulder;
typedef struct ChainSettingsFinger
{
	bool useLeafAtEnd; 
	int32_t metacarpalBoneId; 
	int32_t handChainId; 
	float fingerWidth; 
} ChainSettingsFinger;
typedef struct ChainSettingsHand
{
	int32_t fingerChainIds[MAX_NUM_FINGER_IDS];
	int32_t fingerChainIdsUsed; 
	HandMotion handMotion; 
} ChainSettingsHand;
typedef struct ChainSettingsFoot
{
	int32_t toeChainIds[MAX_NUM_TOE_IDS];
	int32_t toeChainIdsUsed; 
} ChainSettingsFoot;
typedef struct ChainSettingsToe
{
	int32_t footChainId; 
	bool useLeafAtEnd; 
} ChainSettingsToe;
typedef struct ChainSettings
{
	ChainType usedSettings;
	ChainSettingsPelvis pelvis;
	ChainSettingsLeg leg;
	ChainSettingsSpine spine;
	ChainSettingsNeck neck;
	ChainSettingsHead head;
	ChainSettingsArm arm;
	ChainSettingsShoulder shoulder;
	ChainSettingsFinger finger;
	ChainSettingsHand hand;
	ChainSettingsFoot foot;
	ChainSettingsToe toe;
} ChainSettings;
typedef struct ChainSetup
{
	uint32_t id; 
	ChainType type; 
	ChainType dataType; 
	uint32_t dataIndex; 
	uint32_t nodeIdCount; 
	uint32_t nodeIds[MAX_CHAIN_LENGTH];
	ChainSettings settings;
	Side side; 
} ChainSetup;
typedef struct SphereColliderSetup
{
	float radius; 
} SphereColliderSetup;
typedef struct CapsuleColliderSetup
{
	float radius; 
	float length; 
} CapsuleColliderSetup;
typedef struct BoxColliderSetup
{
	ManusVec3 size; 
} BoxColliderSetup;
typedef struct ColliderSetup
{
	uint32_t nodeID; 
	ManusVec3 localPosition; 
	ManusVec3 localRotation; 

	ColliderType type;
	SphereColliderSetup sphere;
	CapsuleColliderSetup capsule;
	BoxColliderSetup box;
} ColliderSetup;
typedef struct Weight
{
	uint32_t nodeID;
	float weightValue;
} Weight;
typedef struct Vertex
{
	ManusVec3 position; 
	uint32_t weightsCount; 
	Weight weights[MAX_BONE_WEIGHTS_PER_VERTEX];
} Vertex;
typedef struct Triangle
{
	int32_t vertexIndex1;
	int32_t vertexIndex2;
	int32_t vertexIndex3;
} Triangle;
typedef struct SkeletonTargetUserData
{
	uint32_t userID; 
} SkeletonTargetUserData;
typedef struct SkeletonTargetUserIndexData
{
	uint32_t userIndex; 
} SkeletonTargetUserIndexData;
typedef struct SkeletonTargetAnimationData
{
	char id[MAX_NUM_CHARS_IN_TARGET_ID]; 
} SkeletonTargetAnimationData;
typedef struct SkeletonTargetGloveData
{
	uint32_t gloveID; 
} SkeletonTargetGloveData;
typedef struct SkeletonSettings
{
	bool scaleToTarget; 
	bool useEndPointApproximations; 
	CollisionType collisionType; 

	SkeletonTargetType targetType;
	SkeletonTargetUserData skeletonTargetUserData;
	SkeletonTargetUserIndexData skeletonTargetUserIndexData;
	SkeletonTargetAnimationData skeletonTargetAnimationData;
	SkeletonTargetGloveData skeletonGloveData;
} SkeletonSettings;
typedef struct SkeletonSetupInfo
{
	uint32_t id; 
	SkeletonType type; 
	SkeletonSettings settings;
	char name[MAX_NUM_CHARS_IN_SKELETON_NAME]; 
} SkeletonSetupInfo;
typedef struct SkeletonSetupArraySizes
{
	uint32_t nodesCount; 
	uint32_t chainsCount; 
	uint32_t collidersCount; 
	uint32_t meshCount; 
} SkeletonSetupArraySizes;
typedef struct TemporarySkeletonInfo
{
	char name[MAX_NUM_CHARS_IN_SKELETON_NAME]; 
	uint32_t index; 
} TemporarySkeletonInfo;
typedef struct TemporarySkeletonsInfoForSession
{
	uint32_t sessionId; 
	char sessionName[MAX_NUM_CHARS_IN_HOST_NAME];
	uint32_t skeletonCount; 
	TemporarySkeletonInfo skeletonInfo[MAX_NUMBER_OF_SKELETONS_PER_SESSION];
} TemporarySkeletonsInfoForSession;
typedef struct TemporarySkeletonCountForSession
{
	uint32_t sessionId; 
	char sessionName[MAX_NUM_CHARS_IN_HOST_NAME];
	uint32_t skeletonCount; 
} TemporarySkeletonCountForSession;
typedef struct TemporarySkeletonCountForAllSessions
{
	uint32_t sessionsCount; 
	TemporarySkeletonCountForSession temporarySkeletonCountForSessions[MAX_NUMBER_OF_SESSIONS];
} TemporarySkeletonCountForAllSessions;
typedef struct TemporarySkeletonSessionsData
{
	uint32_t sessionsCount; 
	TemporarySkeletonsInfoForSession temporarySkeletonsSessions[MAX_NUMBER_OF_SESSIONS];
} TemporarySkeletonSessionsData;
typedef struct SystemMessage
{
	SystemMessageType type;
	char infoString[MAX_NUM_CHARS_IN_SYSTEM_ERROR_MESSAGE];
	uint32_t infoUInt;
} SystemMessage;
typedef struct NodeInfo
{
	uint32_t nodeId; 
	uint32_t parentId; 
	ChainType chainType;
	Side side;
	FingerJointType fingerJointType;
}NodeInfo;
typedef struct GloveCalibrationArgs {
	uint32_t gloveId; 
} GloveCalibrationArgs;
typedef struct GloveCalibrationStepArgs {
	uint32_t gloveId; 
	uint32_t stepIndex; 
} GloveCalibrationStepArgs;
typedef struct GloveCalibrationStepData {
	uint32_t index; 
	char title[MAX_NUM_CHARS_IN_CALIBRATION_TITLE];
	char description[MAX_NUM_CHARS_IN_CALIBRATION_DESCRIPTION];
	float time; 
} GloveCalibrationStepData;
typedef struct CoordinateSystemVUH
{
	AxisView view;
	AxisPolarity up;
	Side handedness;
	float unitScale; 
} CoordinateSystemVUH;
typedef struct CoordinateSystemDirection
{
	AxisDirection x;
	AxisDirection y;
	AxisDirection z;
	float unitScale; 
} CoordinateSystemDirection;
typedef struct TrackerDirection
{
	TrackerOffsetType type; 
	ManusVec3 side;
	ManusVec3 up;
	ManusVec3 forward;
}TrackerDirection;
typedef struct CalibrationProfile
{
	TrackerOffset trackerOffsets[TrackerOffsetType_MAX_SIZE];
	TrackerDirection trackerDirections[TrackerOffsetType_MAX_SIZE];
	Measurement measurements[MeasurementType_MAX_SIZE];
}CalibrationProfile;
typedef void(*ConnectedToCoreCallback_t)(const ManusHost* const p_Host);
typedef void(*DisconnectedFromCoreCallback_t)(const ManusHost* const p_Host);
typedef void(*LoggingCallback_t)(LogSeverity p_Severity, const char* const p_Log, uint32_t p_Length);
typedef void(*SkeletonStreamCallback_t)(const SkeletonStreamInfo* const p_SkeletonInfo);
typedef void(*LandscapeStreamCallback_t)(const Landscape* const p_Landscape);
typedef void(*TrackerStreamCallback_t)(const TrackerStreamInfo* const p_TrackerStreamInfo);
typedef void(*ErgonomicsStreamCallback_t)(const ErgonomicsStream* const p_Ergonomics);
typedef void(*SystemStreamCallback_t)(const SystemMessage* const p_SystemMessage);
typedef void(*RawSkeletonStreamCallback_t)(const SkeletonStreamInfo* const p_SkeletonInfo);
typedef void(*RawDeviceDataStreamCallback_t)(const RawDeviceDataInfo* const p_RawDeviceDataInfo);
typedef void(*GestureStreamCallback_t)(const GestureStreamInfo* const p_GestureStream);

	SDKReturnCode CoreSdk_InitializeCore();
	SDKReturnCode CoreSdk_InitializeIntegrated();
	SDKReturnCode CoreSdk_ShutDown();
	SDKReturnCode CoreSdk_SetSessionType(SessionType p_SessionType);
	SDKReturnCode CoreSdk_SetSettingsLocation(const char* p_SettingsLocation);
	SDKReturnCode CoreSdk_SetLogLocation(const char* p_LogLocation);
	SDKReturnCode CoreSdk_WasDllBuiltInDebugConfiguration(bool* p_WasBuiltInDebugConfiguration);
	SDKReturnCode CoreSdk_GetTimestampInfo(ManusTimestamp p_Timestamp, ManusTimestampInfo* p_Info);
	SDKReturnCode CoreSdk_SetTimestampInfo(ManusTimestamp* p_Timestamp, ManusTimestampInfo p_Info);
	SDKReturnCode CoreSdk_LookForHosts(uint32_t p_WaitSeconds , bool p_LoopbackOnly );
	SDKReturnCode CoreSdk_GetNumberOfAvailableHostsFound(uint32_t* p_NumberOfAvailableHostsFound);
	SDKReturnCode CoreSdk_GetAvailableHostsFound(ManusHost* p_AvailableHostsFound, const uint32_t p_NumberOfHostsThatFitInArray);
	SDKReturnCode CoreSdk_GetIsConnectedToCore(bool* p_ConnectedToCore);
	SDKReturnCode CoreSdk_ConnectGRPC();
	SDKReturnCode CoreSdk_Disconnect();
	SDKReturnCode CoreSdk_ConnectToHost(ManusHost p_Host);
	SDKReturnCode CoreSdk_InitializeCoordinateSystemWithVUH(CoordinateSystemVUH p_CoordinateSystem, bool p_UseWorldCoordinates);
	SDKReturnCode CoreSdk_InitializeCoordinateSystemWithDirection(CoordinateSystemDirection p_CoordinateSystem, bool p_UseWorldCoordinates);
	SDKReturnCode CoreSdk_GetVersionsAndCheckCompatibility(ManusVersion* p_SdkVersion, ManusVersion* p_CoreVersion, bool* p_AreVersionsCompatible);
	SDKReturnCode CoreSdk_GetSessionId(uint32_t* p_SessionId);
	SDKReturnCode CoreSdk_RegisterCallbackForOnConnect(ConnectedToCoreCallback_t p_ConnectedCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForOnDisconnect(DisconnectedFromCoreCallback_t p_DisconnectedCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForOnLog(LoggingCallback_t p_LoggingCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForSkeletonStream(SkeletonStreamCallback_t p_SkeletonStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForTrackerStream(TrackerStreamCallback_t p_TrackerStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForLandscapeStream(LandscapeStreamCallback_t p_LandscapeStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForSystemStream(SystemStreamCallback_t p_SystemStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForErgonomicsStream(ErgonomicsStreamCallback_t p_ErgonomicsStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForRawSkeletonStream(RawSkeletonStreamCallback_t p_RawSkeletonStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForRawDeviceDataStream(RawDeviceDataStreamCallback_t p_RawDeviceDataStreamCallback);
	SDKReturnCode CoreSdk_RegisterCallbackForGestureStream(GestureStreamCallback_t p_GestureStreamCallback);
	SDKReturnCode CoreSdk_SetLicense(uint32_t p_DongleId, const char* p_LicenseString, uint32_t p_LicenseStringSize, Response* p_Response);
	SDKReturnCode CoreSdk_RetrieveLicense(uint32_t p_DongleId, Response* p_Response);
	SDKReturnCode CoreSdk_UpdateFirmware(uint32_t p_DeviceId, Response* p_Response);
	SDKReturnCode CoreSdk_PairGlove(uint32_t p_GloveID, bool* p_Result);
	SDKReturnCode CoreSdk_PairGloveToDongle(uint32_t p_GloveID, uint32_t p_DongleID, bool* p_Result);
	SDKReturnCode CoreSdk_UnpairGlove(uint32_t p_GloveID, bool* p_Result);
	SDKReturnCode CoreSdk_VibrateFingersForGlove(uint32_t p_GloveId, const float* p_Powers);
	SDKReturnCode CoreSdk_VibrateFingersForSkeleton(uint32_t p_SkeletonId, Side p_HandType, const float* p_Powers);
	SDKReturnCode CoreSdk_GetGloveIdOfUser_UsingUserId(uint32_t p_UserId, Side p_HandType, uint32_t* p_GloveId);
	SDKReturnCode CoreSdk_GetNumberOfAvailableGloves(uint32_t* p_NumberOfAvailableGloves);
	SDKReturnCode CoreSdk_GetIdsOfAvailableGloves(uint32_t* p_IdsOfAvailableGloves, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_GetGlovesForDongle(uint32_t p_DongleId, uint32_t* p_LeftGloveId, uint32_t* p_RightGloveId);
	SDKReturnCode CoreSdk_GetDataForGlove_UsingGloveId(uint32_t p_GloveId, GloveLandscapeData* p_GloveData);
	SDKReturnCode CoreSdk_GetDataForDongle(uint32_t p_DongleId, DongleLandscapeData* p_DongleData);
	SDKReturnCode CoreSdk_GetNumberOfDongles(uint32_t* p_NumberOfDongles);
	SDKReturnCode CoreSdk_GetDongleIds(uint32_t* p_DongleIds, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_SetRawSkeletonPinchCompensation(bool p_Enable);
	SDKReturnCode CoreSdk_GetRawSkeletonPinchCompensation(bool* p_Enabled);
	SDKReturnCode CoreSdk_SetRawSkeletonCasingCompensation(float p_FilterStength);
	SDKReturnCode CoreSdk_GetRawSkeletonCasingCompensation(float* p_FilterStength);
	SDKReturnCode CoreSdk_GetNumberOfAvailableUsers(uint32_t* p_NumberOfAvailableUsers);
	SDKReturnCode CoreSdk_GetIdsOfAvailableUsers(uint32_t* p_IdsOfAvailableUsers, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_GetTrackerData(uint32_t p_TrackerIndex, TrackerData* p_TrackerData);
	SDKReturnCode CoreSdk_GetNumberOfAvailableTrackers(uint32_t* p_NumberOfAvailableTrackers);
	SDKReturnCode CoreSdk_GetIdsOfAvailableTrackers(TrackerId* p_IdsOfAvailableTrackers, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_GetNumberOfAvailableTrackersForUserId(uint32_t* p_NumberOfAvailableTrackers, uint32_t p_UserId);
	SDKReturnCode CoreSdk_GetIdsOfAvailableTrackersForUserId(TrackerId* p_IdsOfAvailableTrackers, uint32_t p_UserId, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_GetNumberOfAvailableTrackersForUserIndex(uint32_t* p_NumberOfAvailableTrackers, uint32_t p_UserIndex);
	SDKReturnCode CoreSdk_GetIdsOfAvailableTrackersForUserIndex(TrackerId* p_IdsOfAvailableTrackers, uint32_t p_UserIndex, uint32_t p_NumberOfIdsThatFitInArray);
	SDKReturnCode CoreSdk_GetDataForTracker_UsingTrackerId(TrackerId p_TrackerId, TrackerData* p_TrackerData);
	SDKReturnCode CoreSdk_GetDataForTracker_UsingIdAndType(uint32_t p_UserId, uint32_t p_TrackerType, TrackerData* p_TrackerData);
	SDKReturnCode CoreSdk_SendDataForTrackers(const TrackerData* p_TrackerData, uint32_t p_NumberOfTrackers);
	SDKReturnCode CoreSdk_SetTrackerOffset(uint32_t p_UserId, const TrackerOffset* p_TrackerOffset);
	SDKReturnCode CoreSdk_AssignTrackerToUser(TrackerId p_TrackerId, uint32_t p_UserId);
	SDKReturnCode CoreSdk_AssignRoleToTracker(TrackerId p_TrackerId, TrackerType p_TrackerType);
	SDKReturnCode CoreSdk_GetTrackerSystemsSettings(TrackerSystem* p_TrackerSystems, uint32_t* p_TrackerSystemCount);
	SDKReturnCode CoreSdk_SetTrackerSystemsSettings(TrackerSystem* p_TrackerSystems);
	SDKReturnCode CoreSdk_SetTrackerTimeOutEnabled(bool p_UseTimeOut);
	SDKReturnCode CoreSdk_GetTrackerTimeOutEnabled(bool* p_UseTimeOut);
	SDKReturnCode CoreSdk_SetTrackerTimeOut(float p_TimeOut);
	SDKReturnCode CoreSdk_GetTrackerTimeOut(float* p_TimeOut);
	SDKReturnCode CoreSdk_GetGestureLandscapeData(GestureLandscapeData* p_LandscapeDataArray, uint32_t p_ArraySize);
	SDKReturnCode CoreSdk_GetGestureStreamData(uint32_t p_GestureStreamDataIndex, uint32_t p_StartDataIndex, GestureProbabilities* p_GestureProbabilitiesCollection);
	SDKReturnCode CoreSdk_GloveCalibrationStart(GloveCalibrationArgs p_CalibrationArgs, bool* p_Result);
	SDKReturnCode CoreSdk_GloveCalibrationStop(GloveCalibrationArgs p_CalibrationArgs, bool* p_Result);
	SDKReturnCode CoreSdk_GloveCalibrationFinish(GloveCalibrationArgs p_CalibrationArgs, bool* p_Result);
	SDKReturnCode CoreSdk_GloveCalibrationGetNumberOfSteps(GloveCalibrationArgs p_CalibrationArgs, uint32_t* p_NumberOfSteps);
	SDKReturnCode CoreSdk_GloveCalibrationGetStepData(GloveCalibrationStepArgs p_CalibrationStepArgs, GloveCalibrationStepData* p_Data);
	SDKReturnCode CoreSdk_GloveCalibrationStartStep(GloveCalibrationStepArgs p_CalibrationStepArgs, bool* p_Result);
	SDKReturnCode CoreSdk_GetGloveCalibrationSize(uint32_t p_GloveId, uint32_t* p_Size);
	SDKReturnCode CoreSdk_GetGloveCalibrationSizeForUser(uint32_t p_UserId, Side p_Side, GloveProfileType p_ProfileType, uint32_t* p_Size);
	SDKReturnCode CoreSdk_GetGloveCalibration(unsigned char* p_CalibrationBytes, uint32_t p_BytesLength);
	SDKReturnCode CoreSdk_SetGloveCalibration(uint32_t p_GloveId, unsigned char* p_CalibrationBytes, uint32_t p_BytesLength, SetGloveCalibrationReturnCode* p_Result);
	SDKReturnCode CoreSdk_SetGloveCalibrationForUser(uint32_t p_UserId, unsigned char* p_CalibrationBytes, uint32_t p_BytesLength, SetGloveCalibrationReturnCode* p_Result);
	SDKReturnCode CoreSdk_GetSkeletonInfo(uint32_t p_SkeletonIndex, SkeletonInfo* p_Info);
	SDKReturnCode CoreSdk_GetSkeletonData(uint32_t p_SkeletonIndex, SkeletonNode* p_Nodes, uint32_t p_NodeCount);
	SDKReturnCode CoreSdk_SetRawSkeletonHandMotion(HandMotion p_HandMotion);
	SDKReturnCode CoreSdk_GetRawSkeletonHandMotion(HandMotion* p_HandMotion);
	SDKReturnCode CoreSdk_GetRawSkeletonInfo(uint32_t p_SkeletonIndex, RawSkeletonInfo* p_Info);
	SDKReturnCode CoreSdk_GetRawSkeletonData(uint32_t p_SkeletonIndex, SkeletonNode* p_Nodes, uint32_t p_NodeCount);
	SDKReturnCode CoreSdk_GetRawDeviceData(uint32_t p_RawDeviceDataIndex, RawDeviceData* p_RawDeviceData);
	SDKReturnCode CoreSdk_DoesSkeletonGloveSupportHaptics(uint32_t p_SkeletonId, Side p_HandType, bool* p_IsHaptics);
	SDKReturnCode CoreSdk_CreateSkeletonSetup(SkeletonSetupInfo p_Skeleton, uint32_t* p_SkeletonSetupIndex);
	SDKReturnCode CoreSdk_AddNodeToSkeletonSetup(uint32_t p_SkeletonSetupIndex, NodeSetup p_Node);
	SDKReturnCode CoreSdk_AddChainToSkeletonSetup(uint32_t p_SkeletonSetupIndex, ChainSetup p_Chain);
	SDKReturnCode CoreSdk_AddColliderToSkeletonSetup(uint32_t p_SkeletonSetupIndex, ColliderSetup p_Collider);
	SDKReturnCode CoreSdk_AddMeshSetupToSkeletonSetup(uint32_t p_SkeletonSetupIndex, uint32_t p_NodeID, uint32_t* p_MeshSetupIndex);
	SDKReturnCode CoreSdk_AddVertexToMeshSetup(uint32_t p_SkeletonSetupIndex, uint32_t p_MeshSetupIndex, Vertex p_Vertex);
	SDKReturnCode CoreSdk_AddTriangleToMeshSetup(uint32_t p_SkeletonSetupIndex, uint32_t p_MeshSetupIndex, Triangle p_Triangle);
	SDKReturnCode CoreSdk_OverwriteSkeletonSetup(uint32_t p_SkeletonSetupIndex, SkeletonSetupInfo p_SkeletonSetup);
	SDKReturnCode CoreSdk_OverwriteChainToSkeletonSetup(uint32_t p_SkeletonSetupIndex, ChainSetup p_Chain);
	SDKReturnCode CoreSdk_OverwriteNodeToSkeletonSetup(uint32_t p_SkeletonSetupIndex, NodeSetup p_Node);
	SDKReturnCode CoreSdk_GetSkeletonSetupArraySizes(uint32_t p_SkeletonSetupIndex, SkeletonSetupArraySizes* p_SkeletonInfo);
	SDKReturnCode CoreSdk_AllocateChainsForSkeletonSetup(uint32_t p_SkeletonSetupIndex);
	SDKReturnCode CoreSdk_PrepareSkeletonSetup(uint32_t p_SkeletonSetupIndex);
	SDKReturnCode CoreSdk_GetSkeletonSetupInfo(uint32_t p_SkeletonSetupIndex, SkeletonSetupInfo* p_SDK);
	SDKReturnCode CoreSdk_GetSkeletonSetupChains(uint32_t p_SkeletonSetupIndex, ChainSetup* p_SDK);
	SDKReturnCode CoreSdk_GetSkeletonSetupChainsArray(uint32_t p_SkeletonSetupIndex, ChainSetup* p_ChainSetupArray, uint32_t p_ArraySize);
	SDKReturnCode CoreSdk_GetSkeletonSetupNodes(uint32_t p_SkeletonSetupIndex, NodeSetup* p_SDK);
	SDKReturnCode CoreSdk_GetSkeletonSetupNodesArray(uint32_t p_SkeletonSetupIndex, NodeSetup* p_NodeSetupArray, uint32_t p_ArraySize);
	SDKReturnCode CoreSdk_GetSkeletonSetupColliders(uint32_t p_SkeletonSetupIndex, ColliderSetup* p_SDK);
	SDKReturnCode CoreSdk_GetRawSkeletonNodeCount(uint32_t p_GloveId, uint32_t* p_NodeCount);
	SDKReturnCode CoreSdk_GetRawSkeletonNodeInfo(uint32_t p_GloveId, NodeInfo* p_NodeInfo);
	SDKReturnCode CoreSdk_GetRawSkeletonNodeInfoArray(uint32_t p_GloveId, NodeInfo* p_NodeInfoArray, uint32_t p_ArraySize);
	SDKReturnCode CoreSdk_LoadSkeleton(uint32_t p_SkeletonSetupIndex, uint32_t* p_SkeletonId);
	SDKReturnCode CoreSdk_UnloadSkeleton(uint32_t p_SkeletonId);
	SDKReturnCode CoreSdk_SaveTemporarySkeleton(uint32_t p_SkeletonSetupIndex, uint32_t p_SessionId, bool p_IsSkeletonModified);
	SDKReturnCode CoreSdk_CompressTemporarySkeletonAndGetSize(uint32_t p_SkeletonSetupIndex, uint32_t p_SessionId, uint32_t* p_TemporarySkeletonLengthInBytes);
	SDKReturnCode CoreSdk_GetCompressedTemporarySkeletonData(unsigned char* p_TemporarySkeletonData, uint32_t p_TemporarySkeletonLengthInBytes);
	SDKReturnCode CoreSdk_GetTemporarySkeleton(uint32_t p_SkeletonSetupIndex, uint32_t p_SessionId);
	SDKReturnCode CoreSdk_GetTemporarySkeletonFromCompressedData(uint32_t p_SkeletonSetupIndex, uint32_t p_SessionId, unsigned char* p_TemporarySkeletonData, uint32_t p_TemporarySkeletonLengthInBytes);
	SDKReturnCode CoreSdk_ClearTemporarySkeleton(uint32_t p_SkeletonSetupIndex, uint32_t p_SessionId);
	SDKReturnCode CoreSdk_ClearAllTemporarySkeletons();
	SDKReturnCode CoreSdk_GetTemporarySkeletonCountForAllSessions(TemporarySkeletonCountForAllSessions* p_TemporarySkeletonCountForAllSessions);
	SDKReturnCode CoreSdk_GetTemporarySkeletonsInfoForSession(uint32_t p_SessionId, TemporarySkeletonsInfoForSession* p_TemporarySkeletonsInfoForSession);
	SDKReturnCode CoreSdk_AddUser(char* p_Name, uint32_t* p_UserID);
	SDKReturnCode CoreSdk_RemoveUser(uint32_t p_Id);
	SDKReturnCode CoreSdk_SetUserName(uint32_t p_Id, char* p_Name);
	SDKReturnCode CoreSdk_GetAutoUserAssignment(bool* p_Enabled);
	SDKReturnCode CoreSdk_SetAutoUserAssignment(bool p_Enabled);
	SDKReturnCode CoreSdk_AssignDongleToUser(uint32_t p_Id, uint32_t p_DongleId);
	SDKReturnCode CoreSdk_AssignGloveToUser(uint32_t p_UserId, uint32_t p_GloveId, Side p_Side);
	SDKReturnCode CoreSdk_MoveUserUp(uint32_t p_Id);
	SDKReturnCode CoreSdk_MoveUserDown(uint32_t p_Id);

// Python callbacks - extern "Python" declarations
extern "Python" void python_raw_skeleton_callback(const SkeletonStreamInfo* const p_SkeletonInfo);
extern "Python" void python_skeleton_callback(const SkeletonStreamInfo* const p_SkeletonInfo);
extern "Python" void python_landscape_callback(const Landscape* const p_Landscape);
extern "Python" void python_ergonomics_callback(const ErgonomicsStream* const p_Ergonomics);
extern "Python" void python_raw_device_data_callback(const RawDeviceDataInfo* const p_RawDeviceDataInfo);
extern "Python" void python_system_callback(const SystemMessage* const p_SystemMessage);
extern "Python" void python_connected_callback(const ManusHost* const p_Host);
extern "Python" void python_disconnected_callback(const ManusHost* const p_Host);
extern "Python" void python_log_callback(LogSeverity p_Severity, const char* const p_Log, uint32_t p_Length);
extern "Python" void python_tracker_callback(const TrackerStreamInfo* const p_TrackerStreamInfo);
