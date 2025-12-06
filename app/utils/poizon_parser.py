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
            
            # Парсинг данных из __NEXT_DATA__ (Next.js хранит все данные в JSON)
            title = None
            price = None
            images = []
            description = ""
            sizes_prices = []  # Инициализируем список размеров
            next_data = None
            
            # Ищем __NEXT_DATA__ скрипт (там все данные товара)
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                try:
                    import json
                    next_data = json.loads(next_data_script.string)
                    print("✅ Found __NEXT_DATA__ script with product data")
                    print(f"  __NEXT_DATA__ keys: {list(next_data.keys())[:10]}")
                except Exception as e:
                    print(f"❌ Error parsing __NEXT_DATA__: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ __NEXT_DATA__ script not found in HTML!")
            
            # Если нашли __NEXT_DATA__, используем данные оттуда
            if next_data:
                try:
                    # Извлекаем данные из структуры Next.js
                    props = next_data.get('props', {})
                    page_props = props.get('pageProps', {})
                    
                    # Ищем данные товара в разных местах структуры (более глубокий поиск)
                    # В логах видно, что в pageProps есть 'goodsDetail' - это и есть данные товара!
                    product_data = (page_props.get('goodsDetail') or 
                                  page_props.get('productData') or 
                                  page_props.get('product') or
                                  page_props.get('initialState', {}).get('product') if isinstance(page_props.get('initialState'), dict) else None or
                                  page_props.get('data', {}).get('product') if isinstance(page_props.get('data'), dict) else None or
                                  page_props.get('data', {}).get('productData') if isinstance(page_props.get('data'), dict) else None)
                    
                    # Также пробуем поискать в dehydratedState (часто используется в Next.js)
                    dehydrated_state = page_props.get('dehydratedState', {})
                    if not product_data and dehydrated_state:
                        queries = dehydrated_state.get('queries', [])
                        for query in queries:
                            state_data = query.get('state', {}).get('data', {})
                            if state_data:
                                # Пробуем разные варианты
                                product_data = (state_data.get('goodsDetail') or
                                              state_data.get('product') or 
                                              state_data.get('productData') or
                                              state_data.get('data', {}).get('product') if isinstance(state_data.get('data'), dict) else None or
                                              state_data.get('data', {}).get('goodsDetail') if isinstance(state_data.get('data'), dict) else None)
                                if product_data:
                                    print("  Found product_data in dehydratedState.queries")
                                    break
                    
                    # Если все еще не нашли, пробуем взять goodsDetail напрямую из pageProps
                    if not product_data and 'goodsDetail' in page_props:
                        goods_detail = page_props['goodsDetail']
                        if goods_detail and isinstance(goods_detail, dict):
                            product_data = goods_detail
                            print(f"  ✅ Using goodsDetail from pageProps as product_data, keys: {list(product_data.keys())[:30]}")
                    
                    if product_data:
                        print(f"✅ Found product_data in __NEXT_DATA__")
                        print(f"  product_data type: {type(product_data)}")
                        if isinstance(product_data, dict):
                            print(f"  product_data keys (first 30): {list(product_data.keys())[:30]}")
                        
                        # Название
                        if isinstance(product_data, dict):
                            title = (product_data.get('title') or 
                                   product_data.get('name') or
                                   product_data.get('productName') or
                                   product_data.get('spuName') or
                                   product_data.get('goodsName') or
                                   product_data.get('goodsNameEn'))
                        
                            # Изображения (сохраняем как URL, потом скачаем)
                            images_data = (product_data.get('images') or 
                                         product_data.get('imageList') or
                                         product_data.get('imageUrls') or
                                         product_data.get('spuImages') or
                                         product_data.get('mainImages') or
                                         product_data.get('detailImages') or
                                         product_data.get('goodsImages') or
                                         product_data.get('goodsImageList'))
                        
                        if images_data:
                            if isinstance(images_data, list):
                                # Пропускаем первое изображение (обычно это подошва/стопа)
                                for img in images_data[1:11]:  # Пропускаем первый, берем следующие 10
                                    img_url = None
                                    if isinstance(img, str):
                                        img_url = img
                                    elif isinstance(img, dict):
                                        img_url = img.get('url') or img.get('src') or img.get('imageUrl') or img.get('originUrl')
                                    
                                    if img_url:
                                        # Нормализуем URL
                                        if img_url.startswith('//'):
                                            img_url = 'https:' + img_url
                                        elif img_url.startswith('/'):
                                            img_url = base_domain + img_url
                                        
                                        if img_url.startswith('http') and img_url not in images:
                                            images.append(img_url)  # Пока сохраняем как URL
                            elif isinstance(images_data, str):
                                # Если одно изображение, тоже пропускаем
                                pass
                        
                        print(f"Found {len(images)} image URLs from __NEXT_DATA__ (skipped first)")
                        
                        # SKU данные (размеры и цены) - более глубокий поиск
                        # Пробуем разные пути в структуре данных
                        skus = None
                        
                        # Сначала ищем напрямую
                        for key in ['skus', 'skuList', 'skuInfos', 'skuData', 'priceList', 'sizeList', 
                                   'sizePriceList', 'sizes', 'sizeInfos', 'goodsSkuList', 'skuInfosList',
                                   'skuListData', 'sizePriceData', 'variants', 'variations']:
                            if key in product_data:
                                skus = product_data[key]
                                print(f"  Found SKUs in product_data['{key}']")
                                break
                        
                        # Если не нашли напрямую, пробуем поискать глубже во вложенных структурах
                        if not skus:
                            print("  SKUs not found directly, searching in nested structures...")
                            nested_keys = ['data', 'goodsDetail', 'detail', 'goods', 'productInfo', 'spuInfo', 'goodsInfo']
                            for nested_key in nested_keys:
                                nested_data = product_data.get(nested_key)
                                if isinstance(nested_data, dict):
                                    for key in ['skus', 'skuList', 'skuInfos', 'sizeList', 'skuData']:
                                        if key in nested_data:
                                            skus = nested_data[key]
                                            print(f"  Found SKUs in product_data['{nested_key}']['{key}']")
                                            break
                                    if skus:
                                        break
                        
                        # Также пробуем поискать в массивах внутри product_data
                        if not skus:
                            print("  Searching in arrays within product_data...")
                            for key, value in product_data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    first_item = value[0]
                                    if isinstance(first_item, dict):
                                        has_size = any(k in first_item for k in ['size', 'sizeName', 'specValue', 'sizeValue', 'sizeText'])
                                        has_price = any(k in first_item for k in ['price', 'salePrice', 'currentPrice', 'priceValue'])
                                        if has_size and has_price:
                                            skus = value
                                            print(f"  Found SKUs in array: product_data['{key}']")
                                            break
                        
                        # Также пробуем поискать размеры и цены в priceInfo из pageProps
                        if not skus and 'priceInfo' in page_props:
                            price_info = page_props['priceInfo']
                            print(f"  Found priceInfo in pageProps, type: {type(price_info)}")
                            if isinstance(price_info, dict):
                                print(f"    priceInfo keys: {list(price_info.keys())[:20]}")
                                # Пробуем найти список размеров с ценами
                                for key in ['skuList', 'skus', 'sizePriceList', 'sizeList', 'prices']:
                                    if key in price_info:
                                        candidate = price_info[key]
                                        if isinstance(candidate, list) and len(candidate) > 0:
                                            skus = candidate
                                            print(f"  ✅ Found SKUs in priceInfo['{key}']")
                                            break
                            elif isinstance(price_info, list) and len(price_info) > 0:
                                # Если priceInfo сам является массивом
                                first_item = price_info[0]
                                if isinstance(first_item, dict):
                                    has_size = any(k in first_item for k in ['size', 'sizeName', 'specValue'])
                                    has_price = any(k in first_item for k in ['price', 'salePrice', 'currentPrice'])
                                    if has_size and has_price:
                                        skus = price_info
                                        print(f"  ✅ Using priceInfo list as SKUs")
                        
                        # Пробуем найти в __NEXT_DATA__ через другой путь - через queries/dehydratedState
                        if not skus and dehydrated_state:
                            print("  Searching in dehydratedState queries...")
                            queries = dehydrated_state.get('queries', [])
                            for query in queries:
                                state_data = query.get('state', {}).get('data', {})
                                if isinstance(state_data, dict):
                                    # Ищем SKU данные в разных местах
                                    for path in [
                                        lambda d: d.get('skuList'),
                                        lambda d: d.get('skus'),
                                        lambda d: d.get('data', {}).get('skuList'),
                                        lambda d: d.get('data', {}).get('skus'),
                                        lambda d: d.get('goodsDetail', {}).get('skuList'),
                                        lambda d: d.get('goodsDetail', {}).get('skus'),
                                    ]:
                                        result = path(state_data)
                                        if result:
                                            skus = result
                                            print(f"  Found SKUs in dehydratedState.queries")
                                            break
                                    if skus:
                                        break
                        
                        if skus and isinstance(skus, list) and len(skus) > 0:
                            sizes_prices = []
                            print(f"  ✅ Processing {len(skus)} SKU items from __NEXT_DATA__...")
                            
                            # Отладочная информация о структуре первого SKU
                            if len(skus) > 0:
                                print(f"  DEBUG: First SKU keys: {list(skus[0].keys())[:15]}")
                            
                            for idx, sku in enumerate(skus):
                                size = (sku.get('size') or 
                                       sku.get('sizeName') or 
                                       sku.get('specValue') or
                                       sku.get('sizeValue') or
                                       sku.get('sizeText') or
                                       sku.get('sizeLabel') or
                                       sku.get('sizeNameCn') or
                                       sku.get('sizeNameEn'))
                                price_value = (sku.get('price') or 
                                             sku.get('salePrice') or 
                                             sku.get('currentPrice') or
                                             sku.get('priceValue') or
                                             sku.get('priceText') or
                                             sku.get('priceLabel') or
                                             sku.get('lowPrice') or
                                             sku.get('highPrice'))
                                
                                # Если не нашли напрямую, пробуем вложенные структуры
                                if not price_value and isinstance(sku, dict):
                                    price_info = sku.get('priceInfo') or sku.get('price')
                                    if isinstance(price_info, dict):
                                        price_value = (price_info.get('price') or 
                                                     price_info.get('salePrice') or
                                                     price_info.get('currentPrice'))
                                
                                if size and price_value:
                                    try:
                                        # Цена может быть в разных форматах
                                        if isinstance(price_value, (int, float)):
                                            # Если число большое (>= 1000), возможно это уже в копейках или центах
                                            if price_value >= 1000:
                                                price_cents = int(price_value)
                                            else:
                                                price_cents = int(price_value * 100)  # Предполагаем рубли
                                        else:
                                            price_str = str(price_value).replace(' ', '').replace(',', '').replace('₽', '').replace('₴', '')
                                            price_num = float(re.sub(r'[^\d.]', '', price_str))
                                            if price_num >= 1000:
                                                price_cents = int(price_num)
                                            else:
                                                price_cents = int(price_num * 100)
                                        
                                        sizes_prices.append({
                                            'size': str(size),
                                            'price': price_cents
                                        })
                                        print(f"  SKU {idx+1}: size={size}, price={price_cents} копеек")
                                    except Exception as e:
                                        print(f"  Error parsing SKU {idx+1}: {e}")
                                        pass
                            
                            if sizes_prices:
                                description_lines = ["Размеры и цены:"]
                                for item in sizes_prices:
                                    price_rub = item['price'] / 100
                                    description_lines.append(f"{item['size']}: {price_rub:,.0f} ₽")
                                description = "\n".join(description_lines)
                                
                                # Минимальная цена
                                min_price = min(item['price'] for item in sizes_prices)
                                price = min_price
                                
                                print(f"✅ Found {len(sizes_prices)} sizes from __NEXT_DATA__")
                            else:
                                print(f"⚠️ SKUs list found but no valid sizes parsed (skus count: {len(skus)})")
                                # Выводим структуру для отладки
                                if skus and len(skus) > 0:
                                    print(f"  First SKU structure (keys): {list(skus[0].keys())[:10]}")
                        else:
                            print(f"⚠️ No SKUs found in product_data")
                            print(f"    Available top-level keys ({len(product_data.keys())}): {list(product_data.keys())[:50]}")
                            
                            # Детальный анализ структуры
                            try:
                                import json
                                # Ищем любые массивы в product_data
                                arrays_found = []
                                for key, value in product_data.items():
                                    if isinstance(value, list) and len(value) > 0:
                                        arrays_found.append((key, len(value)))
                                        print(f"    Found array '{key}' with {len(value)} items")
                                        if isinstance(value[0], dict):
                                            print(f"      First item keys: {list(value[0].keys())[:20]}")
                                
                                if not arrays_found:
                                    print(f"    ⚠️ No arrays found in product_data!")
                                
                                # Ищем ключи, связанные с размерами/ценами
                                size_related_keys = [k for k in product_data.keys() if any(word in str(k).lower() for word in ['size', 'sku', 'price', 'variant', 'spec'])]
                                if size_related_keys:
                                    print(f"    🔍 Size/SKU/Price related keys: {size_related_keys}")
                                    # Показываем содержимое этих ключей
                                    for key in size_related_keys[:5]:
                                        value = product_data[key]
                                        print(f"      {key}: {type(value).__name__}, value preview: {str(value)[:200]}")
                                
                                # Показываем структуру для анализа
                                sample = json.dumps(product_data, default=str, indent=2, ensure_ascii=False)[:3000]
                                print(f"    Product data structure (first 3000 chars):\n{sample}")
                            except Exception as e:
                                print(f"    ❌ Error analyzing structure: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        # Если цена не найдена из SKU, ищем основную цену
                        if not price:
                            price_value = (product_data.get('price') or 
                                         product_data.get('salePrice') or
                                         product_data.get('currentPrice') or
                                         product_data.get('lowPrice'))
                            
                            if price_value:
                                try:
                                    if isinstance(price_value, (int, float)):
                                        price = int(price_value * 100) if price_value < 1000 else int(price_value)
                                    else:
                                        price_str = str(price_value).replace(' ', '').replace(',', '')
                                        price_num = float(re.sub(r'[^\d.]', '', price_str))
                                        price = int(price_num * 100) if price_num < 1000 else int(price_num)
                                except:
                                    pass
                        
                        print(f"Parsed from __NEXT_DATA__: title={bool(title)}, price={bool(price)}, images={len(images)}")
                
                except Exception as e:
                    print(f"Error extracting data from __NEXT_DATA__: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Если не нашли в __NEXT_DATA__, продолжаем обычный парсинг
            
            # Поиск названия товара (оригинальное, без перевода)
            if not title:
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
                
                # Удаляем все слова на кириллице, оставляем только латиницу, цифры и пробелы
                # Разбиваем на слова и фильтруем только те, что содержат латиницу или цифры
                words = title.split()
                english_words = []
                
                for word in words:
                    # Проверяем, есть ли в слове кириллица
                    has_cyrillic = re.search(r'[А-Яа-яЁё]', word)
                    # Проверяем, есть ли в слове латиница или цифры
                    has_latin_or_digits = re.search(r'[A-Za-z0-9]', word)
                    
                    # Пропускаем слова с кириллицей
                    if has_cyrillic:
                        continue
                    
                    # Оставляем слова с латиницей или цифрами, а также специальные символы (например, модели типа "NB-850")
                    if has_latin_or_digits or re.match(r'^[A-Za-z0-9\-_/]+$', word):
                        english_words.append(word)
                
                # Объединяем обратно
                title = ' '.join(english_words).strip()
                
                # Дополнительная очистка - убираем множественные пробелы
                title = re.sub(r'\s+', ' ', title).strip()
            
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
            
            # Поиск изображений (галерея товара, пропускаем первое - это обычно подошва/стопа)
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
                    
                    # Не прерываемся, собираем все
                
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
            
            # Скачиваем и конвертируем изображения (пропускаем первое - обычно это подошва/стопа)
            if found_urls:
                # Пропускаем первое изображение, берем следующие (максимум 10)
                images_to_download = found_urls[1:11] if len(found_urls) > 1 else []
                max_images = len(images_to_download)
                
                for idx, img_url in enumerate(images_to_download, 1):
                    print(f"Downloading image {idx}/{max_images}: {img_url[:80]}...")
                    img_base64 = await download_image_to_base64(img_url, client)
                    if img_base64:
                        images.append(img_base64)
                        print(f"  Successfully downloaded image {idx}")
                    else:
                        print(f"  Failed to download image {idx}")
            
            # Если images уже содержит URL (из __NEXT_DATA__), нужно их скачать
            if images and all(isinstance(img, str) and img.startswith('http') for img in images):
                downloaded_images = []
                # Пропускаем первое, скачиваем остальные
                images_to_download = images[1:11] if len(images) > 1 else []
                for idx, img_url in enumerate(images_to_download, 1):
                    print(f"Downloading image {idx}/{len(images_to_download)}: {img_url[:80]}...")
                    img_base64 = await download_image_to_base64(img_url, client)
                    if img_base64:
                        downloaded_images.append(img_base64)
                        print(f"  Successfully downloaded image {idx}")
                    else:
                        print(f"  Failed to download image {idx}")
                images = downloaded_images
            
            print(f"Downloaded {len(images)} images")
            
            # Парсинг размеров и цен (если еще не нашли из __NEXT_DATA__)
            # Используем селекторы из Selenium кода
            if not description:
                sizes_prices = []
                print("Searching for sizes and prices using SkuPanel selectors...")
                
                # Сначала проверим, есть ли вообще элементы SkuPanel на странице
                sku_panel_elements = soup.select('div[class*="SkuPanel"]')
                print(f"  DEBUG: Found {len(sku_panel_elements)} elements with class containing 'SkuPanel'")
                
                # Проверяем количество меню (как в оригинальном коде)
                check_count_menu = soup.select('div.SkuPanel_label__Vbp8t>span:nth-child(1)')
                menu_count = len(check_count_menu)
                
                print(f"  Found {menu_count} menu(s) in SkuPanel_label__Vbp8t")
                
                # Дополнительная диагностика - проверим все возможные селекторы
                debug_selectors = {
                    'SkuPanel_group': soup.select('div.SkuPanel_group__egmoX'),
                    'SkuPanel_value': soup.select('div.SkuPanel_value__BAJ1p'),
                    'SkuPanel_price': soup.select('div.SkuPanel_price__KCs7G'),
                    'SkuPanel_label': soup.select('div.SkuPanel_label__Vbp8t'),
                }
                for name, elements in debug_selectors.items():
                    print(f"  DEBUG: {name} elements found: {len(elements)}")
                    if elements and len(elements) > 0:
                        print(f"    First element text: {elements[0].get_text(strip=True)[:100]}")
                
                if menu_count == 1:
                    # Одно меню: размеры и цены в nth-child(1)
                    print(f"  Trying menu_count=1 approach...")
                    try:
                        # Пробуем разные варианты селекторов
                        size_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_value__BAJ1p')
                        price_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_price__KCs7G')
                        
                        # Если не нашли, пробуем без nth-child
                        if not size_elements:
                            size_elements = soup.select('div.SkuPanel_group__egmoX div.SkuPanel_value__BAJ1p')
                        if not price_elements:
                            price_elements = soup.select('div.SkuPanel_group__egmoX div.SkuPanel_price__KCs7G')
                        
                        print(f"    Found {len(size_elements)} size elements, {len(price_elements)} price elements")
                        
                        if size_elements and price_elements:
                            sizes = [elem.get_text(strip=True) for elem in size_elements]
                            prices = [elem.get_text(strip=True).replace('₽', '').replace('P', '').replace('$', '').replace(' ', '') for elem in price_elements]
                            
                            for size, price_text in zip(sizes, prices):
                                try:
                                    # Пытаемся преобразовать цену в число
                                    price_clean = price_text.replace(' ', '').replace(',', '').replace('₽', '').replace('P', '').replace('$', '')
                                    if price_clean and price_clean != '-':
                                        price_num = float(price_clean)
                                        # Если цена меньше 1000, возможно это в юанях, умножаем на ~12.5
                                        if price_num < 1000:
                                            price_num = price_num * 12.5
                                        price_cents = int(price_num * 100)  # в копейках
                                        
                                        sizes_prices.append({
                                            'size': size,
                                            'price': price_cents
                                        })
                                        print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                                except Exception as e:
                                    print(f"    ⚠️ Error parsing price for size {size}: {e}")
                                    pass
                    except Exception as e:
                        print(f"  Error parsing sizes/prices with menu_count=1: {e}")
                
                elif menu_count == 2:
                    # Два меню (цвет): размеры и цены в nth-child(2)
                    print(f"  Trying menu_count=2 approach...")
                    try:
                        size_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(2) div.SkuPanel_value__BAJ1p')
                        price_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(2) div.SkuPanel_price__KCs7G')
                        
                        # Если не нашли, пробуем без nth-child
                        if not size_elements:
                            size_elements = soup.select('div.SkuPanel_group__egmoX div.SkuPanel_value__BAJ1p')
                        if not price_elements:
                            price_elements = soup.select('div.SkuPanel_group__egmoX div.SkuPanel_price__KCs7G')
                        
                        print(f"    Found {len(size_elements)} size elements, {len(price_elements)} price elements")
                        
                        if size_elements and price_elements:
                            sizes = [elem.get_text(strip=True) for elem in size_elements]
                            prices = [elem.get_text(strip=True).replace('₽', '').replace('P', '').replace('$', '').replace(' ', '') for elem in price_elements]
                            
                            for size, price_text in zip(sizes, prices):
                                try:
                                    price_clean = price_text.replace(' ', '').replace(',', '').replace('₽', '').replace('P', '').replace('$', '')
                                    if price_clean and price_clean != '-':
                                        price_num = float(price_clean)
                                        if price_num < 1000:
                                            price_num = price_num * 12.5
                                        price_cents = int(price_num * 100)
                                        
                                        sizes_prices.append({
                                            'size': size,
                                            'price': price_cents
                                        })
                                        print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                                except Exception as e:
                                    print(f"    ⚠️ Error parsing price for size {size}: {e}")
                                    pass
                    except Exception as e:
                        print(f"  Error parsing sizes/prices with menu_count=2: {e}")
                
                elif menu_count == 3:
                    # Три меню: размеры и цены в nth-child(3)
                    print(f"  Trying menu_count=3 approach...")
                    try:
                        size_element = soup.select_one('div.SkuPanel_group__egmoX:nth-child(3) div.SkuPanel_value__BAJ1p')
                        price_element = soup.select_one('div.SkuPanel_group__egmoX:nth-child(3) div.SkuPanel_price__KCs7G')
                        
                        # Если не нашли, пробуем без nth-child
                        if not size_element:
                            size_element = soup.select_one('div.SkuPanel_group__egmoX div.SkuPanel_value__BAJ1p')
                        if not price_element:
                            price_element = soup.select_one('div.SkuPanel_group__egmoX div.SkuPanel_price__KCs7G')
                        
                        print(f"    Found size_element: {bool(size_element)}, price_element: {bool(price_element)}")
                        
                        if size_element and price_element:
                            size = size_element.get_text(strip=True)
                            price_text = price_element.get_text(strip=True).replace('₽', '').replace('P', '').replace('$', '').replace(' ', '')
                            
                            try:
                                price_clean = price_text.replace(' ', '').replace(',', '').replace('₽', '').replace('P', '').replace('$', '')
                                if price_clean and price_clean != '-':
                                    price_num = float(price_clean)
                                    if price_num < 1000:
                                        price_num = price_num * 12.5
                                    price_cents = int(price_num * 100)
                                    
                                    sizes_prices.append({
                                        'size': size,
                                        'price': price_cents
                                    })
                                    print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                            except Exception as e:
                                print(f"    ⚠️ Error parsing price for size {size}: {e}")
                                pass
                    except Exception as e:
                        print(f"  Error parsing sizes/prices with menu_count=3: {e}")
                
                # Попробуем более простой подход - просто ищем все элементы с этими классами
                if not sizes_prices:
                    print(f"  Fallback: Trying to find ANY SkuPanel_value and SkuPanel_price elements...")
                    try:
                        all_size_elements = soup.select('div.SkuPanel_value__BAJ1p')
                        all_price_elements = soup.select('div.SkuPanel_price__KCs7G')
                        
                        print(f"    Found {len(all_size_elements)} total size elements, {len(all_price_elements)} total price elements")
                        
                        if all_size_elements and all_price_elements and len(all_size_elements) == len(all_price_elements):
                            sizes = [elem.get_text(strip=True) for elem in all_size_elements]
                            prices = [elem.get_text(strip=True).replace('₽', '').replace('P', '').replace('$', '').replace(' ', '') for elem in all_price_elements]
                            
                            print(f"    Extracted {len(sizes)} sizes: {sizes[:5]}...")
                            print(f"    Extracted {len(prices)} prices: {prices[:5]}...")
                            
                            for size, price_text in zip(sizes, prices):
                                try:
                                    price_clean = price_text.replace(' ', '').replace(',', '').replace('₽', '').replace('P', '').replace('$', '')
                                    if price_clean and price_clean != '-':
                                        price_num = float(price_clean)
                                        if price_num < 1000:
                                            price_num = price_num * 12.5
                                        price_cents = int(price_num * 100)
                                        
                                        sizes_prices.append({
                                            'size': size,
                                            'price': price_cents
                                        })
                                        print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                                except Exception as e:
                                    print(f"    ⚠️ Error parsing price '{price_text}' for size {size}: {e}")
                                    pass
                    except Exception as e:
                        print(f"  Error in fallback parsing: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Если есть вкладки размеров (check_gender в оригинальном коде)
                if not sizes_prices:
                    try:
                        size_buttons = soup.select('div.SkuPanel_tabItem__MuUkW')
                        if size_buttons:
                            print(f"  Found {len(size_buttons)} size tab(s), trying to parse from first tab...")
                            # Берем первую вкладку
                            size_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_value__BAJ1p')
                            price_elements = soup.select('div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_price__KCs7G')
                            
                            print(f"    In tabs: Found {len(size_elements)} size elements, {len(price_elements)} price elements")
                            
                            if size_elements and price_elements:
                                sizes = [elem.get_text(strip=True) for elem in size_elements]
                                prices = [elem.get_text(strip=True).replace('₽', '').replace('P', '').replace('$', '').replace(' ', '') for elem in price_elements]
                                
                                for size, price_text in zip(sizes, prices):
                                    try:
                                        price_clean = price_text.replace(' ', '').replace(',', '').replace('₽', '').replace('P', '').replace('$', '')
                                        if price_clean and price_clean != '-':
                                            price_num = float(price_clean)
                                            if price_num < 1000:
                                                price_num = price_num * 12.5
                                            price_cents = int(price_num * 100)
                                            
                                            if not any(sp['size'] == size for sp in sizes_prices):
                                                sizes_prices.append({
                                                    'size': size,
                                                    'price': price_cents
                                                })
                                                print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                                    except Exception as e:
                                        pass
                    except Exception as e:
                        print(f"  Error parsing from size tabs: {e}")
            
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
            
            # Логируем финальное описание для отладки
            if description:
                print(f"Description will be saved (first 200 chars): {description[:200]}")
            else:
                print("WARNING: Description is empty - no sizes and prices found!")
            
            return {
                'title': title[:500],  # Ограничиваем длину
                'price_cents': final_price,
                'description': description[:2000] if description else '',  # Размеры и цены сохраняются здесь
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
