"""
Auto-generated Python enums from Manus SDK headers
Do not edit manually - regenerate with build_ffi.py
"""
from enum import IntEnum

class AxisDirection(IntEnum):
    """Auto-generated from AxisDirection"""
    Invalid = 0
    AxisDirection_Invalid = 0  # Full name alias
    Backward = 1
    AxisDirection_Backward = 1  # Full name alias
    Left = 2
    AxisDirection_Left = 2  # Full name alias
    Down = 3
    AxisDirection_Down = 3  # Full name alias
    Up = 4
    AxisDirection_Up = 4  # Full name alias
    Right = 5
    AxisDirection_Right = 5  # Full name alias
    Forward = 6
    AxisDirection_Forward = 6  # Full name alias


class AxisPolarity(IntEnum):
    """Auto-generated from AxisPolarity"""
    Invalid = 0
    AxisPolarity_Invalid = 0  # Full name alias
    NegativeZ = 1
    AxisPolarity_NegativeZ = 1  # Full name alias
    NegativeY = 2
    AxisPolarity_NegativeY = 2  # Full name alias
    NegativeX = 3
    AxisPolarity_NegativeX = 3  # Full name alias
    PositiveX = 4
    AxisPolarity_PositiveX = 4  # Full name alias
    PositiveY = 5
    AxisPolarity_PositiveY = 5  # Full name alias
    PositiveZ = 6
    AxisPolarity_PositiveZ = 6  # Full name alias


class AxisView(IntEnum):
    """Auto-generated from AxisView"""
    Invalid = 0
    AxisView_Invalid = 0  # Full name alias
    ZFromViewer = 1
    AxisView_ZFromViewer = 1  # Full name alias
    YFromViewer = 2
    AxisView_YFromViewer = 2  # Full name alias
    XFromViewer = 3
    AxisView_XFromViewer = 3  # Full name alias
    XToViewer = 4
    AxisView_XToViewer = 4  # Full name alias
    YToViewer = 5
    AxisView_YToViewer = 5  # Full name alias
    ZToViewer = 6
    AxisView_ZToViewer = 6  # Full name alias


class ChainType(IntEnum):
    """Auto-generated from ChainType"""
    Invalid = 0
    ChainType_Invalid = 0  # Full name alias
    Arm = 1
    ChainType_Arm = 1  # Full name alias
    Leg = 2
    ChainType_Leg = 2  # Full name alias
    Neck = 3
    ChainType_Neck = 3  # Full name alias
    Spine = 4
    ChainType_Spine = 4  # Full name alias
    FingerThumb = 5
    ChainType_FingerThumb = 5  # Full name alias
    FingerIndex = 6
    ChainType_FingerIndex = 6  # Full name alias
    FingerMiddle = 7
    ChainType_FingerMiddle = 7  # Full name alias
    FingerRing = 8
    ChainType_FingerRing = 8  # Full name alias
    FingerPinky = 9
    ChainType_FingerPinky = 9  # Full name alias
    Pelvis = 10
    ChainType_Pelvis = 10  # Full name alias
    Head = 11
    ChainType_Head = 11  # Full name alias
    Shoulder = 12
    ChainType_Shoulder = 12  # Full name alias
    Hand = 13
    ChainType_Hand = 13  # Full name alias
    Foot = 14
    ChainType_Foot = 14  # Full name alias
    Toe = 15
    ChainType_Toe = 15  # Full name alias


class ColliderType(IntEnum):
    """Auto-generated from ColliderType"""
    Invalid = 0
    ColliderType_Invalid = 0  # Full name alias
    Sphere = 1
    ColliderType_Sphere = 1  # Full name alias
    Capsule = 2
    ColliderType_Capsule = 2  # Full name alias
    Box = 3
    ColliderType_Box = 3  # Full name alias


class CollisionType(IntEnum):
    """Auto-generated from CollisionType"""
    None_ = 0
    CollisionType_None = 0  # Full name alias
    Discrete = 1
    CollisionType_Discrete = 1  # Full name alias
    Continuous = 2
    CollisionType_Continuous = 2  # Full name alias


class DeviceClassType(IntEnum):
    """Auto-generated from DeviceClassType"""
    Unknown = 0
    DeviceClassType_Unknown = 0  # Full name alias
    Dongle = 1
    DeviceClassType_Dongle = 1  # Full name alias
    Glove = 2
    DeviceClassType_Glove = 2  # Full name alias
    Glongle = 3
    DeviceClassType_Glongle = 3  # Full name alias


