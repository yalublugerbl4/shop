from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from app.middleware.telegram_auth import get_current_user
from app.db import queries

router = APIRouter()


@router.get("")
async def get_products(
    category: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """Получить список товаров"""
    products = queries.get_products(category=category, season=season, q=q)
    return products


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Получить товар по ID"""
    product = queries.get_product_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Product not found"}}
        )
    
    return product
