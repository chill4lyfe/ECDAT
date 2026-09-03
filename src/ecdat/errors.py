class ECDATError(Exception):
    """Base exception for expected platform errors."""


class ContractViolation(ECDATError):
    """Raised when a plugin violates a platform contract."""


class UnsupportedTarget(ECDATError):
    """Raised when a scanner cannot process a target type."""
