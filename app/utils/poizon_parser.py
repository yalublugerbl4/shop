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
            'Referer': 'https://thepoizon.ru/'
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
    Парсит товар с thepoizon.ru по URL
    Возвращает данные товара для создания в БД
    """
    try:
        # Проверяем, что URL валидный
        if not url or not url.startswith('http'):
            raise Exception("Некорректный URL. URL должен начинаться с http:// или https://")
        
        # Определяем базовый домен для referer
        if 'thepoizon.ru' in url:
            base_domain = 'https://thepoizon.ru'
        elif 'poizon.com' in url:
            base_domain = 'https://www.poizon.com'
        else:
            base_domain = 'https://thepoizon.ru'
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': f'{base_domain}/',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }
            
            print(f"Fetching thepoizon.ru URL: {url}")
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            # Проверяем, что получили HTML
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type:
                raise Exception(f"Получен не HTML-контент (content-type: {content_type}). Проверьте URL товара.")
            
            print(f"Received HTML, length: {len(response.text)}")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Парсинг данных (адаптировано под структуру POIZON)
            title = None
            price = None
            images = []
            description = ""
            
            # Поиск названия товара
            # Варианты селекторов для thepoizon.ru
            title_selectors = [
                'h1.product-title',
                'h1.goods-title',
                '.product-name',
                '.goods-name',
                '.product__title',
                '.product-title',
                '.title',
                'h1[class*="product"]',
                'h1[class*="title"]',
                'h1',
                '[class*="title"][class*="product"]',
                '[class*="name"]',
                'title'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 5:
                        print(f"Found title with selector '{selector}': {title[:50]}...")
                        break
            
            # Если не нашли через селекторы, ищем в мета-тегах
            if not title:
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    title = meta_title.get('content', '').strip()
                    print(f"Found title from meta: {title[:50]}...")
                
                # Пробуем из тега title
                if not title:
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        # Убираем стандартные суффиксы сайта
                        title = re.sub(r'\s*[-|]\s*thepoizon.*$', '', title, flags=re.IGNORECASE)
                        title = re.sub(r'\s*[-|]\s*POIZON.*$', '', title, flags=re.IGNORECASE)
                        title = re.sub(r'\s*[-|]\s*得物.*$', '', title, flags=re.IGNORECASE)
                        print(f"Found title from <title> tag: {title[:50]}...")
            
            # Поиск цены
            price_selectors = [
                '.product-price',
                '.price',
                '.goods-price',
                '.product__price',
                '.price-value',
                '.product-price-value',
                '[class*="price"]',
                '[class*="Price"]',
                '[class*="PRICE"]',
                '[data-price]',
                '[class*="amount"]',
                '[class*="Amount"]',
                '[class*="cost"]',
                '[class*="Cost"]',
                '.current-price',
                '.price-current',
                '.price__current',
                '[itemprop="price"]',
                '[data-value]',
                '.sale-price',
                '.final-price'
            ]
            
            for selector in price_selectors:
                price_elems = soup.select(selector)
                for price_elem in price_elems:
                    price_text = price_elem.get_text(strip=True)
                    if not price_text:
                        # Пробуем атрибуты
                        price_text = price_elem.get('data-price') or price_elem.get('data-value') or price_elem.get('content') or ''
                    
                    if price_text:
                        # Извлекаем число из цены (удаляем символы валют)
                        # Поддерживаем разные форматы: "12 345 ₽", "12345₽", "12,345", "12.345"
                        price_text_clean = re.sub(r'[^\d.,]', '', price_text.replace(',', '').replace(' ', ''))
                        if price_text_clean:
                            try:
                                price_num = float(price_text_clean.replace(',', '.'))
                                # Проверяем разумность цены (от 100 рублей до 1 млн)
                                if 100 <= price_num <= 1000000:
                                    price_rub = int(price_num * 100)  # в копейках
                                    price = price_rub
                                    print(f"Found price with selector '{selector}': {price_text} -> {price_rub} копеек")
                                    break
                                elif price_num < 100:  # Если цена меньше 100, возможно это юани
                                    price_rub = int(price_num * 12.5 * 100)  # в копейках
                                    if price_rub >= 10000:  # Проверяем разумность после конвертации
                                        price = price_rub
                                        print(f"Found price (yuan->rub) with selector '{selector}': {price_text} -> {price_rub} копеек")
                                        break
                            except Exception as e:
                                print(f"Error parsing price '{price_text}': {e}")
                                pass
                if price:
                    break
            
            # Также пробуем найти цену в JSON-LD или других мета-тегах
            if not price:
                # Ищем JSON-LD с данными товара
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                for json_ld in json_ld_scripts:
                    try:
                        import json
                        data = json.loads(json_ld.string)
                        # Поддерживаем как объект, так и массив
                        if isinstance(data, list) and len(data) > 0:
                            data = data[0]
                        
                        if isinstance(data, dict):
                            offers = data.get('offers', {})
                            if isinstance(offers, dict) and 'price' in offers:
                                price_num = float(offers['price'])
                                if 100 <= price_num <= 1000000:
                                    price_rub = int(price_num * 100)
                                    price = price_rub
                                    print(f"Found price in JSON-LD offers: {price_rub} копеек")
                                    break
                                elif price_num < 100:
                                    price_rub = int(price_num * 12.5 * 100)
                                    if price_rub >= 10000:
                                        price = price_rub
                                        print(f"Found price (yuan->rub) in JSON-LD: {price_rub} копеек")
                                        break
                    except Exception as e:
                        print(f"Error parsing JSON-LD: {e}")
                        pass
            
            # Если все еще не нашли, ищем в meta-тегах
            if not price:
                meta_price = soup.find('meta', property='product:price:amount')
                if meta_price:
                    try:
                        price_num = float(meta_price.get('content', ''))
                        if 100 <= price_num <= 1000000:
                            price_rub = int(price_num * 100)
                            price = price_rub
                            print(f"Found price in meta product:price:amount: {price_rub} копеек")
                    except:
                        pass
            
            # Последняя попытка - ищем все числа на странице, которые похожи на цены
            if not price:
                # Ищем числа от 1000 до 100000 с символом рубля рядом
                price_patterns = [
                    re.compile(r'(\d{1,3}(?:\s?\d{3})*(?:[.,]\d{2})?)\s*[₽₴]', re.IGNORECASE),
                    re.compile(r'(\d{1,3}(?:\s?\d{3})*(?:[.,]\d{2})?)\s*(?:руб|RUB)', re.IGNORECASE),
                    re.compile(r'price["\']?\s*[:=]\s*["\']?(\d{1,3}(?:\s?\d{3})*(?:[.,]\d{2})?)', re.IGNORECASE),
                ]
                
                page_text = soup.get_text()
                for pattern in price_patterns:
                    matches = pattern.findall(page_text)
                    for match in matches[:5]:  # Проверяем первые 5 совпадений
                        try:
                            price_text_clean = match.replace(' ', '').replace(',', '.')
                            price_num = float(price_text_clean)
                            if 1000 <= price_num <= 100000:
                                price_rub = int(price_num * 100)
                                price = price_rub
                                print(f"Found price with regex pattern: {match} -> {price_rub} копеек")
                                break
                        except:
                            pass
                    if price:
                        break
            
            # Поиск изображений
            # Сначала пробуем найти основные изображения товара
            img_selectors = [
                '.product-gallery img',
                '.product-images img',
                '.product-image img',
                '.goods-image img',
                '.product__image img',
                '.swiper-slide img',
                '.slider img',
                '[class*="gallery"] img',
                '[class*="product"] img[src*="http"]',
                '[class*="goods"] img[src*="http"]',
                'img[src*="goods"]',
                'img[src*="product"]',
                'img[alt*="product"]'
            ]
            
            found_urls = set()
            for selector in img_selectors:
                img_tags = soup.select(selector)
                for img in img_tags[:5]:  # максимум 5 для выбора лучших
                    img_url = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-lazy') or img.get('data-url')
                    if img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = base_domain + img_url
                        if img_url.startswith('http') and img_url not in found_urls:
                            found_urls.add(img_url)
            
            # Также проверяем Open Graph изображение
            og_image = soup.find('meta', property='og:image')
            if og_image:
                img_url = og_image.get('content', '').strip()
                if img_url and img_url not in found_urls:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = base_domain + img_url
                    found_urls.add(img_url)
            
            print(f"Found {len(found_urls)} image URLs")
            
            # Скачиваем и конвертируем изображения (максимум 3)
            for img_url in list(found_urls)[:3]:
                img_base64 = await download_image_to_base64(img_url, client)
                if img_base64:
                    images.append(img_base64)
            
            print(f"Downloaded {len(images)} images")
            
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
                        print(f"Found description with selector '{selector}'")
                        break
            
            # Если не нашли описание, используем мета-описание
            if not description:
                meta_desc = soup.find('meta', property='og:description')
                if meta_desc:
                    description = meta_desc.get('content', '').strip()
                    print("Found description from meta")
            
            if not title:
                raise Exception("Не удалось найти название товара. Возможно, структура страницы изменилась или товар недоступен.")
            
            if not price or price <= 0:
                # Дополнительная отладочная информация
                print("DEBUG: Price selectors found:")
                for selector in ['.product-price', '.price', '[class*="price"]', '[data-price]']:
                    elems = soup.select(selector)
                    for elem in elems[:3]:
                        print(f"  {selector}: {elem.get_text(strip=True)[:100]} (attrs: {dict(list(elem.attrs.items())[:3])})")
                
                raise Exception(f"Не удалось найти цену товара. Проверьте формат страницы thepoizon.ru. Название товара найдено: '{title[:50]}...'")
            
            print(f"Successfully parsed product: {title[:50]}... (price: {price} копеек)")
            
            return {
                'title': title[:500],  # Ограничиваем длину
                'price_cents': price,
                'description': description[:2000] if description else '',  # Ограничиваем длину
                'images_base64': images
            }
            
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: Не удалось загрузить страницу thepoizon.ru. Сайт может блокировать запросы или URL неверный."
        print(error_msg)
        raise Exception(error_msg)
    except httpx.RequestError as e:
        error_msg = f"Ошибка сети: Не удалось подключиться к thepoizon.ru. Проверьте подключение к интернету."
        print(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = str(e)
        print(f"Parse error: {error_msg}")
        import traceback
        traceback.print_exc()
        raise Exception(error_msg)
