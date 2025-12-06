import httpx
from bs4 import BeautifulSoup
import base64
from typing import Optional, Dict, Any
import re

async def download_image_to_base64(url: str, client: httpx.AsyncClient) -> Optional[str]:
    """Скачивает изображение и конвертирует в base64"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.poizon.com/'
        }
        response = await client.get(url, headers=headers, timeout=10.0)
        if response.status_code == 200:
            img_base64 = base64.b64encode(response.content).decode('utf-8')
            # Определяем тип изображения
            content_type = response.headers.get('content-type', 'image/jpeg')
            return f"data:{content_type};base64,{img_base64}"
    except Exception as e:
        print(f"Error downloading image {url}: {e}")
    return None

async def parse_poizon_product(url: str) -> Optional[Dict[str, Any]]:
    """
    Парсит товар с POIZON по URL
    Возвращает данные товара для создания в БД
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.poizon.com/',
            }
            
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Парсинг данных (адаптировано под структуру POIZON)
            title = None
            price = None
            images = []
            description = ""
            
            # Поиск названия товара
            # Варианты селекторов для POIZON
            title_selectors = [
                'h1.product-title',
                'h1.goods-title',
                '.product-name',
                '.goods-name',
                'h1',
                '[class*="title"]',
                '[class*="name"]'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 5:
                        break
            
            # Если не нашли через селекторы, ищем в мета-тегах
            if not title:
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    title = meta_title.get('content', '').strip()
            
            # Поиск цены
            price_selectors = [
                '.price',
                '.goods-price',
                '.product-price',
                '[class*="price"]',
                '[data-price]'
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Извлекаем число из цены (удаляем символы валют)
                    price_text_clean = re.sub(r'[^\d.,]', '', price_text.replace(',', ''))
                    if price_text_clean:
                        try:
                            # Предполагаем, что цена в юанях, конвертируем в рубли (примерно 12-13 руб за юань)
                            price_yuan = float(price_text_clean)
                            price_rub = int(price_yuan * 12.5 * 100)  # в копейках
                            price = price_rub
                            break
                        except:
                            pass
            
            # Поиск изображений
            # Сначала пробуем найти основные изображения товара
            img_selectors = [
                '.product-image img',
                '.goods-image img',
                '.swiper-slide img',
                '[class*="product"] img[src*="http"]',
                '[class*="goods"] img[src*="http"]'
            ]
            
            found_urls = set()
            for selector in img_selectors:
                img_tags = soup.select(selector)
                for img in img_tags[:5]:  # максимум 5 для выбора лучших
                    img_url = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-lazy')
                    if img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = 'https://www.poizon.com' + img_url
                        if img_url.startswith('http') and img_url not in found_urls:
                            found_urls.add(img_url)
            
            # Также проверяем Open Graph изображение
            og_image = soup.find('meta', property='og:image')
            if og_image:
                img_url = og_image.get('content', '').strip()
                if img_url and img_url not in found_urls:
                    found_urls.add(img_url)
            
            # Скачиваем и конвертируем изображения (максимум 3)
            for img_url in list(found_urls)[:3]:
                img_base64 = await download_image_to_base64(img_url, client)
                if img_base64:
                    images.append(img_base64)
            
            # Описание
            desc_selectors = [
                '.product-description',
                '.goods-description',
                '.product-detail',
                '[class*="description"]',
                '[class*="detail"]'
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True, separator='\n')
                    if description and len(description) > 10:
                        break
            
            # Если не нашли описание, используем мета-описание
            if not description:
                meta_desc = soup.find('meta', property='og:description')
                if meta_desc:
                    description = meta_desc.get('content', '').strip()
            
            if not title:
                print("Failed to find product title")
                return None
            
            if not price or price <= 0:
                print(f"Failed to find valid price (found: {price})")
                return None
            
            return {
                'title': title[:500],  # Ограничиваем длину
                'price_cents': price,
                'description': description[:2000] if description else '',  # Ограничиваем длину
                'images_base64': images
            }
            
    except httpx.HTTPStatusError as e:
        print(f"HTTP error parsing POIZON product: {e.response.status_code}")
        return None
    except Exception as e:
        print(f"Error parsing POIZON product: {e}")
        import traceback
        traceback.print_exc()
        return None

