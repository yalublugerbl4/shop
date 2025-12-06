from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Optional, List
import asyncio
from app.middleware.telegram_auth import get_current_user, require_admin
from app.db import queries
from app.utils.poizon_parser import parse_poizon_product
from app.utils.poizon_category_parser import extract_product_links_from_category

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


class ParsePoizonRequest(BaseModel):
    url: str = Field(..., description="URL товара с thepoizon.ru")
    category: str = Field(..., min_length=1)
    season: Optional[str] = Field(None)
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith('http'):
            raise ValueError('URL must start with http:// or https://')
        return v
    
    @validator('season')
    def validate_season(cls, v):
        if v and v not in ['winter', 'demi', 'all']:
            raise ValueError('season must be one of: winter, demi, all')
        return v


class ParsePoizonBatchRequest(BaseModel):
    urls: List[str] = Field(..., min_items=1, max_items=50, description="Список URL товаров с thepoizon.ru")
    category: str = Field(..., min_length=1)
    season: Optional[str] = Field(None)
    
    @validator('urls')
    def validate_urls(cls, v):
        for url in v:
            if not url.startswith('http'):
                raise ValueError(f'Invalid URL: {url}')
        return v
    
    @validator('season')
    def validate_season(cls, v):
        if v and v not in ['winter', 'demi', 'all']:
            raise ValueError('season must be one of: winter, demi, all')
        return v


@router.post("/parse-poizon")
async def parse_poizon(
    request: ParsePoizonRequest,
    current_user: dict = Depends(get_current_user)
):
    """Парсить товар с thepoizon.ru (только админ)"""
    user = await require_admin(current_user)
    
    # Парсим товар
    try:
        parsed_data = await parse_poizon_product(request.url)
        if not parsed_data:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "PARSE_ERROR", "message": "Не удалось распарсить товар. Проверьте URL и убедитесь, что страница доступна."}}
            )
    except Exception as e:
        error_message = str(e)
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PARSE_ERROR", "message": error_message}}
        )
    
    # Создаем товар в БД
    product_data = {
        'category': request.category,
        'season': request.season,
        'title': parsed_data['title'],
        'description': parsed_data.get('description', ''),
        'price_cents': parsed_data['price_cents'],
        'images_base64': parsed_data.get('images_base64', [])
    }
    
    product = queries.create_product(product_data)
    return {
        "success": True,
        "product": product,
        "message": "Product parsed and created successfully"
    }


@router.post("/parse-poizon-batch")
async def parse_poizon_batch(
    request: ParsePoizonBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """Массовый парсинг товаров с POIZON (только админ)"""
    user = await require_admin(current_user)
    
    results = {
        "success": [],
        "failed": [],
        "total": len(request.urls)
    }
    
    for url in request.urls:
        try:
            parsed = await parse_poizon_product(url)
            if parsed:
                product_data = {
                    'category': request.category,
                    'season': request.season,
                    'title': parsed['title'],
                    'description': parsed.get('description', ''),
                    'price_cents': parsed['price_cents'],
                    'images_base64': parsed.get('images_base64', [])
                }
                product = queries.create_product(product_data)
                results["success"].append({
                    "url": url,
                    "product_id": product['id'],
                    "title": product['title']
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
        
        # Небольшая задержка между запросами
        if len(results["success"]) + len(results["failed"]) < len(request.urls):
            await asyncio.sleep(1)
    
    return results


class ParseCategoryRequest(BaseModel):
    category_url: str = Field(..., description="URL категории на thepoizon.ru")
    category: str = Field(..., min_length=1, description="Категория товара для сохранения в БД")
    season: Optional[str] = Field(None)
    max_products: Optional[int] = Field(50, ge=1, le=200, description="Максимальное количество товаров для парсинга")
    
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
async def parse_category(
    request: ParseCategoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Автоматический парсинг категории - собирает все товары из категории и добавляет в БД
    Аналогично reads_files() из примера
    """
    user = await require_admin(current_user)
    
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
                parsed = await parse_poizon_product(url)
                
                if parsed:
                    product_data = {
                        'category': request.category,
                        'season': request.season,
                        'title': parsed['title'],
                        'description': parsed.get('description', ''),
                        'price_cents': parsed['price_cents'],
                        'images_base64': parsed.get('images_base64', [])
                    }
                    
                    product = queries.create_product(product_data)
                    results["success"].append({
                        "url": url,
                        "product_id": product['id'],
                        "title": product['title']
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
            
            # Задержка между запросами (чтобы не нагружать сайт)
            if idx < len(product_links):
                await asyncio.sleep(2)
        
        results["status"] = "completed"
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        print(f"Error parsing category: {e}")
    
    return results
