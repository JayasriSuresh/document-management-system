"""
Centralized repositories exporting tenant-scoped data access.
"""

from app.repositories.base import BaseTenantRepository
from app.repositories.documents import DocumentRepository
from app.repositories.invoices import InvoiceRepository
from app.repositories.users import UserRepository
from app.repositories.companies import CompanyRepository, BranchRepository

__all__ = [
    "BaseTenantRepository",
    "DocumentRepository",
    "InvoiceRepository",
    "UserRepository",
    "CompanyRepository",
    "BranchRepository",
]