class DeviceFamilyType(IntEnum):
    """Auto-generated from DeviceFamilyType"""
    Unknown = 0
    DeviceFamilyType_Unknown = 0  # Full name alias
    Prime1 = 1
    DeviceFamilyType_Prime1 = 1  # Full name alias
    Prime2 = 2
    DeviceFamilyType_Prime2 = 2  # Full name alias
    PrimeX = 3
    DeviceFamilyType_PrimeX = 3  # Full name alias
    Metaglove = 4
    DeviceFamilyType_Metaglove = 4  # Full name alias
    Prime3 = 5
    DeviceFamilyType_Prime3 = 5  # Full name alias
    Virtual = 6
    DeviceFamilyType_Virtual = 6  # Full name alias
    MetaglovePro = 7
    DeviceFamilyType_MetaglovePro = 7  # Full name alias
    MetagloveProPrecision = 8
    DeviceFamilyType_MetagloveProPrecision = 8  # Full name alias
    MetagloveProHaptics = 9
    DeviceFamilyType_MetagloveProHaptics = 9  # Full name alias
    MetagloveProPrecisionHaptics = 10
    DeviceFamilyType_MetagloveProPrecisionHaptics = 10  # Full name alias
    MetagloveAir = 11
    DeviceFamilyType_MetagloveAir = 11  # Full name alias
    MetagloveAirHaptic = 12
    DeviceFamilyType_MetagloveAirHaptic = 12  # Full name alias
    MetagloveTopModule = 13
    DeviceFamilyType_MetagloveTopModule = 13  # Full name alias


class DevicePairedState(IntEnum):
    """Auto-generated from DevicePairedState"""
    Unknown = 0
    DevicePairedState_Unknown = 0  # Full name alias
    Paired = 1
    DevicePairedState_Paired = 1  # Full name alias
    Unpaired = 2
    DevicePairedState_Unpaired = 2  # Full name alias
    Pairing = 3
    DevicePairedState_Pairing = 3  # Full name alias


class ErgonomicsDataType(IntEnum):
    """Auto-generated from ErgonomicsDataType"""
    LeftFingerThumbCMCSpread = 0
    ErgonomicsDataType_LeftFingerThumbCMCSpread = 0  # Full name alias
    LeftFingerThumbCMCStretch = 1
    ErgonomicsDataType_LeftFingerThumbCMCStretch = 1  # Full name alias
    LeftFingerThumbMCPStretch = 2
    ErgonomicsDataType_LeftFingerThumbMCPStretch = 2  # Full name alias
    LeftFingerThumbIPStretch = 3
    ErgonomicsDataType_LeftFingerThumbIPStretch = 3  # Full name alias
    LeftFingerIndexMCPSpread = 4
    ErgonomicsDataType_LeftFingerIndexMCPSpread = 4  # Full name alias
    LeftFingerIndexMCPStretch = 5
    ErgonomicsDataType_LeftFingerIndexMCPStretch = 5  # Full name alias
    LeftFingerIndexPIPStretch = 6
    ErgonomicsDataType_LeftFingerIndexPIPStretch = 6  # Full name alias
    LeftFingerIndexDIPStretch = 7
    ErgonomicsDataType_LeftFingerIndexDIPStretch = 7  # Full name alias
    LeftFingerMiddleMCPSpread = 8
    ErgonomicsDataType_LeftFingerMiddleMCPSpread = 8  # Full name alias
    LeftFingerMiddleMCPStretch = 9
    ErgonomicsDataType_LeftFingerMiddleMCPStretch = 9  # Full name alias
    LeftFingerMiddlePIPStretch = 10
    ErgonomicsDataType_LeftFingerMiddlePIPStretch = 10  # Full name alias
    LeftFingerMiddleDIPStretch = 11
    ErgonomicsDataType_LeftFingerMiddleDIPStretch = 11  # Full name alias
    LeftFingerRingMCPSpread = 12
    ErgonomicsDataType_LeftFingerRingMCPSpread = 12  # Full name alias
    LeftFingerRingMCPStretch = 13
    ErgonomicsDataType_LeftFingerRingMCPStretch = 13  # Full name alias
    LeftFingerRingPIPStretch = 14
    ErgonomicsDataType_LeftFingerRingPIPStretch = 14  # Full name alias
    LeftFingerRingDIPStretch = 15
    ErgonomicsDataType_LeftFingerRingDIPStretch = 15  # Full name alias
    LeftFingerPinkyMCPSpread = 16
    ErgonomicsDataType_LeftFingerPinkyMCPSpread = 16  # Full name alias
    LeftFingerPinkyMCPStretch = 17
    ErgonomicsDataType_LeftFingerPinkyMCPStretch = 17  # Full name alias
    LeftFingerPinkyPIPStretch = 18
    ErgonomicsDataType_LeftFingerPinkyPIPStretch = 18  # Full name alias
    LeftFingerPinkyDIPStretch = 19
    ErgonomicsDataType_LeftFingerPinkyDIPStretch = 19  # Full name alias
    RightFingerThumbCMCSpread = 20
    ErgonomicsDataType_RightFingerThumbCMCSpread = 20  # Full name alias
    RightFingerThumbCMCStretch = 21
    ErgonomicsDataType_RightFingerThumbCMCStretch = 21  # Full name alias
    RightFingerThumbMCPStretch = 22
    ErgonomicsDataType_RightFingerThumbMCPStretch = 22  # Full name alias
    RightFingerThumbIPStretch = 23
    ErgonomicsDataType_RightFingerThumbIPStretch = 23  # Full name alias
    RightFingerIndexMCPSpread = 24
    ErgonomicsDataType_RightFingerIndexMCPSpread = 24  # Full name alias
    RightFingerIndexMCPStretch = 25
    ErgonomicsDataType_RightFingerIndexMCPStretch = 25  # Full name alias
    RightFingerIndexPIPStretch = 26
    ErgonomicsDataType_RightFingerIndexPIPStretch = 26  # Full name alias
    RightFingerIndexDIPStretch = 27
    ErgonomicsDataType_RightFingerIndexDIPStretch = 27  # Full name alias
    RightFingerMiddleMCPSpread = 28
    ErgonomicsDataType_RightFingerMiddleMCPSpread = 28  # Full name alias
    RightFingerMiddleMCPStretch = 29
    ErgonomicsDataType_RightFingerMiddleMCPStretch = 29  # Full name alias
    RightFingerMiddlePIPStretch = 30
    ErgonomicsDataType_RightFingerMiddlePIPStretch = 30  # Full name alias
    RightFingerMiddleDIPStretch = 31
    ErgonomicsDataType_RightFingerMiddleDIPStretch = 31  # Full name alias
    RightFingerRingMCPSpread = 32
    ErgonomicsDataType_RightFingerRingMCPSpread = 32  # Full name alias
    RightFingerRingMCPStretch = 33
    ErgonomicsDataType_RightFingerRingMCPStretch = 33  # Full name alias
    RightFingerRingPIPStretch = 34
    ErgonomicsDataType_RightFingerRingPIPStretch = 34  # Full name alias
    RightFingerRingDIPStretch = 35
    ErgonomicsDataType_RightFingerRingDIPStretch = 35  # Full name alias
    RightFingerPinkyMCPSpread = 36
    ErgonomicsDataType_RightFingerPinkyMCPSpread = 36  # Full name alias
    RightFingerPinkyMCPStretch = 37
    ErgonomicsDataType_RightFingerPinkyMCPStretch = 37  # Full name alias
    RightFingerPinkyPIPStretch = 38
    ErgonomicsDataType_RightFingerPinkyPIPStretch = 38  # Full name alias
    RightFingerPinkyDIPStretch = 39
    ErgonomicsDataType_RightFingerPinkyDIPStretch = 39  # Full name alias
    MAX_SIZE = 40
    ErgonomicsDataType_MAX_SIZE = 40  # Full name alias


