"""Shared FastAPI dependencies.

Endpoints receive their configuration through `SettingsDep` rather than calling
`get_settings()` directly, so tests can substitute configuration through
`app.dependency_overrides` without patching module internals.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]
