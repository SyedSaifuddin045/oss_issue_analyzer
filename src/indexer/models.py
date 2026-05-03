from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UnitType(str, Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    C = "c"
    CPP = "cpp"


class ComplexityMetrics(BaseModel):
    cyclomatic_complexity: int = Field(default=0, ge=0)
    lines_of_code: int = Field(default=0, ge=0)
    cognitive_complexity: int = Field(default=0, ge=0)
    fan_in: int = Field(default=0, ge=0)
    fan_out: int = Field(default=0, ge=0)


class ContributorSignals(BaseModel):
    is_well_documented: bool = False
    has_type_hints: bool = False
    has_tests: bool = False
    is_isolated: bool = False
    has_clear_naming: bool = False


class IndexedUnit(BaseModel):
    id: str
    repo_id: str
    type: UnitType
    path: str
    language: Language
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: Optional[str] = None
    docstring: Optional[str] = None
    code: str
    complexity: ComplexityMetrics
    contributor_signals: ContributorSignals
    code_embedding: list[float]
    doc_embedding: Optional[list[float]] = None
    file_hash: str
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class Repository(BaseModel):
    id: str
    name: str
    path: str
    language: Language
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class Directory(BaseModel):
    id: str
    repo_id: str
    path: str
    name: str
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