class ExtraTrackerOffsetType(IntEnum):
    """Auto-generated from ExtraTrackerOffsetType"""
    Unknown = 0
    ExtraTrackerOffsetType_Unknown = 0  # Full name alias
    HeadForward = 1
    ExtraTrackerOffsetType_HeadForward = 1  # Full name alias
    HipForward = 2
    ExtraTrackerOffsetType_HipForward = 2  # Full name alias
    HipHeight = 3
    ExtraTrackerOffsetType_HipHeight = 3  # Full name alias
    MAX_SIZE = 4
    ExtraTrackerOffsetType_MAX_SIZE = 4  # Full name alias


class FingerJointType(IntEnum):
    """Auto-generated from FingerJointType"""
    Invalid = 0
    FingerJointType_Invalid = 0  # Full name alias
    Metacarpal = 1
    FingerJointType_Metacarpal = 1  # Full name alias
    Proximal = 2
    FingerJointType_Proximal = 2  # Full name alias
    Intermediate = 3
    FingerJointType_Intermediate = 3  # Full name alias
    Distal = 4
    FingerJointType_Distal = 4  # Full name alias
    Tip = 5
    FingerJointType_Tip = 5  # Full name alias


class GloveProfileType(IntEnum):
    """Auto-generated from GloveProfileType"""
    Invalid = 0
    GloveProfileType_Invalid = 0  # Full name alias
    Metaglove = 1
    GloveProfileType_Metaglove = 1  # Full name alias
    MetaglovePro = 2
    GloveProfileType_MetaglovePro = 2  # Full name alias


class HandMotion(IntEnum):
    """Auto-generated from HandMotion"""
    None_ = 0
    HandMotion_None = 0  # Full name alias
    IMU = 1
    HandMotion_IMU = 1  # Full name alias
    Tracker = 2
    HandMotion_Tracker = 2  # Full name alias
    Tracker_RotationOnly = 3
    HandMotion_Tracker_RotationOnly = 3  # Full name alias
    Auto = 4
    HandMotion_Auto = 4  # Full name alias


