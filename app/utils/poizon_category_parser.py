import httpx
from bs4 import BeautifulSoup
from typing import List, Set
import re
import asyncio
import json

async def extract_product_links_from_category(category_url: str) -> List[str]:
    """
    Извлекает все ссылки на товары из страницы категории
    Аналогично check_links_categories из примера
    """
    product_links = set()
    
    base_domain = 'https://thepoizon.ru'
    if 'thepoizon.ru' not in category_url:
        base_domain = 'https://www.poizon.com'
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8',
            'Referer': f'{base_domain}/',
        }
        
        page = 1
        max_pages = 50  # Ограничение для безопасности
        
        while page <= max_pages:
            # Формируем URL с пагинацией
            if '?' in category_url:
                page_url = f"{category_url}&page={page}"
            else:
                page_url = f"{category_url}?page={page}"
            
            try:
                print(f"Fetching category page {page}: {page_url}")
                response = await client.get(page_url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем ссылки на товары в __NEXT_DATA__
                next_data_script = soup.find('script', id='__NEXT_DATA__')
                found_links = False
                
                if next_data_script:
                    try:
                        next_data = json.loads(next_data_script.string)
                        props = next_data.get('props', {})
                        page_props = props.get('pageProps', {})
                        
                        # Ищем список товаров
                        products = (page_props.get('products') or 
                                  page_props.get('goodsList') or
                                  page_props.get('items') or
                                  page_props.get('productList'))
                        
                        if products and isinstance(products, list):
                            for product in products:
                                product_url = (product.get('url') or 
                                             product.get('link') or
                                             product.get('href') or
                                             product.get('productUrl'))
                                
                                if product_url:
                                    # Нормализуем URL
                                    if product_url.startswith('/'):
                                        product_url = base_domain + product_url
                                    elif not product_url.startswith('http'):
                                        continue
                                    
                                    product_links.add(product_url)
                                    found_links = True
                    except Exception as e:
                        print(f"Error parsing __NEXT_DATA__: {e}")
                
                # Если не нашли в __NEXT_DATA__, ищем в HTML
                if not found_links:
                    # Селекторы для ссылок на товары (аналогично примеру)
                    link_selectors = [
                        'div.GoodsList_goodsList__hPoCW > a',
                        'a[href*="/product/"]',
                        '.goods-item a',
                        '.product-item a',
                        '[class*="goods"] a[href*="product"]',
                        '[class*="product"] a[href*="product"]'
                    ]
                    
                    for selector in link_selectors:
                        links = soup.select(selector)
                        for link in links:
                            href = link.get('href')
                            if href and '/product/' in href:
                                if href.startswith('/'):
                                    href = base_domain + href
                                elif not href.startswith('http'):
                                    continue
                                
                                product_links.add(href)
                                found_links = True
                        
                        if found_links:
                            break
                
                # Проверяем, есть ли следующая страница
                # Ищем кнопку "следующая" или пагинацию
                has_next_page = False
                
                # Проверяем в __NEXT_DATA__
                if next_data_script:
                    try:
                        next_data = json.loads(next_data_script.string)
                        props = next_data.get('props', {})
                        page_props = props.get('pageProps', {})
                        
                        pagination = page_props.get('pagination') or page_props.get('pageInfo')
                        if pagination:
                            current = pagination.get('current', page)
                            total = pagination.get('total', pagination.get('totalPages'))
                            if total and current < total:
                                has_next_page = True
                    except:
                        pass
                
                # Проверяем в HTML
                if not has_next_page:
                    next_button = soup.select_one('li.ant-pagination-next:not([aria-disabled="true"])')
                    if next_button:
                        has_next_page = True
                
                if not found_links or not has_next_page:
                    print(f"No more pages or products found. Total links collected: {len(product_links)}")
                    break
                
                page += 1
                await asyncio.sleep(1)  # Задержка между запросами
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    print(f"Page {page} not found, stopping pagination")
                    break
                else:
                    print(f"HTTP error on page {page}: {e.response.status_code}")
                    page += 1
                    continue
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                page += 1
                continue
    
    return list(product_links)

