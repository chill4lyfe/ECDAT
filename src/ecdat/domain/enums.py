from enum import StrEnum


class TargetKind(StrEnum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    CONTAINER_IMAGE = "container_image"
    BINARY = "binary"
    ENDPOINT = "endpoint"
    BOM = "bom"


class AssetType(StrEnum):
    ALGORITHM = "algorithm"
    KEY = "key"
    CERTIFICATE = "certificate"
    PROTOCOL = "protocol"
    LIBRARY = "library"
    HARDWARE_MODULE = "hardware_module"
    CLOUD_CRYPTO_SERVICE = "cloud_crypto_service"
    CRYPTO_USAGE = "crypto_usage"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskPriority(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    CRITICAL = "critical"


class QuantumPosture(StrEnum):
    VULNERABLE = "vulnerable"
    REDUCED_MARGIN = "reduced_margin"
    RESISTANT = "resistant"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


class GraphNodeType(StrEnum):
    APPLICATION = "application"
    SERVICE = "service"
    REPOSITORY = "repository"
    CONTAINER = "container"
    LIBRARY = "library"
    CERTIFICATE = "certificate"
    KEY = "key"
    ALGORITHM = "algorithm"
    PROTOCOL = "protocol"
    DATA_CLASS = "data_class"
    BUSINESS_FUNCTION = "business_function"
    INFRASTRUCTURE = "infrastructure"
    CRYPTO_ASSET = "crypto_asset"


class GraphEdgeType(StrEnum):
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    USES = "uses"
    PROTECTS = "protects"
    AUTHENTICATES_WITH = "authenticates_with"
    SIGNED_BY = "signed_by"
    ISSUED_BY = "issued_by"
    IMPLEMENTS = "implements"
    CONNECTS_TO = "connects_to"
    BLOCKS_MIGRATION_OF = "blocks_migration_of"
    SHARES_CRYPTO_WITH = "shares_crypto_with"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
