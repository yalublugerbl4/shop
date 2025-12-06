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
        # Проверяем, что URL валидный
        if not url or not url.startswith('http'):
            raise Exception("Некорректный URL. URL должен начинаться с http:// или https://")
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.poizon.com/',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }
            
            print(f"Fetching POIZON URL: {url}")
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
            # Варианты селекторов для POIZON
            title_selectors = [
                'h1.product-title',
                'h1.goods-title',
                '.product-name',
                '.goods-name',
                'h1',
                '[class*="title"]',
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
                        title = re.sub(r'\s*[-|]\s*POIZON.*$', '', title, flags=re.IGNORECASE)
                        title = re.sub(r'\s*[-|]\s*得物.*$', '', title, flags=re.IGNORECASE)
                        print(f"Found title from <title> tag: {title[:50]}...")
            
            # Поиск цены
            price_selectors = [
                '.price',
                '.goods-price',
                '.product-price',
                '[class*="price"]',
                '[data-price]',
                '[class*="Price"]',
                '[class*="amount"]'
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
                            print(f"Found price with selector '{selector}': {price_text} -> {price_rub} копеек")
                            break
                        except:
                            pass
            
            # Также пробуем найти цену в JSON-LD или других мета-тегах
            if not price:
                # Ищем JSON-LD с данными товара
                json_ld = soup.find('script', type='application/ld+json')
                if json_ld:
                    try:
                        import json
                        data = json.loads(json_ld.string)
                        if isinstance(data, dict):
                            offers = data.get('offers', {})
                            if isinstance(offers, dict) and 'price' in offers:
                                price_yuan = float(offers['price'])
                                price_rub = int(price_yuan * 12.5 * 100)
                                price = price_rub
                                print(f"Found price in JSON-LD: {price_rub} копеек")
                    except:
                        pass
            
            # Поиск изображений
            # Сначала пробуем найти основные изображения товара
            img_selectors = [
                '.product-image img',
                '.goods-image img',
                '.swiper-slide img',
                '[class*="product"] img[src*="http"]',
                '[class*="goods"] img[src*="http"]',
                'img[src*="goods"]',
                'img[src*="product"]'
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
                            img_url = 'https://www.poizon.com' + img_url
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
                        img_url = 'https://www.poizon.com' + img_url
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
                raise Exception(f"Не удалось найти цену товара. Проверьте формат страницы POIZON.")
            
            print(f"Successfully parsed product: {title[:50]}... (price: {price} копеек)")
            
            return {
                'title': title[:500],  # Ограничиваем длину
                'price_cents': price,
                'description': description[:2000] if description else '',  # Ограничиваем длину
                'images_base64': images
            }
            
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: Не удалось загрузить страницу POIZON. Сайт может блокировать запросы или URL неверный."
        print(error_msg)
        raise Exception(error_msg)
    except httpx.RequestError as e:
        error_msg = f"Ошибка сети: Не удалось подключиться к POIZON. Проверьте подключение к интернету."
        print(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = str(e)
        print(f"Parse error: {error_msg}")
        import traceback
        traceback.print_exc()
        raise Exception(error_msg)
