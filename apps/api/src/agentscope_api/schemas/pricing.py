from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ModelPricingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    input_price_per_million_tokens: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    output_price_per_million_tokens: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    effective_from: datetime | None = None
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "ModelPricingCreate":
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("effective_to must be later than effective_from")
        return self


class ModelPricingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    provider: str
    model: str
    input_price_per_million_tokens: Decimal
    output_price_per_million_tokens: Decimal
    currency: str
    source_url: str | None
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime
    custom: bool