class LicenseStatus(IntEnum):
    """Auto-generated from LicenseStatus"""
    Unknown = 0
    LicenseStatus_Unknown = 0  # Full name alias
    Valid = 1
    LicenseStatus_Valid = 1  # Full name alias
    Invalid = 2
    LicenseStatus_Invalid = 2  # Full name alias
    Expired = 3
    LicenseStatus_Expired = 3  # Full name alias
    SupportExpired = 4
    LicenseStatus_SupportExpired = 4  # Full name alias


class LicenseTermType(IntEnum):
    """Auto-generated from LicenseTermType"""
    Unknown = 0
    LicenseTermType_Unknown = 0  # Full name alias
    Recurring = 1
    LicenseTermType_Recurring = 1  # Full name alias
    Perpetual = 2
    LicenseTermType_Perpetual = 2  # Full name alias


class LicenseType(IntEnum):
    """Auto-generated from LicenseType"""
    Undefined = 0
    LicenseType_Undefined = 0  # Full name alias
    Polygon = 1
    LicenseType_Polygon = 1  # Full name alias
    CoreXO = 2
    LicenseType_CoreXO = 2  # Full name alias
    CorePro = 3
    LicenseType_CorePro = 3  # Full name alias
    CoreXOPro = 4
    LicenseType_CoreXOPro = 4  # Full name alias
    CoreX = 5
    LicenseType_CoreX = 5  # Full name alias
    CoreO = 6
    LicenseType_CoreO = 6  # Full name alias
    CoreQ = 7
    LicenseType_CoreQ = 7  # Full name alias
    CoreXPro = 8
    LicenseType_CoreXPro = 8  # Full name alias
    CoreOPro = 9
    LicenseType_CoreOPro = 9  # Full name alias
    CoreQPro = 10
    LicenseType_CoreQPro = 10  # Full name alias
    CoreXOQPro = 11
    LicenseType_CoreXOQPro = 11  # Full name alias
    CoreXR = 12
    LicenseType_CoreXR = 12  # Full name alias
    CorePrimeThree = 13
    LicenseType_CorePrimeThree = 13  # Full name alias
    Feature = 14
    LicenseType_Feature = 14  # Full name alias


class LogSeverity(IntEnum):
    """Auto-generated from LogSeverity"""
    Debug = 0
    LogSeverity_Debug = 0  # Full name alias
    Info = 1
    LogSeverity_Info = 1  # Full name alias
    Warn = 2
    LogSeverity_Warn = 2  # Full name alias
    Error = 3
    LogSeverity_Error = 3  # Full name alias


class MeasurementCategory(IntEnum):
    """Auto-generated from MeasurementCategory"""
    Misc = 0
    MeasurementCategory_Misc = 0  # Full name alias
    Generic = 1
    MeasurementCategory_Generic = 1  # Full name alias
    Arms = 2
    MeasurementCategory_Arms = 2  # Full name alias
    Legs = 3
    MeasurementCategory_Legs = 3  # Full name alias
    Body = 4
    MeasurementCategory_Body = 4  # Full name alias


class MeasurementType(IntEnum):
    """Auto-generated from MeasurementType"""
    Unknown = 0
    MeasurementType_Unknown = 0  # Full name alias
    PlayerHeight = 1
    MeasurementType_PlayerHeight = 1  # Full name alias
    SpineLength = 2
    MeasurementType_SpineLength = 2  # Full name alias
    NeckLength = 3
    MeasurementType_NeckLength = 3  # Full name alias
    UpperArmLength = 4
    MeasurementType_UpperArmLength = 4  # Full name alias
    LowerArmLength = 5
    MeasurementType_LowerArmLength = 5  # Full name alias
    ArmLength = 6
    MeasurementType_ArmLength = 6  # Full name alias
    ArmSpan = 7
    MeasurementType_ArmSpan = 7  # Full name alias
    UpperLegLength = 8
    MeasurementType_UpperLegLength = 8  # Full name alias
    LowerLegLength = 9
    MeasurementType_LowerLegLength = 9  # Full name alias
    LegLength = 10
    MeasurementType_LegLength = 10  # Full name alias
    HandLength = 11
    MeasurementType_HandLength = 11  # Full name alias
    FootLength = 12
    MeasurementType_FootLength = 12  # Full name alias
    HipWidth = 13
    MeasurementType_HipWidth = 13  # Full name alias
    ShoulderWidth = 14
    MeasurementType_ShoulderWidth = 14  # Full name alias
    ShoulderHeight = 15
    MeasurementType_ShoulderHeight = 15  # Full name alias
    HeadLength = 16
    MeasurementType_HeadLength = 16  # Full name alias
    Thickness = 17
    MeasurementType_Thickness = 17  # Full name alias
    ArmRatio = 18
    MeasurementType_ArmRatio = 18  # Full name alias
    LegRatio = 19
    MeasurementType_LegRatio = 19  # Full name alias
    MAX_SIZE = 20
    MeasurementType_MAX_SIZE = 20  # Full name alias


