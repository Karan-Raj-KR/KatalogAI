# Import all ORM models here so that SQLAlchemy's mapper registry is fully
# populated before any session work begins.  This prevents
# NoReferencedTableError when foreign-key resolution runs at flush time.
from app.models.api_key import APIKey
from app.models.hsn_code import HSNCode
from app.models.ingestion_job import IngestionJob
from app.models.product import Product
from app.models.product_field import ProductField
from app.models.review_item import ReviewItem

__all__ = [
    "APIKey",
    "HSNCode",
    "IngestionJob",
    "Product",
    "ProductField",
    "ReviewItem",
]
