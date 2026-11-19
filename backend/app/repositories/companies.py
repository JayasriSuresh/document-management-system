"""
Company and Branch repository for administrative management and lookup.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Company, CompanyStatus, Branch


class CompanyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, company_id: int) -> Optional[Company]:
        return self.db.query(Company).filter(Company.id == company_id).first()

    def get_by_code(self, code: str) -> Optional[Company]:
        return self.db.query(Company).filter(Company.code == code).first()

    def set_status(self, company_id: int, new_status: CompanyStatus) -> Company:
        company = self.get_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        company.status = new_status
        self.db.commit()
        self.db.refresh(company)
        return company

    def suspend(self, company_id: int) -> Company:
        return self.set_status(company_id, CompanyStatus.SUSPENDED)

    def activate(self, company_id: int) -> Company:
        return self.set_status(company_id, CompanyStatus.ACTIVE)


class BranchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, branch_id: int, company_id: int) -> Optional[Branch]:
        return (
            self.db.query(Branch)
            .filter(Branch.id == branch_id, Branch.company_id == company_id)
            .first()
        )

    def list_for_company(self, company_id: int) -> List[Branch]:
        return (
            self.db.query(Branch)
            .filter(Branch.company_id == company_id)
            .order_by(Branch.name.asc())
            .all()
        )
