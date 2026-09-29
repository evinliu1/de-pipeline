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


class GitHubError(DePipelineError):
    """A GitHub API request failed."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NoFailuresError(DePipelineError):
    """The run has no failed jobs to analyze, for example because it was cancelled."""