class MeasurementUnit(IntEnum):
    """Auto-generated from MeasurementUnit"""
    Meters = 0
    MeasurementUnit_Meters = 0  # Full name alias
    Percentage = 1
    MeasurementUnit_Percentage = 1  # Full name alias


class MessageType(IntEnum):
    """Auto-generated from MessageType"""
    Unknown = 0
    MessageType_Unknown = 0  # Full name alias
    Info = 1
    MessageType_Info = 1  # Full name alias
    Success = 2
    MessageType_Success = 2  # Full name alias
    Warning = 3
    MessageType_Warning = 3  # Full name alias
    Error = 4
    MessageType_Error = 4  # Full name alias


class NetSeatState(IntEnum):
    """Auto-generated from NetSeatState"""
    Unknown = 0
    NetSeatState_Unknown = 0  # Full name alias
    AllSeatsTaken = 1
    NetSeatState_AllSeatsTaken = 1  # Full name alias
    HostUnlicensed = 2
    NetSeatState_HostUnlicensed = 2  # Full name alias


class NodeSettingsFlag(IntEnum):
    """Auto-generated from NodeSettingsFlag"""
    None_ = 0
    NodeSettingsFlag_None = 0  # Full name alias
    IK = 1
    NodeSettingsFlag_IK = 1  # Full name alias
    Foot = 2
    NodeSettingsFlag_Foot = 2  # Full name alias
    RotationOffset = 4
    NodeSettingsFlag_RotationOffset = 4  # Full name alias
    Leaf = 8
    NodeSettingsFlag_Leaf = 8  # Full name alias


class NodeType(IntEnum):
    """Auto-generated from NodeType"""
    Invalid = 0
    NodeType_Invalid = 0  # Full name alias
    Joint = 1
    NodeType_Joint = 1  # Full name alias
    Mesh = 2
    NodeType_Mesh = 2  # Full name alias
    Leaf = 3
    NodeType_Leaf = 3  # Full name alias
    Collider = 4
    NodeType_Collider = 4  # Full name alias


class ProfileType(IntEnum):
    """Auto-generated from ProfileType"""
    Hands = 0
    ProfileType_Hands = 0  # Full name alias
    FullBody = 1
    ProfileType_FullBody = 1  # Full name alias
    MAX_SIZE = 2
    ProfileType_MAX_SIZE = 2  # Full name alias


class SDKReturnCode(IntEnum):
    """Auto-generated from SDKReturnCode"""
    Success = 0
    SDKReturnCode_Success = 0  # Full name alias
    InvalidArgument = 1
    SDKReturnCode_InvalidArgument = 1  # Full name alias
    ArgumentSizeMismatch = 2
    SDKReturnCode_ArgumentSizeMismatch = 2  # Full name alias
    UnsupportedStringSizeEncountered = 3
    SDKReturnCode_UnsupportedStringSizeEncountered = 3  # Full name alias
    SdkNotAvailable = 4
    SDKReturnCode_SdkNotAvailable = 4  # Full name alias
    HostFinderNotAvailable = 5
    SDKReturnCode_HostFinderNotAvailable = 5  # Full name alias
    DataNotAvailable = 6
    SDKReturnCode_DataNotAvailable = 6  # Full name alias
    MemoryError = 7
    SDKReturnCode_MemoryError = 7  # Full name alias
    InternalError = 8
    SDKReturnCode_InternalError = 8  # Full name alias
    FunctionCalledAtWrongTime = 9
    SDKReturnCode_FunctionCalledAtWrongTime = 9  # Full name alias
    NotConnected = 10
    SDKReturnCode_NotConnected = 10  # Full name alias
    ConnectionTimeout = 11
    SDKReturnCode_ConnectionTimeout = 11  # Full name alias
    InvalidID = 12
    SDKReturnCode_InvalidID = 12  # Full name alias
    NullPointer = 13
    SDKReturnCode_NullPointer = 13  # Full name alias
    InvalidSequence = 14
    SDKReturnCode_InvalidSequence = 14  # Full name alias
    NoCoordinateSystemSet = 15
    SDKReturnCode_NoCoordinateSystemSet = 15  # Full name alias
    SdkIsTerminating = 16
    SDKReturnCode_SdkIsTerminating = 16  # Full name alias
    StubNullPointer = 17
    SDKReturnCode_StubNullPointer = 17  # Full name alias
    SkeletonNotLoaded = 18
    SDKReturnCode_SkeletonNotLoaded = 18  # Full name alias
    FunctionNotAvailable = 19
    SDKReturnCode_FunctionNotAvailable = 19  # Full name alias
    MAX_SIZE = 20
    SDKReturnCode_MAX_SIZE = 20  # Full name alias


