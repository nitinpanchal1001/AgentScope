from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from agentscope_api.models.entities import Role


class OrganizationCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    role: Role | None = None


class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: Role
    created_at: datetime
