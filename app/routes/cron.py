from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import os
from app.db import queries
from app.utils.poizon_parser import parse_poizon_product

router = APIRouter()


class UpdatePricesRequest(BaseModel):
    token: str = Field(..., description="Токен для авторизации cron-запроса")
    max_products: Optional[int] = Field(100, ge=1, le=1000, description="Максимальное количество товаров для обновления")


@router.post("/update-prices")
async def update_prices(request: UpdatePricesRequest):
    """
    Обновление цен и размеров для всех товаров с source_url
    Используется для cron-задач (раз в сутки)
    Требует токен из переменной окружения CRON_TOKEN
    """
    cron_token = os.getenv('CRON_TOKEN', '')
    
    if not cron_token or request.token != cron_token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token"}}
        )
    
    results = {
        "total_products": 0,
        "updated": [],
        "failed": [],
        "status": "in_progress"
    }
    
    try:
        # Получаем все товары с source_url
        products = queries.get_all_products_with_source_url()
        results["total_products"] = len(products)
        
        if not products:
            return {
                **results,
                "status": "completed",
                "message": "Нет товаров для обновления"
            }
        
        # Ограничиваем количество
        products = products[:request.max_products]
        
        print(f"Updating prices for {len(products)} products...")
        
        for idx, product in enumerate(products, 1):
            try:
                print(f"Updating product {idx}/{len(products)}: {product['title'][:50]}...")
                source_url = product['source_url']
                
                # Парсим товар заново
                parsed = await parse_poizon_product(source_url)
                
                if parsed:
                    # Обновляем только цену и описание (размеры и цены)
                    updates = {
                        'price_cents': parsed['price_cents'],
                        'description': parsed.get('description', '')
                    }
                    
                    updated_product = queries.update_product(product['id'], updates)
                    
                    if updated_product:
                        results["updated"].append({
                            "product_id": product['id'],
                            "title": product['title'],
                            "new_price": parsed['price_cents']
                        })
                    else:
                        results["failed"].append({
                            "product_id": product['id'],
                            "title": product['title'],
                            "error": "Failed to update in database"
                        })
                else:
                    results["failed"].append({
                        "product_id": product['id'],
                        "title": product['title'],
                        "error": "Failed to parse product"
                    })
            
            except Exception as e:
                results["failed"].append({
                    "product_id": product['id'],
                    "title": product['title'],
                    "error": str(e)
                })
                print(f"Error updating {product['source_url']}: {e}")
            
            # Задержка между запросами
            if idx < len(products):
                await asyncio.sleep(2)
        
        results["status"] = "completed"
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        print(f"Error updating prices: {e}")
    
    return results