class SessionType(IntEnum):
    """Auto-generated from SessionType"""
    Unknown = 0
    SessionType_Unknown = 0  # Full name alias
    UnityPlugin = 1
    SessionType_UnityPlugin = 1  # Full name alias
    UnrealPlugin = 2
    SessionType_UnrealPlugin = 2  # Full name alias
    CoreSDK = 3
    SessionType_CoreSDK = 3  # Full name alias


class SetGloveCalibrationReturnCode(IntEnum):
    """Auto-generated from SetGloveCalibrationReturnCode"""
    Error = 0
    SetGloveCalibrationReturnCode_Error = 0  # Full name alias
    Success = 1
    SetGloveCalibrationReturnCode_Success = 1  # Full name alias
    VersionError = 2
    SetGloveCalibrationReturnCode_VersionError = 2  # Full name alias
    WrongSideError = 3
    SetGloveCalibrationReturnCode_WrongSideError = 3  # Full name alias
    GloveNotFoundError = 4
    SetGloveCalibrationReturnCode_GloveNotFoundError = 4  # Full name alias
    UserServiceError = 5
    SetGloveCalibrationReturnCode_UserServiceError = 5  # Full name alias
    DeserializationError = 6
    SetGloveCalibrationReturnCode_DeserializationError = 6  # Full name alias
    MAX_SIZE = 7
    SetGloveCalibrationReturnCode_MAX_SIZE = 7  # Full name alias


class Side(IntEnum):
    """Auto-generated from Side"""
    Invalid = 0
    Side_Invalid = 0  # Full name alias
    Left = 1
    Side_Left = 1  # Full name alias
    Right = 2
    Side_Right = 2  # Full name alias
    Center = 3
    Side_Center = 3  # Full name alias


class SkeletonTargetType(IntEnum):
    """Auto-generated from SkeletonTargetType"""
    Invalid = 0
    SkeletonTargetType_Invalid = 0  # Full name alias
    UserData = 1
    SkeletonTargetType_UserData = 1  # Full name alias
    UserIndexData = 2
    SkeletonTargetType_UserIndexData = 2  # Full name alias
    AnimationData = 3
    SkeletonTargetType_AnimationData = 3  # Full name alias
    GloveData = 4
    SkeletonTargetType_GloveData = 4  # Full name alias


class SkeletonType(IntEnum):
    """Auto-generated from SkeletonType"""
    Invalid = 0
    SkeletonType_Invalid = 0  # Full name alias
    Hand = 1
    SkeletonType_Hand = 1  # Full name alias
    Body = 2
    SkeletonType_Body = 2  # Full name alias
    Both = 3
    SkeletonType_Both = 3  # Full name alias


class SystemMessageType(IntEnum):
    """Auto-generated from SystemMessageType"""
    Unknown = 0
    SystemMessageType_Unknown = 0  # Full name alias
    LibDebugReplugDongle = 1
    SystemMessageType_LibDebugReplugDongle = 1  # Full name alias
    LibDebugRxStall = 2
    SystemMessageType_LibDebugRxStall = 2  # Full name alias
    LibDebugTxStall = 3
    SystemMessageType_LibDebugTxStall = 3  # Full name alias
    TrackerError = 4
    SystemMessageType_TrackerError = 4  # Full name alias
    TrackerOk = 5
    SystemMessageType_TrackerOk = 5  # Full name alias
    TrackerSystemOutOfDate = 6
    SystemMessageType_TrackerSystemOutOfDate = 6  # Full name alias
    GloveSanityErrorPSOCInit = 7
    SystemMessageType_GloveSanityErrorPSOCInit = 7  # Full name alias
    GloveSanityErrorQCBatV = 8
    SystemMessageType_GloveSanityErrorQCBatV = 8  # Full name alias
    GloveSanityErrorQCLRACalib = 9
    SystemMessageType_GloveSanityErrorQCLRACalib = 9  # Full name alias
    GloveSanityErrorQCFlexInit = 10
    SystemMessageType_GloveSanityErrorQCFlexInit = 10  # Full name alias
    GloveSanityErrorQCIMUInit = 11
    SystemMessageType_GloveSanityErrorQCIMUInit = 11  # Full name alias
    GloveSanityErrorQCIMUCalib = 12
    SystemMessageType_GloveSanityErrorQCIMUCalib = 12  # Full name alias
    GloveSanityErrorQCID = 13
    SystemMessageType_GloveSanityErrorQCID = 13  # Full name alias
    GloveSanityErrorQCInterCPU = 14
    SystemMessageType_GloveSanityErrorQCInterCPU = 14  # Full name alias
    SessionConnectionVersionMismatch = 15
    SystemMessageType_SessionConnectionVersionMismatch = 15  # Full name alias
    TemporarySkeletonModified = 16
    SystemMessageType_TemporarySkeletonModified = 16  # Full name alias
    SessionRefusedDueToLicenseIssue = 17
    SystemMessageType_SessionRefusedDueToLicenseIssue = 17  # Full name alias
    LaunchDevTools = 18
    SystemMessageType_LaunchDevTools = 18  # Full name alias
    MaxSeatMixing = 19
    SystemMessageType_MaxSeatMixing = 19  # Full name alias
    DeprecatedLicense = 20
    SystemMessageType_DeprecatedLicense = 20  # Full name alias
    LicenseSupportExpired = 21
    SystemMessageType_LicenseSupportExpired = 21  # Full name alias
    NetSeatsExhausted = 22
    SystemMessageType_NetSeatsExhausted = 22  # Full name alias


