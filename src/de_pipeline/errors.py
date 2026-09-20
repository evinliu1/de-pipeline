class DePipelineError(Exception):
    """Base class for expected errors with a message safe to show users."""


class UsageError(DePipelineError):
    """The command was run with the wrong arguments"""


class EnvError(DePipelineError):
    """The env var could not be found"""


class LogFileError(DePipelineError):
    """Error reading file contents"""


class ModelError(DePipelineError):
    """Error from calling the model"""


class DiagnosisError(DePipelineError):
    """Error parsing content into Diagnosis class"""
