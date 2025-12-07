from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Optional
import asyncio
import os
from app.db import queries
from app.utils.poizon_parser import parse_poizon_product
from app.utils.poizon_category_parser import extract_product_links_from_category

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


class ParseCategoryRequest(BaseModel):
    token: str = Field(..., description="Токен для авторизации cron-запроса")
    category_url: str = Field(..., description="URL категории на thepoizon.ru")
    category: str = Field(..., min_length=1, description="Категория товара для сохранения в БД")
    season: Optional[str] = Field(None)
    max_products: Optional[int] = Field(200, ge=1, le=500, description="Максимальное количество товаров для парсинга")
    
    @validator('category_url')
    def validate_category_url(cls, v):
        if not v.startswith('http'):
            raise ValueError('URL must start with http:// or https://')
        if '/product/' in v:
            raise ValueError('URL должен быть категории, а не товара')
        return v
    
    @validator('season')
    def validate_season(cls, v):
        if v and v not in ['winter', 'demi', 'all']:
            raise ValueError('season must be one of: winter, demi, all')
        return v


@router.post("/parse-category")
async def parse_category_cron(request: ParseCategoryRequest):
    """
    Автоматический парсинг категории через cron
    Используется для автоматического парсинга категорий (например, раз в день)
    Требует токен из переменной окружения CRON_TOKEN
    """
    
    cron_token = os.getenv('CRON_TOKEN', '')
    
    if not cron_token or request.token != cron_token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token"}}
        )
    
    results = {
        "total_links_found": 0,
        "success": [],
        "failed": [],
        "status": "in_progress"
    }
    
    try:
        # Шаг 1: Собираем все ссылки на товары из категории
        print(f"Extracting product links from category: {request.category_url}")
        product_links = await extract_product_links_from_category(request.category_url)
        
        results["total_links_found"] = len(product_links)
        print(f"Found {len(product_links)} product links")
        
        if not product_links:
            return {
                **results,
                "status": "completed",
                "message": "Не найдено товаров в категории"
            }
        
        # Ограничиваем количество
        product_links = product_links[:request.max_products]
        
        # Шаг 2: Парсим каждый товар
        print(f"Parsing {len(product_links)} products...")
        
        for idx, url in enumerate(product_links, 1):
            try:
                print(f"Parsing product {idx}/{len(product_links)}: {url[:80]}...")
                
                # Проверяем, существует ли уже товар с таким source_url
                existing_product = queries.get_product_by_source_url(url)
                if existing_product:
                    print(f"  ⏭️ Product already exists, skipping: {url[:80]}...")
                    results["success"].append({
                        "url": url,
                        "product_id": existing_product['id'],
                        "title": existing_product['title'],
                        "status": "already_exists"
                    })
                    continue
                
                parsed = await parse_poizon_product(url)
                
                if parsed:
                    product_data = {
                        'category': request.category,
                        'season': request.season,
                        'title': parsed['title'],
                        'description': parsed.get('description', ''),
                        'price_cents': parsed['price_cents'],
                        'images_base64': parsed.get('images_base64', []),
                        'source_url': url
                    }
                    
                    product = queries.create_product(product_data)
                    results["success"].append({
                        "url": url,
                        "product_id": product['id'],
                        "title": product['title'],
                        "status": "created"
                    })
                else:
                    results["failed"].append({
                        "url": url,
                        "error": "Failed to parse product"
                    })
            
            except Exception as e:
                results["failed"].append({
                    "url": url,
                    "error": str(e)
                })
                print(f"Error parsing {url}: {e}")
            
            # Задержка между запросами
            if idx < len(product_links):
                await asyncio.sleep(2)
        
        results["status"] = "completed"
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        print(f"Error parsing category: {e}")
    
    return results