class TimecodeFPS(IntEnum):
    """Auto-generated from TimecodeFPS"""
    Undefined = 0
    TimecodeFPS_Undefined = 0  # Full name alias
    _23_976 = 1
    TimecodeFPS_23_976 = 1  # Full name alias
    _24 = 2
    TimecodeFPS_24 = 2  # Full name alias
    _25 = 3
    TimecodeFPS_25 = 3  # Full name alias
    _29_97 = 4
    TimecodeFPS_29_97 = 4  # Full name alias
    _30 = 5
    TimecodeFPS_30 = 5  # Full name alias
    _48 = 6
    TimecodeFPS_48 = 6  # Full name alias
    _50 = 7
    TimecodeFPS_50 = 7  # Full name alias
    _59_94 = 8
    TimecodeFPS_59_94 = 8  # Full name alias
    _60 = 9
    TimecodeFPS_60 = 9  # Full name alias
    _29_97DF = 10
    TimecodeFPS_29_97DF = 10  # Full name alias
    _59_94DF = 11
    TimecodeFPS_59_94DF = 11  # Full name alias


class TrackedPoint(IntEnum):
    """Auto-generated from TrackedPoint"""
    Unknown = 0
    TrackedPoint_Unknown = 0  # Full name alias
    Casing = 1
    TrackedPoint_Casing = 1  # Full name alias
    Joint = 2
    TrackedPoint_Joint = 2  # Full name alias


class TrackerOffsetType(IntEnum):
    """Auto-generated from TrackerOffsetType"""
    Unknown = 0
    TrackerOffsetType_Unknown = 0  # Full name alias
    HeadTrackerToHead = 1
    TrackerOffsetType_HeadTrackerToHead = 1  # Full name alias
    HeadTrackerToTopOfHead = 2
    TrackerOffsetType_HeadTrackerToTopOfHead = 2  # Full name alias
    LeftHandTrackerToWrist = 3
    TrackerOffsetType_LeftHandTrackerToWrist = 3  # Full name alias
    RightHandTrackerToWrist = 4
    TrackerOffsetType_RightHandTrackerToWrist = 4  # Full name alias
    LeftFootTrackerToAnkle = 5
    TrackerOffsetType_LeftFootTrackerToAnkle = 5  # Full name alias
    RightFootTrackerToAnkle = 6
    TrackerOffsetType_RightFootTrackerToAnkle = 6  # Full name alias
    HipTrackerToHip = 7
    TrackerOffsetType_HipTrackerToHip = 7  # Full name alias
    HipTrackerToLeftLeg = 8
    TrackerOffsetType_HipTrackerToLeftLeg = 8  # Full name alias
    HipTrackerToRightLeg = 9
    TrackerOffsetType_HipTrackerToRightLeg = 9  # Full name alias
    LeftUpperArmTrackerToElbow = 10
    TrackerOffsetType_LeftUpperArmTrackerToElbow = 10  # Full name alias
    RightUpperArmTrackerToElbow = 11
    TrackerOffsetType_RightUpperArmTrackerToElbow = 11  # Full name alias
    LeftUpperArmTrackerToShoulder = 12
    TrackerOffsetType_LeftUpperArmTrackerToShoulder = 12  # Full name alias
    RightUpperArmTrackerToShoulder = 13
    TrackerOffsetType_RightUpperArmTrackerToShoulder = 13  # Full name alias
    LeftHandTrackerToCasing = 14
    TrackerOffsetType_LeftHandTrackerToCasing = 14  # Full name alias
    RightHandTrackerToCasing = 15
    TrackerOffsetType_RightHandTrackerToCasing = 15  # Full name alias
    MAX_SIZE = 16
    TrackerOffsetType_MAX_SIZE = 16  # Full name alias


class TrackerSystemSettingType(IntEnum):
    """Auto-generated from TrackerSystemSettingType"""
    Undefined = 0
    TrackerSystemSettingType_Undefined = 0  # Full name alias
    SettingInt = 1
    TrackerSystemSettingType_SettingInt = 1  # Full name alias
    SettingFile = 2
    TrackerSystemSettingType_SettingFile = 2  # Full name alias
    SettingBool = 3
    TrackerSystemSettingType_SettingBool = 3  # Full name alias
    SettingIp = 4
    TrackerSystemSettingType_SettingIp = 4  # Full name alias
    MAX_SIZE = 5
    TrackerSystemSettingType_MAX_SIZE = 5  # Full name alias


