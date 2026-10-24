from enum import StrEnum


class VideoType(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    LIVE = "LIVE"
    UNKNOWN = "UNKNOWN"


class SourceDataType(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    OFFICIAL = "OFFICIAL"
    PROVIDER = "PROVIDER"
    HUMAN = "HUMAN"
    AI_INFERENCE = "AI_INFERENCE"


class AvailabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    RESTRICTED = "RESTRICTED"
    EXPIRED = "EXPIRED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
