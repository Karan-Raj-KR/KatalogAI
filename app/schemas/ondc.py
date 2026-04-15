"""
ONDC (Open Network for Digital Commerce) payload schemas.

These mirror the ONDC protocol's Item / Descriptor / Price structures so
that a ProductOut can be serialised into a network-ready ONDC catalogue
item without any further transformation in the caller.

Reference: https://docs.google.com/document/d/1brvcltG_DagZ3kGr1ZZub94_bBMIH_2yRGJZOLNFpzk
"""

from pydantic import BaseModel, Field


class ONDCDescriptor(BaseModel):
    name: str
    short_desc: str | None = None
    long_desc: str | None = None
    images: list[str] = Field(default_factory=list)


class ONDCQuantity(BaseModel):
    count: int | None = None
    measure: dict[str, str] | None = None  # {"unit": "kg", "value": "1"}


class ONDCPrice(BaseModel):
    currency: str = "INR"
    value: str  # string per ONDC spec, e.g. "28.00"
    maximum_value: str | None = None  # MRP


class ONDCItem(BaseModel):
    """Single ONDC catalogue item derived from a ProductOut."""

    id: str
    descriptor: ONDCDescriptor
    quantity: ONDCQuantity | None = None
    price: ONDCPrice
    category_id: str | None = None  # ONDC category code
    fulfillment_id: str | None = None
    tags: list[dict[str, str]] = Field(default_factory=list)


class ONDCCatalogueOut(BaseModel):
    """Top-level ONDC catalogue payload (one item per ingestion result)."""

    bpp_descriptor: dict[str, str] = Field(default_factory=dict)
    bpp_providers: list[dict] = Field(default_factory=list)
    items: list[ONDCItem] = Field(default_factory=list)