class TrackerSystemType(IntEnum):
    """Auto-generated from TrackerSystemType"""
    Unknown = 0
    TrackerSystemType_Unknown = 0  # Full name alias
    Antilatency = 1
    TrackerSystemType_Antilatency = 1  # Full name alias
    ART = 2
    TrackerSystemType_ART = 2  # Full name alias
    OpenVR = 3
    TrackerSystemType_OpenVR = 3  # Full name alias
    Optitrack = 4
    TrackerSystemType_Optitrack = 4  # Full name alias
    Vicon = 5
    TrackerSystemType_Vicon = 5  # Full name alias
    OpenXR = 6
    TrackerSystemType_OpenXR = 6  # Full name alias


class TrackerType(IntEnum):
    """Auto-generated from TrackerType"""
    Unknown = 0
    TrackerType_Unknown = 0  # Full name alias
    Head = 1
    TrackerType_Head = 1  # Full name alias
    Waist = 2
    TrackerType_Waist = 2  # Full name alias
    LeftHand = 3
    TrackerType_LeftHand = 3  # Full name alias
    RightHand = 4
    TrackerType_RightHand = 4  # Full name alias
    LeftFoot = 5
    TrackerType_LeftFoot = 5  # Full name alias
    RightFoot = 6
    TrackerType_RightFoot = 6  # Full name alias
    LeftUpperArm = 7
    TrackerType_LeftUpperArm = 7  # Full name alias
    RightUpperArm = 8
    TrackerType_RightUpperArm = 8  # Full name alias
    LeftUpperLeg = 9
    TrackerType_LeftUpperLeg = 9  # Full name alias
    RightUpperLeg = 10
    TrackerType_RightUpperLeg = 10  # Full name alias
    Controller = 11
    TrackerType_Controller = 11  # Full name alias
    Camera = 12
    TrackerType_Camera = 12  # Full name alias
    MAX_SIZE = 13
    TrackerType_MAX_SIZE = 13  # Full name alias


class TrackingQuality(IntEnum):
    """Auto-generated from TrackingQuality"""
    Untrackable = 0
    TrackingQuality_Untrackable = 0  # Full name alias
    BadTracking = 1
    TrackingQuality_BadTracking = 1  # Full name alias
    Trackable = 2
    TrackingQuality_Trackable = 2  # Full name alias


class UpdateStatusEnum(IntEnum):
    """Auto-generated from UpdateStatusEnum"""
    Unknown = 0
    UpdateStatusEnum_Unknown = 0  # Full name alias
    NoUpdateAvailable = 1
    UpdateStatusEnum_NoUpdateAvailable = 1  # Full name alias
    UpdateAvailable = 2
    UpdateStatusEnum_UpdateAvailable = 2  # Full name alias
    MandatoryUpdateAvailable = 3
    UpdateStatusEnum_MandatoryUpdateAvailable = 3  # Full name alias
    UpdatingInitializing = 4
    UpdateStatusEnum_UpdatingInitializing = 4  # Full name alias
    UpdatingBootloader = 5
    UpdateStatusEnum_UpdatingBootloader = 5  # Full name alias
    UpdatingFirmware = 6
    UpdateStatusEnum_UpdatingFirmware = 6  # Full name alias
    UpdatingFinalizing = 7
    UpdateStatusEnum_UpdatingFinalizing = 7  # Full name alias
    UpdatingFailed = 8
    UpdateStatusEnum_UpdatingFailed = 8  # Full name alias
    UpdatingRestartRequired = 9
    UpdateStatusEnum_UpdatingRestartRequired = 9  # Full name alias
    UpdatingTimedOut = 10
    UpdateStatusEnum_UpdatingTimedOut = 10  # Full name alias


__all__ = [
    "AxisDirection",
    "AxisPolarity",
    "AxisView",
    "ChainType",
    "ColliderType",
    "CollisionType",
    "DeviceClassType",
    "DeviceFamilyType",
    "DevicePairedState",
    "ErgonomicsDataType",
    "ExtraTrackerOffsetType",
    "FingerJointType",
    "GloveProfileType",
    "HandMotion",
    "LicenseStatus",
    "LicenseTermType",
    "LicenseType",
    "LogSeverity",
    "MeasurementCategory",
    "MeasurementType",
    "MeasurementUnit",
    "MessageType",
    "NetSeatState",
    "NodeSettingsFlag",
    "NodeType",
    "ProfileType",
    "SDKReturnCode",
    "SessionType",
    "SetGloveCalibrationReturnCode",
    "Side",
    "SkeletonTargetType",
    "SkeletonType",
    "SystemMessageType",
    "TimecodeFPS",
    "TrackedPoint",
    "TrackerOffsetType",
    "TrackerSystemSettingType",
    "TrackerSystemType",
    "TrackerType",
    "TrackingQuality",
    "UpdateStatusEnum",
]
