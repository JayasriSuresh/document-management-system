"""
Customer Management Router (Module 13).
Supports B2B customers (with validated GSTIN and PAN) and B2C customers.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.audit import events
from app.audit.service import audit
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import CUSTOMER_VIEW, CUSTOMER_MANAGE
from app.context import AuthContext, MasterAdminContext, get_auth_context
from app.database import get_db
from app.models import Customer, CustomerAddress
from app.schemas import (
    CustomerCreate,
    CustomerUpdate,
    CustomerOut,
    CustomerAddressCreate,
    CustomerAddressOut,
)
from app.services.gstin_validator import validate_gstin, INDIAN_GST_STATE_CODES

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=List[CustomerOut])
@requires(CUSTOMER_VIEW)
def list_customers(
    search: Optional[str] = Query(default=None, description="Search by customer name, GSTIN, PAN, or email"),
    is_b2c: Optional[bool] = Query(default=None, description="Filter by B2B or B2C status"),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List customers scoped strictly to the current tenant company."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if CUSTOMER_VIEW not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    query = db.query(Customer).filter(Customer.company_id == ctx.company_id, Customer.is_active == True)

    if is_b2c is not None:
        query = query.filter(Customer.is_b2c == is_b2c)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (Customer.name.ilike(term))
            | (Customer.display_name.ilike(term))
            | (Customer.gstin.ilike(term))
            | (Customer.pan.ilike(term))
            | (Customer.email.ilike(term))
        )

    return query.order_by(Customer.name.asc()).all()


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
@requires(CUSTOMER_MANAGE)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new customer (B2B or B2C) for the company."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if CUSTOMER_MANAGE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    cleaned_gstin = data.gstin.strip().upper() if data.gstin else None
    derived_pan = data.pan.strip().upper() if data.pan else None

    if cleaned_gstin:
        is_valid, err_msg = validate_gstin(cleaned_gstin)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)
        # PAN is characters 2 to 12 in GSTIN
        if not derived_pan:
            derived_pan = cleaned_gstin[2:12]

    is_b2c = data.is_b2c or (cleaned_gstin is None)

    customer = Customer(
        company_id=ctx.company_id,
        name=data.name.strip(),
        display_name=data.display_name.strip() if data.display_name else None,
        gstin=cleaned_gstin,
        pan=derived_pan,
        email=data.email.strip() if data.email else None,
        phone=data.phone.strip() if data.phone else None,
        is_b2c=is_b2c,
        is_active=True,
    )
    db.add(customer)
    db.flush()

    # Optional initial billing address
    if data.billing_address:
        b = data.billing_address
        b_addr = CustomerAddress(
            customer_id=customer.id,
            address_type="billing",
            address_line1=b.address_line1.strip(),
            address_line2=b.address_line2.strip() if b.address_line2 else None,
            city=b.city.strip(),
            state_code=b.state_code.strip().zfill(2),
            state_name=INDIAN_GST_STATE_CODES.get(b.state_code.strip().zfill(2), b.state_name.strip()),
            pincode=b.pincode.strip(),
            is_default=True,
        )
        db.add(b_addr)

    # Optional initial shipping address
    if data.shipping_address:
        s = data.shipping_address
        s_addr = CustomerAddress(
            customer_id=customer.id,
            address_type="shipping",
            address_line1=s.address_line1.strip(),
            address_line2=s.address_line2.strip() if s.address_line2 else None,
            city=s.city.strip(),
            state_code=s.state_code.strip().zfill(2),
            state_name=INDIAN_GST_STATE_CODES.get(s.state_code.strip().zfill(2), s.state_name.strip()),
            pincode=s.pincode.strip(),
            is_default=True,
        )
        db.add(s_addr)

    db.commit()
    db.refresh(customer)

    audit.record_event(
        db=db,
        action=events.CUSTOMER_CREATE,
        auth_context=ctx,
        object_type=events.ObjectType.CUSTOMER.value,
        object_id=customer.id,
        metadata={"customer_name": customer.name, "is_b2c": customer.is_b2c},
    )

    return customer


@router.get("/{customer_id}", response_model=CustomerOut)
@requires(CUSTOMER_VIEW)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve customer details including all associated addresses."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if CUSTOMER_VIEW not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    customer = (
        db.query(Customer)
        .filter(Customer.company_id == ctx.company_id, Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    return customer


@router.put("/{customer_id}", response_model=CustomerOut)
@requires(CUSTOMER_MANAGE)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update customer master data."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if CUSTOMER_MANAGE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    customer = (
        db.query(Customer)
        .filter(Customer.company_id == ctx.company_id, Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if data.name is not None:
        customer.name = data.name.strip()
    if data.display_name is not None:
        customer.display_name = data.display_name.strip()
    if data.gstin is not None:
        if data.gstin.strip():
            cleaned_gstin = data.gstin.strip().upper()
            is_valid, err_msg = validate_gstin(cleaned_gstin)
            if not is_valid:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)
            customer.gstin = cleaned_gstin
            customer.pan = cleaned_gstin[2:12]
        else:
            customer.gstin = None
    if data.pan is not None:
        customer.pan = data.pan.strip().upper() if data.pan else None
    if data.email is not None:
        customer.email = data.email.strip() if data.email else None
    if data.phone is not None:
        customer.phone = data.phone.strip() if data.phone else None
    if data.is_b2c is not None:
        customer.is_b2c = data.is_b2c
    if data.is_active is not None:
        customer.is_active = data.is_active

    db.commit()
    db.refresh(customer)

    audit.record_event(
        db=db,
        action=events.CUSTOMER_UPDATE,
        auth_context=ctx,
        object_type=events.ObjectType.CUSTOMER.value,
        object_id=customer.id,
    )

    return customer


@router.post("/{customer_id}/addresses", response_model=CustomerAddressOut, status_code=status.HTTP_201_CREATED)
@requires(CUSTOMER_MANAGE)
def add_customer_address(
    customer_id: int,
    data: CustomerAddressCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Add a new billing or shipping address for an existing customer."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if CUSTOMER_MANAGE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    customer = (
        db.query(Customer)
        .filter(Customer.company_id == ctx.company_id, Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    state_code = data.state_code.strip().zfill(2)
    state_name = INDIAN_GST_STATE_CODES.get(state_code, data.state_name.strip())

    if data.is_default:
        db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == customer.id,
            CustomerAddress.address_type == data.address_type,
            CustomerAddress.is_default == True,
        ).update({"is_default": False})

    addr = CustomerAddress(
        customer_id=customer.id,
        address_type=data.address_type,
        address_line1=data.address_line1.strip(),
        address_line2=data.address_line2.strip() if data.address_line2 else None,
        city=data.city.strip(),
        state_code=state_code,
        state_name=state_name,
        pincode=data.pincode.strip(),
        is_default=data.is_default,
    )
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return addr
