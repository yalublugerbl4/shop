from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from app.middleware.telegram_auth import get_current_user, require_admin
from app.db import queries

router = APIRouter()


class CreateProductRequest(BaseModel):
    category: str = Field(..., min_length=1)
    season: Optional[str] = Field(None)
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    price_cents: int = Field(..., gt=0)
    images_base64: List[str] = Field(default_factory=list, max_items=3)
    
    @validator('season')
    def validate_season(cls, v):
        if v and v not in ['winter', 'demi', 'all']:
            raise ValueError('season must be one of: winter, demi, all')
        return v


class UpdateProductRequest(BaseModel):
    category: Optional[str] = Field(None, min_length=1)
    season: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    price_cents: Optional[int] = Field(None, gt=0)
    images_base64: Optional[List[str]] = Field(None, max_items=3)
    
    @validator('season')
    def validate_season(cls, v):
        if v and v not in ['winter', 'demi', 'all']:
            raise ValueError('season must be one of: winter, demi, all')
        return v


@router.post("/products")
async def create_product(
    product_data: CreateProductRequest,
    current_user: dict = Depends(get_current_user)
):
    """Создать товар (только админ)"""
    user = await require_admin(current_user)
    
    product = queries.create_product(product_data.dict(exclude_none=True))
    return product


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    product_data: UpdateProductRequest,
    current_user: dict = Depends(get_current_user)
):
    """Обновить товар (только админ)"""
    user = await require_admin(current_user)
    
    updates = product_data.dict(exclude_none=True)
    product = queries.update_product(product_id, updates)
    
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Product not found"}}
        )
    
    return product


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Удалить товар (только админ)"""
    user = await require_admin(current_user)
    
    success = queries.delete_product(product_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Product not found"}}
        )
    
    return {"success": True}
