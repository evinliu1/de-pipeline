from enum import StrEnum

from pydantic import BaseModel, Field


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Evidence(BaseModel):
    excerpt: str
    explanation: str


class Diagnosis(BaseModel):
    summary: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    fix_steps: list[str]
    confidence: Confidence = Field(min_length=1)
