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
            
            # Поиск названия товара (оригинальное, без перевода)
            title = None
            
            # Ищем оригинальное название в JSON-LD (там обычно английское оригинальное)
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for json_ld in json_ld_scripts:
                try:
                    import json
                    data = json.loads(json_ld.string)
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    
                    if isinstance(data, dict):
                        # Ищем название в JSON-LD - предпочитаем английское
                        if 'name' in data:
                            candidate = data['name']
                            # Предпочитаем названия с латинскими буквами (английские)
                            if re.search(r'[a-zA-Z]', candidate):
                                title = candidate
                                print(f"Found title from JSON-LD name: {title[:50]}...")
                                break
                        elif 'alternateName' in data:
                            candidate = data['alternateName']
                            if re.search(r'[a-zA-Z]', candidate):
                                title = candidate
                                print(f"Found title from JSON-LD alternateName: {title[:50]}...")
                                break
                except Exception as e:
                    print(f"Error parsing JSON-LD for title: {e}")
                    pass
            
            # Если не нашли в JSON-LD, ищем в JavaScript переменных (там часто оригинальное название)
            if not title:
                # Ищем в script тегах переменные типа productName, product_title, etc.
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string:
                        # Ищем паттерны типа "name": "New Balance..."
                        name_patterns = [
                            re.compile(r'["\']name["\']\s*[:=]\s*["\']([^"\']+?)["\']', re.IGNORECASE),
                            re.compile(r'["\']productName["\']\s*[:=]\s*["\']([^"\']+?)["\']', re.IGNORECASE),
                            re.compile(r'["\']title["\']\s*[:=]\s*["\']([^"\']+?)["\']', re.IGNORECASE),
                        ]
                        for pattern in name_patterns:
                            matches = pattern.findall(script.string)
                            for match in matches:
                                # Предпочитаем названия с латинскими буквами
                                if re.search(r'[a-zA-Z]', match) and len(match) > 10:
                                    title = match.strip()
                                    print(f"Found title from script variable: {title[:50]}...")
                                    break
                            if title:
                                break
                    if title:
                        break
            
            # Если не нашли, ищем в data-атрибутах
            if not title:
                title_elem = soup.select_one('[data-name], [data-product-name], [data-title], [data-original-name]')
                if title_elem:
                    candidate = (title_elem.get('data-name') or 
                                title_elem.get('data-product-name') or 
                                title_elem.get('data-title') or
                                title_elem.get('data-original-name'))
                    if candidate:
                        # Предпочитаем английские названия
                        if re.search(r'[a-zA-Z]', candidate):
                            title = candidate
                            print(f"Found title from data-attribute: {title[:50]}...")
            
            # В последнюю очередь пробуем селекторы
            if not title:
                title_selectors = [
                    'h1.product-title',
                    'h1.goods-title',
                    '.product-name',
                    '.goods-name',
                    '.product__title',
                    '.product-title',
                    'h1[class*="product"]',
                    'h1'
                ]
                
                for selector in title_selectors:
                    title_elem = soup.select_one(selector)
                    if title_elem:
                        candidate = title_elem.get_text(strip=True)
                        if candidate and len(candidate) > 5:
                            title = candidate
                            print(f"Found title with selector '{selector}': {title[:50]}...")
                            break
            
            # Очистка названия от суффиксов сайта и переведенных частей
            if title:
                title = re.sub(r'\s*[-|]\s*thepoizon.*$', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*[-|]\s*POIZON.*$', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*[-|]\s*得物.*$', '', title, flags=re.IGNORECASE)
                # Убираем типичные переводы в конце (если есть оригинальное название в начале)
                # Например: "New Balance NB 850 Устойчивые к истиранию..." -> "New Balance NB 850"
                if re.search(r'[a-zA-Z]', title):
                    # Пытаемся оставить только английскую часть
                    parts = re.split(r'\s+[А-Яа-яЁё]', title)
                    if len(parts) > 0 and parts[0].strip():
                        english_part = parts[0].strip()
                        if len(english_part) > 10:  # Если английская часть достаточно длинная
                            title = english_part
                title = title.strip()
            
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
            
            # Поиск изображений (галерея товара, первые 3 оригинальные фото)
            found_urls = []
            
            # Сначала ищем в JSON-LD - там могут быть ссылки на оригинальные изображения
            for json_ld in json_ld_scripts:
                try:
                    import json
                    data = json.loads(json_ld.string)
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    
                    if isinstance(data, dict):
                        # Ищем image (может быть строкой или массивом)
                        if 'image' in data:
                            img_data = data['image']
                            if isinstance(img_data, list):
                                for img in img_data[:3]:
                                    if isinstance(img, str) and img not in found_urls:
                                        found_urls.append(img)
                                    elif isinstance(img, dict) and 'url' in img and img['url'] not in found_urls:
                                        found_urls.append(img['url'])
                            elif isinstance(img_data, str) and img_data not in found_urls:
                                found_urls.append(img_data)
                            
                            if len(found_urls) >= 3:
                                break
                except:
                    pass
            
            # Если не нашли в JSON-LD, ищем в галерее товара
            if len(found_urls) == 0:
                print("Searching for images in HTML gallery...")
                # Селекторы для галереи товара
                gallery_selectors = [
                    '.product-gallery img',
                    '.product-images img',
                    '.gallery-item img',
                    '.swiper-slide img',
                    '.slider-item img',
                    '.product-photos img',
                    '[class*="gallery"] img',
                    '[class*="slider"] img',
                    '[class*="carousel"] img',
                    '[class*="swiper"] img',
                    '.product-image img',
                    '.product__image img',
                    '[class*="product"] [class*="image"] img',
                    '[class*="goods"] img',
                    'img[src*="product"]',
                    'img[src*="goods"]'
                ]
                
                for selector in gallery_selectors:
                    img_tags = soup.select(selector)
                    print(f"  Trying selector '{selector}': found {len(img_tags)} elements")
                    for img in img_tags:
                        # Ищем оригинальные изображения (не миниатюры)
                        img_url = None
                        
                        # Проверяем data-атрибуты для оригинальных изображений (в приоритете)
                        img_url = (img.get('data-original') or 
                                  img.get('data-src-large') or 
                                  img.get('data-full') or
                                  img.get('data-url') or
                                  img.get('data-original-src') or
                                  img.get('data-lazy-src') or
                                  img.get('data-src') or
                                  img.get('src'))
                        
                        if img_url:
                            # Пропускаем миниатюры, иконки, логотипы
                            img_url_lower = img_url.lower()
                            if any(skip in img_url_lower for skip in ['thumb', 'icon', 'placeholder', 'logo', 'avatar', 'default']):
                                continue
                            
                            # Нормализуем URL
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = base_domain + img_url
                            
                            if img_url.startswith('http') and img_url not in found_urls:
                                found_urls.append(img_url)
                                print(f"    Added image: {img_url[:80]}...")
                    
                    # Не прерываемся на 3, собираем все
                
                print(f"Found {len(found_urls)} images in HTML gallery")
            
            # Если все еще не нашли, ищем в JavaScript переменных
            if len(found_urls) == 0:
                print("Searching for images in JavaScript variables...")
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string:
                        # Ищем паттерны типа "image": "http://..." или imageUrls: [...]
                        img_patterns = [
                            re.compile(r'["\']image["\']\s*[:=]\s*["\']([^"\']+?)["\']', re.IGNORECASE),
                            re.compile(r'["\']imageUrl["\']\s*[:=]\s*["\']([^"\']+?)["\']', re.IGNORECASE),
                            re.compile(r'["\']url["\']\s*[:=]\s*["\']([^"\']+?\.(?:jpg|jpeg|png|webp))["\']', re.IGNORECASE),
                        ]
                        for pattern in img_patterns:
                            matches = pattern.findall(script.string)
                            for match in matches:
                                if match.startswith('http') and match not in found_urls:
                                    # Пропускаем миниатюры
                                    if not any(skip in match.lower() for skip in ['thumb', 'icon', 'placeholder']):
                                        found_urls.append(match)
                                        print(f"    Found image in script: {match[:80]}...")
            
            print(f"Total found {len(found_urls)} image URLs before downloading")
            
            # Скачиваем и конвертируем изображения (все найденные, максимум 10)
            max_images = min(len(found_urls), 10)
            for idx, img_url in enumerate(found_urls[:max_images], 1):
                print(f"Downloading image {idx}/{max_images}: {img_url[:80]}...")
                img_base64 = await download_image_to_base64(img_url, client)
                if img_base64:
                    images.append(img_base64)
                    print(f"  Successfully downloaded image {idx}")
                else:
                    print(f"  Failed to download image {idx}")
            
            print(f"Downloaded {len(images)} images")
            
            # Парсинг размеров и цен
            sizes_prices = []
            print("Searching for sizes and prices...")
            
            # Ищем размеры в различных селекторах
            size_selectors = [
                '[class*="size"]',
                '[class*="Size"]',
                '[data-size]',
                '.size-selector',
                '.product-sizes',
                '[class*="sku"]'
            ]
            
            for selector in size_selectors:
                size_elements = soup.select(selector)
                if size_elements:
                    print(f"  Found size elements with selector '{selector}': {len(size_elements)}")
                    for elem in size_elements:
                        # Получаем текст элемента
                        text = elem.get_text(strip=True)
                        # Ищем паттерн: размер и цена
                        # Примеры: "39,5 (40,5) 9 164 ₽", "38 (39) 10 072 ₽"
                        size_price_match = re.search(r'([\d,]+(?:\s*\([^)]+\))?)\s+([\d\s]+)\s*[₽₴]', text)
                        if size_price_match:
                            size_text = size_price_match.group(1).strip()
                            price_text = size_price_match.group(2).strip().replace(' ', '')
                            try:
                                price_num = float(price_text)
                                sizes_prices.append({
                                    'size': size_text,
                                    'price': int(price_num * 100)  # в копейках
                                })
                                print(f"    Found size: {size_text}, price: {price_num} руб")
                            except:
                                pass
            
            # Если не нашли через селекторы, ищем по тексту страницы
            if not sizes_prices:
                print("  Trying to find sizes in page text...")
                page_text = soup.get_text()
                # Паттерн для размеров и цен: "39,5(40,5) 9 164 ₽"
                size_price_pattern = re.compile(r'(\d+[,.]?\d*\s*\([^)]+\))\s+(\d+(?:\s+\d+)*)\s*[₽₴]')
                matches = size_price_pattern.findall(page_text)
                for match in matches[:20]:  # Максимум 20 размеров
                    size_text = match[0].strip()
                    price_text = match[1].strip().replace(' ', '')
                    try:
                        price_num = float(price_text)
                        sizes_prices.append({
                            'size': size_text,
                            'price': int(price_num * 100)
                        })
                        print(f"    Found size: {size_text}, price: {price_num} руб")
                    except:
                        pass
            
            # Формируем описание из размеров и цен
            if sizes_prices:
                description_lines = ["Размеры и цены:"]
                for item in sizes_prices:
                    price_rub = item['price'] / 100
                    description_lines.append(f"{item['size']}: {price_rub:,.0f} ₽")
                description = "\n".join(description_lines)
                print(f"Created description with {len(sizes_prices)} sizes")
            else:
                description = ""
                print("No sizes found, description will be empty")
            
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
            
            # Используем минимальную цену из размеров, если она найдена, иначе основную цену
            final_price = price
            if sizes_prices:
                # Берем минимальную цену среди размеров
                min_size_price = min(item['price'] for item in sizes_prices)
                final_price = min_size_price
                print(f"Using minimum size price: {final_price} копеек (from {len(sizes_prices)} sizes)")
            
            print(f"Successfully parsed product: {title[:50]}... (price: {final_price} копеек, images: {len(images)}, sizes: {len(sizes_prices)})")
            
            return {
                'title': title[:500],  # Ограничиваем длину
                'price_cents': final_price,
                'description': description[:2000] if description else '',  # Размеры и цены
                'images_base64': images  # Все найденные изображения (до 10)
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
