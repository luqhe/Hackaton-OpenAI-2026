from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MembershipRole(StrEnum):
    OWNER = "OWNER"
    GUARDIAN = "GUARDIAN"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class FamilyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"


class DeviceLifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class FamilyScope:
    """Authenticated membership capability for exactly one family."""

    account_id: str
    family_id: str
    membership_id: str
    role: MembershipRole


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: str = Field(min_length=3, max_length=254)
    status: AccountStatus
    created_at: datetime


class Family(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1, max_length=120)
    status: FamilyStatus
    created_at: datetime


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    family_id: str
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime


class Child(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family_id: str
    name: str = Field(min_length=1, max_length=120)
    created_at: datetime
