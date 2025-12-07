import httpx
from bs4 import BeautifulSoup
import base64
from typing import Optional, Dict, Any
import re
import asyncio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from fake_useragent import UserAgent
import time

def _create_selenium_driver():
    """Создает и настраивает Selenium WebDriver"""
    try:
        ua = UserAgent()
        options = Options()
        options.add_argument('--headless')  # Запускаем в фоновом режиме
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--blink-settings=imagesEnabled=false')  # Отключаем загрузку изображений для скорости
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(f'user-agent={ua.random}')
        options.page_load_strategy = 'eager'  # Не ждем полной загрузки
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        print(f"Error creating Selenium driver: {e}")
        import traceback
        traceback.print_exc()
        return None

def _parse_sizes_prices_with_selenium(url: str) -> list:
    """Парсит размеры и цены используя Selenium (как в gitpars.py)"""
    driver = None
    try:
        print(f"  🚀 Using Selenium to parse sizes and prices from {url}")
        driver = _create_selenium_driver()
        if not driver:
            return []
        
        driver.get(url)
        time.sleep(3)  # Ждем загрузки страницы
        
        # Пробуем закрыть модальное окно, если есть
        try:
            button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.ant-modal-content>button')))
            driver.execute_script("arguments[0].click();", button)
            time.sleep(1)
        except:
            pass
        
        # Прокручиваем страницу вниз, чтобы загрузились все элементы
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)
        
        sizes_prices = []
        
        # Проверяем, есть ли вкладки размеров (как в gitpars.py)
        try:
            size_buttons = WebDriverWait(driver, 5).until(
                EC.visibility_of_all_elements_located((By.CSS_SELECTOR, 'div.SkuPanel_tabItem__MuUkW')))
            print(f"    Found {len(size_buttons)} size tab(s), parsing each tab...")
            
            # Парсим каждую вкладку
            for tab_idx, tab_button in enumerate(size_buttons):
                try:
                    driver.execute_script("arguments[0].click();", tab_button)
                    time.sleep(1)
                    
                    # Ищем размеры и цены в первой группе
                    size_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_value__BAJ1p')
                    price_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_price__KCs7G')
                    
                    if size_elements and price_elements:
                        for size_elem, price_elem in zip(size_elements, price_elements):
                            size = size_elem.get_attribute('textContent').strip()
                            price_text = price_elem.get_attribute('textContent').strip().replace('₽', '').replace('P', '').replace('$', '').replace(' ', '').replace('\xa0', '')
                            
                            try:
                                price_num = float(price_text.replace(',', ''))
                                # Если цена меньше 1000, возможно это в долларах, умножаем на 12.5
                                if price_num < 1000:
                                    price_num = price_num * 12.5
                                price_cents = int(price_num * 100)
                                
                                sizes_prices.append({'size': size, 'price': price_cents})
                                print(f"      ✅ Tab {tab_idx+1}: {size} -> {price_cents} копеек")
                            except:
                                pass
                except Exception as e:
                    print(f"      ⚠️ Error parsing tab {tab_idx+1}: {e}")
                    continue
        except:
            # Если нет вкладок, пробуем стандартный подход
            print(f"    No size tabs found, trying standard approach...")
            try:
                # Проверяем количество меню (как в gitpars.py)
                check_count_menu = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_label__Vbp8t>span:nth-child(1)')
                menu_count = len(check_count_menu)
                print(f"    Found {menu_count} menu(s)")
                
                if menu_count == 1:
                    # Одно меню: размеры и цены в nth-child(1)
                    # Ждем появления элементов
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX')))
                    except:
                        pass
                    
                    size_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_value__BAJ1p')
                    price_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(1) div.SkuPanel_price__KCs7G')
                    
                    print(f"    Found {len(size_elements)} size elements, {len(price_elements)} price elements")
                    
                    if size_elements and price_elements:
                        for size_elem, price_elem in zip(size_elements, price_elements):
                            size = size_elem.get_attribute('textContent').strip()
                            # Извлекаем только RU размер (до скобки, если есть)
                            if '(' in size:
                                size = size.split('(')[0].strip()
                            price_text = price_elem.get_attribute('textContent').strip().replace('₽', '').replace('P', '').replace('$', '').replace(' ', '').replace('\xa0', '')
                            
                            try:
                                price_num = float(price_text.replace(',', ''))
                                if price_num < 1000:
                                    price_num = price_num * 12.5
                                price_cents = int(price_num * 100)
                                
                                sizes_prices.append({'size': size, 'price': price_cents})
                                print(f"      ✅ {size} -> {price_cents} копеек")
                            except Exception as e:
                                print(f"      ⚠️ Error parsing {size} -> {price_text}: {e}")
                                pass
                elif menu_count == 2:
                    # Два меню (цвет): размеры и цены в nth-child(2)
                    color_buttons = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_list__OUqa1.SkuPanel_col4__UYcTN.SkuPanel_imgList__7Uem4>div')
                    for color_button in color_buttons:
                        try:
                            driver.execute_script("arguments[0].click();", color_button)
                            time.sleep(1)
                            
                            size_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(2) div.SkuPanel_value__BAJ1p')
                            price_elements = driver.find_elements(By.CSS_SELECTOR, 'div.SkuPanel_group__egmoX:nth-child(2) div.SkuPanel_price__KCs7G')
                            
                            if size_elements and price_elements:
                                for size_elem, price_elem in zip(size_elements, price_elements):
                                    size = size_elem.get_attribute('textContent').strip()
                                    price_text = price_elem.get_attribute('textContent').strip().replace('₽', '').replace('P', '').replace('$', '').replace(' ', '').replace('\xa0', '')
                                    
                                    try:
                                        price_num = float(price_text.replace(',', ''))
                                        if price_num < 1000:
                                            price_num = price_num * 12.5
                                        price_cents = int(price_num * 100)
                                        
                                        sizes_prices.append({'size': size, 'price': price_cents})
                                        print(f"      ✅ {size} -> {price_cents} копеек")
                                    except:
                                        pass
                        except:
                            continue
            except Exception as e:
                print(f"    ⚠️ Error in standard approach: {e}")
        
        print(f"  ✅ Selenium found {len(sizes_prices)} size-price pairs")
        return sizes_prices
        
    except Exception as e:
        print(f"  ❌ Error using Selenium: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

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
                            # Приоритет: detailImageList (основные фото товара в правильном порядке)
                            images_data = product_data.get('detailImageList')
                            if not images_data:
                                # Fallback на другие источники
                                images_data = (product_data.get('images') or 
                                             product_data.get('imageList') or
                                             product_data.get('imageUrls') or
                                             product_data.get('spuImages') or
                                             product_data.get('mainImages') or
                                             product_data.get('detailImages') or
                                             product_data.get('goodsImages') or
                                             product_data.get('goodsImageList'))
                            # sizeImageList - это изображения размеров, не товара, пропускаем
                            
                            print(f"  DEBUG: images_data type: {type(images_data)}")
                            if isinstance(images_data, list):
                                print(f"  DEBUG: images_data list length: {len(images_data)}")
                                if len(images_data) > 0:
                                    print(f"  DEBUG: First image item type: {type(images_data[0])}, value: {str(images_data[0])[:100]}")
                                    if isinstance(images_data[0], dict):
                                        print(f"  DEBUG: First image item keys: {list(images_data[0].keys())[:10]}")
                        
                        if images_data:
                            if isinstance(images_data, list):
                                print(f"  📸 Found {len(images_data)} images in detailImageList, processing in order...")
                                # Сортируем по полю 'sort' или 'genericTypeSort' если оно есть, чтобы сохранить правильный порядок
                                if all(isinstance(img, dict) for img in images_data):
                                    # Пробуем сортировать по 'sort', если нет - по 'genericTypeSort'
                                    if all('sort' in img for img in images_data):
                                        images_data = sorted(images_data, key=lambda x: x.get('sort', 0))
                                        print(f"  📸 Sorted images by 'sort' field")
                                    elif all('genericTypeSort' in img for img in images_data):
                                        images_data = sorted(images_data, key=lambda x: x.get('genericTypeSort', 0))
                                        print(f"  📸 Sorted images by 'genericTypeSort' field")
                                # Берем все изображения в порядке из detailImageList (это правильный порядок с сайта)
                                for idx, img in enumerate(images_data):
                                    if idx >= 10:  # Максимум 10 изображений
                                        break
                                    
                                    img_url = None
                                    if isinstance(img, str):
                                        img_url = img
                                    elif isinstance(img, dict):
                                        # detailImageList содержит объекты с ключом 'url' (видно в логах: ['imageId', 'sort', 'genericType', 'genericTypeSort', 'url', 'imgType', 'burialImgType'])
                                        # Сортируем по полю 'sort' если оно есть, чтобы сохранить правильный порядок
                                        img_url = (img.get('url') or 
                                                  img.get('src') or 
                                                  img.get('imageUrl') or 
                                                  img.get('originUrl') or
                                                  img.get('image') or
                                                  img.get('originalUrl') or
                                                  img.get('largeUrl') or
                                                  img.get('imgUrl'))
                                    
                                    if img_url:
                                        # Пропускаем AI-изображения
                                        img_url_lower = img_url.lower()
                                        if 'ai/generate' in img_url_lower or 'ai_generate' in img_url_lower:
                                            print(f"  ⏭️ Skipping AI-generated image {idx+1}: {img_url[:80]}...")
                                            continue
                                        
                                        # Нормализуем URL
                                        if img_url.startswith('//'):
                                            img_url = 'https:' + img_url
                                        elif img_url.startswith('/'):
                                            img_url = base_domain + img_url
                                        
                                        if img_url.startswith('http') and img_url not in images:
                                            images.append(img_url)  # Пока сохраняем как URL
                                            print(f"    ✅ Added image {idx+1} from __NEXT_DATA__: {img_url[:80]}...")
                            elif isinstance(images_data, str):
                                # Если одно изображение, тоже пропускаем
                                pass
                        
                        print(f"Found {len(images)} image URLs from __NEXT_DATA__")
                        
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
                                first_sku = skus[0]
                                if 'properties' in first_sku:
                                    print(f"  DEBUG: First SKU properties type: {type(first_sku['properties'])}")
                                    if isinstance(first_sku['properties'], dict):
                                        print(f"  DEBUG: First SKU properties keys: {list(first_sku['properties'].keys())[:10]}")
                                    elif isinstance(first_sku['properties'], list):
                                        print(f"  DEBUG: First SKU properties list length: {len(first_sku['properties'])}")
                                        if len(first_sku['properties']) > 0:
                                            print(f"  DEBUG: First property item: {first_sku['properties'][0]}")
                            
                            # Строим маппинг propertyValueId -> значение размера из baseProperties
                            size_mapping = {}
                            if 'baseProperties' in product_data:
                                base_props = product_data['baseProperties']
                                print(f"  DEBUG: baseProperties type: {type(base_props)}")
                                if isinstance(base_props, list):
                                    print(f"  DEBUG: baseProperties list length: {len(base_props)}")
                                    # Выводим все группы для анализа
                                    for idx, prop_group in enumerate(base_props):
                                        if isinstance(prop_group, dict):
                                            prop_name = prop_group.get('propertyName') or prop_group.get('name') or prop_group.get('propertyType') or ''
                                            # Проверяем поле 'value' - возможно, там размер
                                            prop_value = prop_group.get('value')
                                            print(f"    baseProperties[{idx}]: propertyName='{prop_name}', value='{prop_value}', keys={list(prop_group.keys())[:10]}")
                                            
                                            # Если в 'value' есть число, похожее на размер
                                            if prop_value and re.search(r'\d+[,.]?\d*', str(prop_value)):
                                                # Проверяем, есть ли propertyValueId в этом элементе
                                                value_id = prop_group.get('propertyValueId') or prop_group.get('id') or prop_group.get('key')
                                                if value_id:
                                                    size_mapping[value_id] = str(prop_value)
                                                    print(f"      ✅ Mapped size from value: {value_id} -> {prop_value}")
                                            
                                            # Ищем группу с размерами (может быть 'размер', 'Size', 'size', 'RU', 'EU' и т.д.)
                                            prop_name_lower = str(prop_name).lower()
                                            if any(keyword in prop_name_lower for keyword in ['size', 'размер', 'разм']):
                                                print(f"      ✅ Found size group: '{prop_name}'")
                                                # В values могут быть размеры
                                                values = prop_group.get('values') or prop_group.get('propertyValues') or prop_group.get('propertyValueList') or []
                                                if isinstance(values, list):
                                                    print(f"        Found {len(values)} size values")
                                                    for val in values:
                                                        if isinstance(val, dict):
                                                            value_id = val.get('propertyValueId') or val.get('id') or val.get('propertyValueId')
                                                            value_text = val.get('propertyValue') or val.get('value') or val.get('name') or val.get('text') or val.get('propertyValueText')
                                                            if value_id and value_text:
                                                                size_mapping[value_id] = value_text
                                                                print(f"          Mapped size: {value_id} -> {value_text}")
                                                break  # Нашли группу размеров
                                            
                                            # Если не нашли по имени, пробуем все группы
                                            values = prop_group.get('values') or prop_group.get('propertyValues') or []
                                            if isinstance(values, list) and len(values) > 0:
                                                # Проверяем, похожи ли значения на размеры (содержат числа)
                                                first_val = values[0]
                                                if isinstance(first_val, dict):
                                                    val_text = str(first_val.get('propertyValue') or first_val.get('value') or first_val.get('name') or '')
                                                    # Если значение похоже на размер (содержит числа и возможно запятую/точку)
                                                    if re.search(r'\d+[,.]?\d*', val_text):
                                                        print(f"      🔍 Possible size group found (by value pattern): '{prop_name}'")
                                                        for val in values:
                                                            if isinstance(val, dict):
                                                                value_id = val.get('propertyValueId') or val.get('id')
                                                                value_text = val.get('propertyValue') or val.get('value') or val.get('name') or val.get('text')
                                                                if value_id and value_text:
                                                                    size_mapping[value_id] = value_text
                                                                    print(f"          Mapped size: {value_id} -> {value_text}")
                                                        if size_mapping:
                                                            break  # Нашли и заполнили маппинг
                                elif isinstance(base_props, dict):
                                    # Если baseProperties - словарь, пробуем найти внутри
                                    print(f"  DEBUG: baseProperties is dict, keys: {list(base_props.keys())[:10]}")
                                    for key, value in base_props.items():
                                        if isinstance(value, list):
                                            for item in value:
                                                if isinstance(item, dict):
                                                    value_id = item.get('propertyValueId') or item.get('id')
                                                    value_text = item.get('propertyValue') or item.get('value') or item.get('name')
                                                    if value_id and value_text:
                                                        size_mapping[value_id] = value_text
                            
                            # Пробуем найти цены для каждого SKU - возможно, цены в каждом SKU или в отдельном массиве
                            sku_price_mapping = {}  # skuId -> price
                            
                            # Сначала ищем цены в каждом SKU - детальный поиск
                            print(f"  DEBUG: Searching for prices in {len(skus)} SKUs...")
                            for idx, sku in enumerate(skus):
                                sku_id = sku.get('skuId')
                                if idx < 3:  # Логируем первые 3 SKU для анализа
                                    print(f"    SKU {idx+1} (skuId={sku_id}) keys: {list(sku.keys())[:15]}")
                                
                                # Ищем цену в самом SKU - расширенный поиск
                                sku_price = (sku.get('price') or 
                                            sku.get('salePrice') or 
                                            sku.get('currentPrice') or
                                            sku.get('priceValue') or
                                            sku.get('priceInfo') or
                                            sku.get('money') or
                                            sku.get('lowPrice') or
                                            sku.get('highPrice'))
                                
                                # Если price - словарь, извлекаем значение
                                if isinstance(sku_price, dict):
                                    sku_price = (sku_price.get('minUnitVal') or 
                                                sku_price.get('amount') or
                                                sku_price.get('money') or
                                                sku_price.get('price') or
                                                sku_price.get('salePrice'))
                                
                                if sku_price and sku_id:
                                    sku_price_mapping[sku_id] = sku_price
                                    if idx < 3:
                                        print(f"      Found price in SKU: {sku_price}")
                            
                            # Ищем цены в других местах product_data
                            print(f"  DEBUG: Searching for price arrays in product_data...")
                            price_related_keys = [k for k in product_data.keys() if any(word in str(k).lower() for word in ['price', 'sku', 'money', 'cost'])]
                            if price_related_keys:
                                print(f"    Found price-related keys: {price_related_keys}")
                                for key in price_related_keys:
                                    value = product_data[key]
                                    if isinstance(value, list) and len(value) > 0:
                                        print(f"      {key} is a list with {len(value)} items")
                                        if isinstance(value[0], dict):
                                            print(f"        First item keys: {list(value[0].keys())[:10]}")
                                            # Пробуем построить маппинг
                                            for item in value:
                                                if isinstance(item, dict):
                                                    item_sku_id = item.get('skuId') or item.get('id') or item.get('sku')
                                                    item_price = (item.get('price') or 
                                                                item.get('money') or
                                                                item.get('salePrice') or
                                                                item.get('currentPrice') or
                                                                item.get('priceValue'))
                                                    if isinstance(item_price, dict):
                                                        item_price = item_price.get('minUnitVal') or item_price.get('amount')
                                                    if item_price and item_sku_id:
                                                        sku_price_mapping[item_sku_id] = item_price
                                                        print(f"          Mapped price: skuId={item_sku_id}, price={item_price}")
                                    elif isinstance(value, dict):
                                        print(f"      {key} is a dict with keys: {list(value.keys())[:10]}")
                                        # Особый случай: skuMinPriceInfoDTO может содержать цены
                                        if key == 'skuMinPriceInfoDTO':
                                            print(f"        🔍 Analyzing skuMinPriceInfoDTO structure...")
                                            # minPrice или authPrice могут содержать цену
                                            min_price = value.get('minPrice')
                                            auth_price = value.get('authPrice')
                                            sku_id_dto = value.get('skuId')
                                            print(f"          minPrice: {min_price}, authPrice: {auth_price}, skuId: {sku_id_dto}")
                                            if min_price and sku_id_dto:
                                                # Если minPrice - словарь
                                                if isinstance(min_price, dict):
                                                    price_val = min_price.get('minUnitVal') or min_price.get('amount') or min_price.get('money')
                                                    # Если minUnitVal - это число, используем его (уже в копейках)
                                                    if isinstance(price_val, (int, float)) and price_val >= 1000:
                                                        pass  # Уже в копейках
                                                    elif isinstance(price_val, str):
                                                        try:
                                                            price_val = float(price_val)
                                                            if price_val >= 1000:
                                                                price_val = int(price_val)  # Уже в копейках
                                                            else:
                                                                price_val = int(price_val * 100)  # В рублях, конвертируем
                                                        except:
                                                            pass
                                                else:
                                                    price_val = min_price
                                                if price_val:
                                                    # Сохраняем только числовое значение, не словарь
                                                    if isinstance(price_val, dict):
                                                        # Сохраняем оригинальный словарь для извлечения
                                                        price_dict = price_val
                                                        price_val = price_dict.get('minUnitVal')
                                                        if price_val is None:
                                                            amount = price_dict.get('amount')
                                                            if amount:
                                                                try:
                                                                    amount_num = float(str(amount))
                                                                    price_val = int(amount_num * 100) if amount_num < 1000 else int(amount_num)
                                                                except:
                                                                    price_val = None
                                                    if price_val:
                                                        sku_price_mapping[sku_id_dto] = price_val
                                                        print(f"          ✅ Mapped price from minPrice: skuId={sku_id_dto}, price={price_val}")
                                            if auth_price and sku_id_dto and sku_id_dto not in sku_price_mapping:
                                                if isinstance(auth_price, dict):
                                                    price_val = auth_price.get('minUnitVal') or auth_price.get('amount') or auth_price.get('money')
                                                    if isinstance(price_val, (int, float)) and price_val >= 1000:
                                                        pass
                                                    elif isinstance(price_val, str):
                                                        try:
                                                            price_val = float(price_val)
                                                            if price_val >= 1000:
                                                                price_val = int(price_val)
                                                            else:
                                                                price_val = int(price_val * 100)
                                                        except:
                                                            pass
                                                else:
                                                    price_val = auth_price
                                                if price_val:
                                                    sku_price_mapping[sku_id_dto] = price_val
                                                    print(f"          ✅ Mapped price from authPrice: skuId={sku_id_dto}, price={price_val}")
                                        
                                        # Особый случай: levelOneMinPriceSkus может содержать маппинг propertyValueId -> цены
                                        # ВАЖНО: levelOneMinPriceSkus содержит только минимальную цену для одного propertyValueId,
                                        # НЕ индивидуальные цены для каждого размера! Нужно искать цены в других местах.
                                        elif key == 'levelOneMinPriceSkus':
                                            print(f"        🔍 Analyzing levelOneMinPriceSkus structure...")
                                            print(f"        ⚠️ NOTE: levelOneMinPriceSkus usually contains only min price, not individual prices per size")
                                            for prop_value_id, price_info in value.items():
                                                print(f"          propertyValueId={prop_value_id}, price_info type={type(price_info)}")
                                                if isinstance(price_info, dict):
                                                    print(f"            price_info keys: {list(price_info.keys())[:10]}")
                                                    # Ищем цену в структуре - minPrice может быть словарем
                                                    min_price_obj = price_info.get('minPrice')
                                                    if isinstance(min_price_obj, dict):
                                                        # Извлекаем minUnitVal (уже в копейках)
                                                        price_val = min_price_obj.get('minUnitVal')
                                                        if not price_val:
                                                            # Если нет minUnitVal, пробуем amount и конвертируем
                                                            amount = min_price_obj.get('amount')
                                                            if amount:
                                                                try:
                                                                    amount_num = float(str(amount))
                                                                    if amount_num >= 1000:
                                                                        price_val = int(amount_num)  # Уже в копейках
                                                                    else:
                                                                        price_val = int(amount_num * 100)  # В рублях
                                                                except:
                                                                    pass
                                                    else:
                                                        price_val = min_price_obj
                                                    
                                                    # Если не нашли, пробуем authPrice
                                                    if not price_val:
                                                        auth_price_obj = price_info.get('authPrice')
                                                        if isinstance(auth_price_obj, dict):
                                                            price_val = auth_price_obj.get('minUnitVal') or auth_price_obj.get('amount')
                                                        else:
                                                            price_val = auth_price_obj
                                                    
                                                    if price_val:
                                                        # ВАЖНО: levelOneMinPriceSkus содержит только минимальную цену,
                                                        # НЕ используем её для всех SKU, только как fallback
                                                        print(f"          Found min price in levelOneMinPriceSkus: {price_val} (will use as fallback only)")
                                                        # НЕ добавляем в маппинг, чтобы не перезаписать индивидуальные цены
                                                elif isinstance(price_info, (int, float, str)):
                                                    # Возможно, прямое значение цены
                                                    try:
                                                        price_num = float(price_info)
                                                        if price_num > 100:  # Разумная цена
                                                            # Находим все SKU с этим propertyValueId
                                                            for sku_item in skus:
                                                                sku_props = sku_item.get('properties', [])
                                                                if isinstance(sku_props, list):
                                                                    for prop in sku_props:
                                                                        if isinstance(prop, dict):
                                                                            prop_id = prop.get('propertyValueId')
                                                                            if prop_id == prop_value_id or str(prop_id) == str(prop_value_id):
                                                                                sku_id_match = sku_item.get('skuId')
                                                                                if sku_id_match and sku_id_match not in sku_price_mapping:
                                                                                    sku_price_mapping[sku_id_match] = price_num
                                                                                    print(f"          ✅ Mapped price (direct): propertyValueId={prop_value_id} -> skuId={sku_id_match}, price={price_num}")
                                                    except:
                                                        pass
                            
                            # Также пробуем найти массив цен в product_data
                            price_list = None
                            base_price_money = None
                            if 'price' in product_data:
                                price_data = product_data['price']
                                print(f"  DEBUG: price field type: {type(price_data)}")
                                if isinstance(price_data, dict):
                                    print(f"  DEBUG: price dict keys: {list(price_data.keys())[:10]}")
                                    # Возможно, цены в price.money (общая цена) или price.skuList
                                    base_price_money = price_data.get('money')  # Общая цена в центах/копейках
                                    if base_price_money:
                                        print(f"  DEBUG: Found base price money: {base_price_money}")
                                        # Если money - словарь, берем minUnitVal
                                        if isinstance(base_price_money, dict):
                                            base_price_money = base_price_money.get('minUnitVal') or base_price_money.get('amount')
                                    
                                    # Ищем список цен по SKU - расширенный поиск
                                    price_list = (price_data.get('skuList') or 
                                                 price_data.get('priceList') or
                                                 price_data.get('list') or
                                                 price_data.get('skus') or
                                                 price_data.get('skuPrices') or
                                                 price_data.get('skuPriceList') or
                                                 price_data.get('priceMap') or
                                                 price_data.get('skuPriceMap'))
                                    
                                    # Если есть массив цен, строим маппинг
                                    if price_list and isinstance(price_list, list):
                                        print(f"  DEBUG: Found price_list with {len(price_list)} items")
                                        for price_item in price_list:
                                            if isinstance(price_item, dict):
                                                item_sku_id = price_item.get('skuId') or price_item.get('id') or price_item.get('sku')
                                                item_price = (price_item.get('money') or 
                                                            price_item.get('price') or 
                                                            price_item.get('salePrice') or
                                                            price_item.get('currentPrice') or
                                                            price_item.get('priceValue') or
                                                            price_item.get('priceInfo'))
                                                if item_price and item_sku_id:
                                                    # Если price - словарь с minUnitVal
                                                    if isinstance(item_price, dict):
                                                        item_price = item_price.get('minUnitVal') or item_price.get('amount') or item_price.get('money')
                                                        # Если minUnitVal - это число, используем его (уже в копейках)
                                                        if isinstance(item_price, (int, float)) and item_price >= 1000:
                                                            pass  # Уже в копейках
                                                        elif isinstance(item_price, str):
                                                            try:
                                                                item_price = float(item_price)
                                                                if item_price >= 1000:
                                                                    item_price = int(item_price)  # Уже в копейках
                                                                else:
                                                                    item_price = int(item_price * 100)  # В рублях, конвертируем
                                                            except:
                                                                pass
                                                    if item_price:
                                                        sku_price_mapping[item_sku_id] = item_price
                                                        print(f"        Mapped price from price_list: skuId={item_sku_id}, price={item_price}")
                                    
                                    # Также проверяем, может быть price_data - это словарь с ключами-скидками
                                    if isinstance(price_data, dict):
                                        # Ищем вложенные структуры с ценами
                                        for key, value in price_data.items():
                                            if key != 'money' and isinstance(value, (list, dict)):
                                                if isinstance(value, list) and len(value) > 0:
                                                    if isinstance(value[0], dict):
                                                        # Возможно, это массив цен
                                                        for item in value:
                                                            if isinstance(item, dict):
                                                                item_sku_id = item.get('skuId') or item.get('id')
                                                                item_price = item.get('price') or item.get('money')
                                                                if isinstance(item_price, dict):
                                                                    item_price = item_price.get('minUnitVal') or item_price.get('amount')
                                                                if item_price and item_sku_id:
                                                                    sku_price_mapping[item_sku_id] = item_price
                                elif isinstance(price_data, list):
                                    price_list = price_data
                                    print(f"  DEBUG: price is a list with {len(price_list)} items")
                            
                            print(f"  DEBUG: Size mapping has {len(size_mapping)} entries")
                            print(f"  DEBUG: SKU price mapping has {len(sku_price_mapping)} entries")
                            
                            # Дополнительный поиск: проверяем, есть ли в product_data другие структуры с ценами
                            # Проверяем, все ли цены одинаковые (сначала извлекаем числовые значения)
                            unique_price_values = set()
                            for price_val in sku_price_mapping.values():
                                if isinstance(price_val, dict):
                                    # Извлекаем minUnitVal или amount
                                    num_val = price_val.get('minUnitVal')
                                    if num_val is None:
                                        amount = price_val.get('amount')
                                        if amount:
                                            try:
                                                num_val = float(str(amount))
                                                if num_val < 1000:
                                                    num_val = int(num_val * 100)
                                                else:
                                                    num_val = int(num_val)
                                            except:
                                                pass
                                    if num_val is not None:
                                        unique_price_values.add(num_val)
                                elif isinstance(price_val, (int, float)):
                                    unique_price_values.add(price_val)
                            
                            if len(sku_price_mapping) == 0 or len(unique_price_values) <= 1:
                                print(f"  ⚠️ All prices are the same or no prices found. Searching for individual prices...")
                                # Ищем все возможные места с ценами
                                for key, value in product_data.items():
                                    if isinstance(value, (list, dict)):
                                        # Пробуем найти структуры, которые могут содержать цены по SKU
                                        if isinstance(value, list) and len(value) > 0:
                                            first_item = value[0]
                                            if isinstance(first_item, dict):
                                                # Проверяем, есть ли в элементах skuId и price
                                                if 'skuId' in first_item and any(price_key in first_item for price_key in ['price', 'money', 'minPrice', 'salePrice']):
                                                    print(f"    🔍 Found potential price list in '{key}' with {len(value)} items")
                                                    for item in value:
                                                        item_sku_id = item.get('skuId')
                                                        item_price = (item.get('price') or 
                                                                    item.get('money') or
                                                                    item.get('minPrice') or
                                                                    item.get('salePrice'))
                                                        if isinstance(item_price, dict):
                                                            item_price = item_price.get('minUnitVal') or item_price.get('amount')
                                                        if item_price and item_sku_id:
                                                            sku_price_mapping[item_sku_id] = item_price
                                                            print(f"      ✅ Found individual price: skuId={item_sku_id}, price={item_price}")
                            
                            if not size_mapping:
                                print(f"  ⚠️ No size mapping found in baseProperties, trying alternative approach...")
                            
                            for idx, sku in enumerate(skus):
                                # Извлекаем размер из properties через propertyValueId -> baseProperties маппинг
                                size = None
                                properties = sku.get('properties')
                                
                                if isinstance(properties, list):
                                    # properties - список объектов с propertyValueId
                                    for prop in properties:
                                        if isinstance(prop, dict):
                                            property_value_id = prop.get('propertyValueId') or prop.get('id')
                                            if property_value_id:
                                                # Ищем значение размера в маппинге
                                                if property_value_id in size_mapping:
                                                    size = size_mapping[property_value_id]
                                                    print(f"    SKU {idx+1}: Found size via mapping {property_value_id} -> {size}")
                                                    break
                                
                                # Если не нашли через маппинг, пробуем извлечь из skuTitle (но только число размера)
                                if not size:
                                    sku_title = sku.get('skuTitle') or ''
                                    # Ищем паттерн размера в конце названия (число с запятой/точкой)
                                    if sku_title:
                                        # Ищем паттерн типа "43,5" или "43.5" в конце строки
                                        size_match = re.search(r'(\d+[,.]?\d*)\s*$', sku_title.strip())
                                        if size_match:
                                            size = size_match.group(1).replace(',', ',')  # Оставляем запятую как есть
                                            print(f"    SKU {idx+1}: Extracted size from skuTitle: '{size}'")
                                
                                # Если не нашли размер в properties, пробуем другие поля
                                if not size:
                                    size = (sku.get('size') or 
                                           sku.get('sizeName') or 
                                           sku.get('specValue') or
                                           sku.get('sizeValue') or
                                           sku.get('sizeText') or
                                           sku.get('sizeLabel') or
                                           sku.get('sizeNameCn') or
                                           sku.get('sizeNameEn'))
                                
                                # Если размер все еще содержит название товара, извлекаем только числовую часть
                                if size and len(size) > 10:
                                    # Пробуем найти число в конце
                                    size_match = re.search(r'(\d+[,.]?\d*)\s*$', size.strip())
                                    if size_match:
                                        size = size_match.group(1).replace(',', ',')
                                        print(f"    SKU {idx+1}: Cleaned size to: '{size}'")
                                
                                # Ищем цену для этого SKU
                                price_value = None
                                sku_id = sku.get('skuId')
                                
                                # Сначала пробуем найти цену в маппинге цен по SKU
                                if sku_id and sku_id in sku_price_mapping:
                                    price_value_raw = sku_price_mapping[sku_id]
                                    # Если price_value_raw - словарь, извлекаем minUnitVal (уже в копейках)
                                    if isinstance(price_value_raw, dict):
                                        price_value = price_value_raw.get('minUnitVal')
                                        if price_value is None:
                                            # Если нет minUnitVal, пробуем amount и конвертируем
                                            amount = price_value_raw.get('amount') or price_value_raw.get('money')
                                            if amount:
                                                try:
                                                    amount_num = float(str(amount))
                                                    if amount_num >= 1000:
                                                        price_value = int(amount_num)  # Уже в копейках
                                                    else:
                                                        price_value = int(amount_num * 100)  # В рублях
                                                except:
                                                    price_value = None
                                        elif isinstance(price_value, str):
                                            try:
                                                price_val_num = float(price_value)
                                                if price_val_num >= 1000:
                                                    price_value = int(price_val_num)
                                                else:
                                                    price_value = int(price_val_num * 100)
                                            except:
                                                price_value = None
                                    else:
                                        price_value = price_value_raw
                                    print(f"    SKU {idx+1}: Found price in mapping: {price_value} (type: {type(price_value)})")
                                else:
                                    # Пробуем найти цену в самом SKU - расширенный поиск
                                    price_value = (sku.get('price') or 
                                                 sku.get('salePrice') or 
                                                 sku.get('currentPrice') or
                                                 sku.get('priceValue') or
                                                 sku.get('lowPrice') or
                                                 sku.get('highPrice') or
                                                 sku.get('money'))
                                    
                                    # Если price - словарь с money/minUnitVal
                                    if isinstance(price_value, dict):
                                        price_value = price_value.get('minUnitVal') or price_value.get('amount') or price_value.get('money')
                                    
                                    # Пробуем найти в priceInfo
                                    if not price_value:
                                        price_info = sku.get('priceInfo')
                                        if isinstance(price_info, dict):
                                            price_value = (price_info.get('money') or
                                                         price_info.get('price') or
                                                         price_info.get('salePrice') or
                                                         price_info.get('currentPrice'))
                                            if isinstance(price_value, dict):
                                                price_value = price_value.get('minUnitVal') or price_value.get('amount')
                                    
                                    # Если не нашли, пробуем найти в price_list по skuId
                                    if not price_value and price_list and isinstance(price_list, list) and sku_id:
                                        for price_item in price_list:
                                            if isinstance(price_item, dict):
                                                if price_item.get('skuId') == sku_id or price_item.get('id') == sku_id:
                                                    # Цена может быть в price_item.money или напрямую
                                                    price_value = (price_item.get('money') or
                                                                 price_item.get('price') or 
                                                                 price_item.get('salePrice') or
                                                                 price_item.get('currentPrice') or
                                                                 price_item.get('priceValue'))
                                                    # Если price - словарь
                                                    if isinstance(price_value, dict):
                                                        price_value = price_value.get('minUnitVal') or price_value.get('amount')
                                                    if price_value:
                                                        print(f"    SKU {idx+1}: Found price in price_list: {price_value}")
                                                    break
                                    
                                    # Если не нашли, пробуем найти в product_data по skuId (может быть отдельный массив)
                                    if not price_value and sku_id:
                                        # Ищем во всех массивах product_data
                                        for key, value in product_data.items():
                                            if isinstance(value, list) and len(value) > 0:
                                                for item in value:
                                                    if isinstance(item, dict):
                                                        item_sku_id = item.get('skuId') or item.get('id')
                                                        if item_sku_id == sku_id:
                                                            item_price = (item.get('price') or 
                                                                        item.get('money') or
                                                                        item.get('salePrice') or
                                                                        item.get('currentPrice'))
                                                            if isinstance(item_price, dict):
                                                                item_price = item_price.get('minUnitVal') or item_price.get('amount')
                                                            if item_price:
                                                                price_value = item_price
                                                                print(f"    SKU {idx+1}: Found price in product_data['{key}']: {price_value}")
                                                                break
                                                    if price_value:
                                                        break
                                                if price_value:
                                                    break
                                
                                # Если не нашли индивидуальную цену, используем базовую цену (для всех размеров одинаковая)
                                if not price_value and base_price_money is not None:
                                    price_value = base_price_money
                                    print(f"    SKU {idx+1}: Using base price {price_value} (no individual price found)")
                                
                                # Если не нашли напрямую, пробуем вложенные структуры
                                if not price_value and isinstance(sku, dict):
                                    price_info = sku.get('priceInfo') or sku.get('price')
                                    if isinstance(price_info, dict):
                                        price_value = (price_info.get('money') or
                                                     price_info.get('price') or 
                                                     price_info.get('salePrice') or
                                                     price_info.get('currentPrice'))
                                
                                if size and price_value:
                                    try:
                                        # Цена может быть в разных форматах
                                        price_cents = None
                                        
                                        if isinstance(price_value, dict):
                                            # Если это словарь, извлекаем minUnitVal (уже в копейках)
                                            price_cents = price_value.get('minUnitVal')
                                            if price_cents is None:
                                                # Если нет minUnitVal, пробуем amount и конвертируем
                                                amount = price_value.get('amount')
                                                if amount:
                                                    try:
                                                        amount_num = float(str(amount))
                                                        if amount_num >= 1000:
                                                            price_cents = int(amount_num)  # Уже в копейках
                                                        else:
                                                            price_cents = int(amount_num * 100)  # В рублях
                                                    except:
                                                        pass
                                        
                                        elif isinstance(price_value, (int, float)):
                                            # Если число большое (>= 1000), возможно это уже в копейках
                                            if price_value >= 1000:
                                                price_cents = int(price_value)
                                            else:
                                                price_cents = int(price_value * 100)  # Предполагаем рубли
                                        else:
                                            # Строка - парсим
                                            price_str = str(price_value).replace(' ', '').replace(',', '').replace('₽', '').replace('₴', '')
                                            price_num = float(re.sub(r'[^\d.]', '', price_str))
                                            if price_num >= 1000:
                                                price_cents = int(price_num)
                                            else:
                                                price_cents = int(price_num * 100)
                                        
                                        if price_cents and 100 <= price_cents <= 10000000:  # Разумный диапазон
                                            sizes_prices.append({
                                                'size': str(size),
                                                'price': price_cents
                                            })
                                            print(f"  SKU {idx+1}: size={size}, price={price_cents} копеек")
                                        else:
                                            print(f"  SKU {idx+1}: Invalid price value: {price_value} -> {price_cents}")
                                    except Exception as e:
                                        print(f"  Error parsing SKU {idx+1}: {e}")
                                        import traceback
                                        traceback.print_exc()
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
                            price_value = None
                            price_data = product_data.get('price')
                            
                            # Если price - словарь, ищем цену внутри (в логах видели 'money')
                            if isinstance(price_data, dict):
                                price_value = (price_data.get('money') or  # Основная цена в центах/копейках
                                             price_data.get('price') or 
                                             price_data.get('salePrice') or
                                             price_data.get('currentPrice') or
                                             price_data.get('lowPrice') or
                                             price_data.get('minPrice') or
                                             price_data.get('maxPrice'))
                            elif isinstance(price_data, (int, float)):
                                price_value = price_data
                            elif price_data is None:
                                # Пробуем другие поля
                                price_value = (product_data.get('salePrice') or
                                             product_data.get('currentPrice') or
                                             product_data.get('lowPrice'))
                            
                            if price_value:
                                try:
                                    if isinstance(price_value, (int, float)):
                                        # Проверяем разумность
                                        if price_value > 100000:
                                            print(f"  ⚠️ Main price too large ({price_value}), skipping")
                                        elif price_value >= 1000:
                                            price = int(price_value)  # Уже в копейках
                                        else:
                                            price = int(price_value * 100)
                                    else:
                                        price_str = str(price_value).replace(' ', '').replace(',', '')
                                        price_num = float(re.sub(r'[^\d.]', '', price_str))
                                        if price_num > 100000:
                                            print(f"  ⚠️ Main price too large ({price_num} руб), skipping")
                                        elif price_num >= 1000:
                                            price = int(price_num)
                                        else:
                                            price = int(price_num * 100)
                                except Exception as e:
                                    print(f"  ❌ Error parsing main price: {e}")
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
                
                # Собираем все изображения, сохраняя порядок появления на странице
                all_img_elements = []
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
                            # Пропускаем миниатюры, иконки, логотипы, AI-изображения
                            img_url_lower = img_url.lower()
                            skip_keywords = ['thumb', 'icon', 'placeholder', 'logo', 'avatar', 'default', 'ai/generate', 'ai_generate']
                            if any(skip in img_url_lower for skip in skip_keywords):
                                continue
                            
                            # Нормализуем URL
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = base_domain + img_url
                            
                            if img_url.startswith('http'):
                                # Сохраняем URL и позицию для сортировки
                                if not any(item['url'] == img_url for item in all_img_elements):
                                    all_img_elements.append({
                                        'url': img_url,
                                        'position': len(all_img_elements)
                                    })
                                    print(f"    Added image: {img_url[:80]}...")
                
                # Сортируем по порядку появления на странице и добавляем в found_urls
                all_img_elements.sort(key=lambda x: x['position'])
                for item in all_img_elements:
                    if item['url'] not in found_urls:
                        found_urls.append(item['url'])
                
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
            
            # Скачиваем и конвертируем изображения (пропускаем первое, фильтруем AI-изображения)
            if found_urls:
                # Фильтруем изображения: убираем AI-изображения, пропускаем первое
                images_to_download = []
                ai_images = []
                
                for idx, img_url in enumerate(found_urls):
                    img_url_lower = img_url.lower()
                    
                    # Пропускаем AI-изображения
                    if 'ai/generate' in img_url_lower or 'ai_generate' in img_url_lower:
                        ai_images.append(img_url)
                        continue
                    
                    # Пропускаем первое изображение (как просил пользователь)
                    if idx == 0:
                        print(f"  ⏭️ Skipping first image: {img_url[:80]}...")
                        continue
                    
                    images_to_download.append(img_url)
                    if len(images_to_download) >= 10:
                        break
                
                # Если реальных изображений мало, добавляем AI-изображения в конец
                if len(images_to_download) < 5 and ai_images:
                    print(f"  ⚠️ Only {len(images_to_download)} real images found, adding {len(ai_images)} AI images...")
                    for ai_img in ai_images[:5]:
                        if len(images_to_download) >= 10:
                            break
                        images_to_download.append(ai_img)
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
            
            # Парсинг размеров и цен из HTML (даже если уже есть description, чтобы получить правильные цены)
            # Используем селекторы из Selenium кода
            html_sizes_prices = []
            
            # Если у нас уже есть sizes_prices из __NEXT_DATA__ но все цены одинаковые, 
            # пробуем найти индивидуальные цены из HTML
            need_html_prices = False
            if sizes_prices:
                # Проверяем, все ли цены одинаковые
                unique_prices = set(item['price'] for item in sizes_prices)
                if len(unique_prices) == 1:
                    need_html_prices = True
                    print(f"  ⚠️ All sizes have the same price ({list(unique_prices)[0]}), trying to find individual prices from HTML...")
            
            # Используем Selenium для парсинга размеров и цен, если они все одинаковые
            if need_html_prices:
                selenium_sizes_prices = _parse_sizes_prices_with_selenium(url)
                if selenium_sizes_prices:
                    print(f"  ✅ Got {len(selenium_sizes_prices)} size-price pairs from Selenium")
                    # Объединяем с существующими размерами
                    if sizes_prices:
                        selenium_price_map = {item['size']: item['price'] for item in selenium_sizes_prices}
                        for item in sizes_prices:
                            size_key = item['size']
                            if size_key in selenium_price_map:
                                item['price'] = selenium_price_map[size_key]
                                print(f"    ✅ Updated price for size {size_key}: {item['price']} копеек")
                    else:
                        sizes_prices = selenium_sizes_prices
            
            if not description or need_html_prices:
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
                                        
                                        html_sizes_prices.append({
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
                                        
                                        html_sizes_prices.append({
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
                                    
                                    html_sizes_prices.append({
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
                if not html_sizes_prices:
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
                                        
                                        html_sizes_prices.append({
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
                
                # Агрессивный поиск: ищем размеры и цены в любых элементах с числами и ценами
                # Всегда запускаем, даже если уже есть результаты
                print(f"  🔍 Aggressive search: Looking for size-price pairs in HTML...")
                try:
                    # Сначала пробуем найти размеры и цены в структурированных данных (JSON-LD)
                    json_ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in json_ld_scripts:
                        try:
                            import json
                            json_data = json.loads(script.string)
                            if isinstance(json_data, dict) and 'offers' in json_data:
                                offers = json_data.get('offers', [])
                                if isinstance(offers, list):
                                    for offer in offers:
                                        if isinstance(offer, dict):
                                            size = offer.get('itemOffered', {}).get('name', '')
                                            price = offer.get('price', '')
                                            if size and price:
                                                print(f"    ✅ Found size-price in JSON-LD: {size} -> {price}")
                        except:
                            pass
                    
                    # Сначала пробуем найти размеры и цены в data-атрибутах и структурированных данных
                    # Ищем элементы с data-атрибутами, содержащими размеры и цены
                    size_price_elements = soup.find_all(attrs={'data-size': True, 'data-price': True})
                    if size_price_elements:
                        print(f"    Found {len(size_price_elements)} elements with data-size and data-price")
                        for elem in size_price_elements:
                            size_val = elem.get('data-size', '').strip()
                            price_val = elem.get('data-price', '').strip()
                            if size_val and price_val:
                                try:
                                    price_num = float(price_val.replace(' ', '').replace(',', '').replace('₽', '').replace('P', ''))
                                    price_cents = int(price_num * 100)
                                    if 30 <= float(size_val.replace(',', '.')) <= 50 and 1000 <= price_cents <= 10000000:
                                        html_sizes_prices.append({'size': size_val, 'price': price_cents})
                                        print(f"    ✅ Found size-price in data-attributes: {size_val} -> {price_cents} копеек")
                                except:
                                    pass
                    
                    # Ищем в JavaScript переменных
                    script_tags = soup.find_all('script')
                    for script in script_tags:
                        if script.string and ('size' in script.string.lower() or 'price' in script.string.lower()):
                            # Пробуем найти размеры и цены в JavaScript
                            js_pattern = re.compile(r'["\']?size["\']?\s*[:=]\s*["\']?(\d+[,.]?\d*)["\']?\s*[,;].*?["\']?price["\']?\s*[:=]\s*["\']?(\d+(?:\s?\d{3})*)["\']?', re.IGNORECASE)
                            js_matches = js_pattern.findall(script.string)
                            if js_matches:
                                print(f"    Found {len(js_matches)} size-price pairs in JavaScript")
                                for size_str, price_str in js_matches:
                                    try:
                                        size_num = float(size_str.replace(',', '.'))
                                        price_num = float(price_str.replace(' ', '').replace(',', ''))
                                        price_cents = int(price_num * 100)
                                        if 30 <= size_num <= 50 and 1000 <= price_cents <= 10000000:
                                            html_sizes_prices.append({'size': size_str, 'price': price_cents})
                                            print(f"    ✅ Found size-price in JavaScript: {size_str} -> {price_cents} копеек")
                                    except:
                                        pass
                    
                    # Ищем все элементы, которые могут содержать размеры и цены
                    # Паттерн: размер (число с запятой) и цена (число с пробелами и ₽)
                    page_text = soup.get_text()
                    # Логируем небольшой фрагмент текста для отладки (ищем примеры размеров и цен)
                    if '37,5' in page_text or '41' in page_text:
                        # Находим фрагмент с размерами
                        idx = page_text.find('37,5') or page_text.find('41')
                        if idx > 0:
                            sample = page_text[max(0, idx-50):idx+200]
                            print(f"    DEBUG: Found size in text, sample: {sample[:150]}...")
                    
                    # Улучшенный паттерн: ищем "38 (39) 3 993 Р" или "40 (41) 3 741 Р" или "39,5 (40,5) 8 094 Р"
                    # ВАЖНО: размер должен быть строго в диапазоне 30-50, чтобы не находить части цены
                    # Ищем размер (30-50, может быть с запятой), затем опционально (EU размер), затем пробел и полная цена (минимум 4 цифры)
                    # Паттерн: размер (30-50 или 30.5-49.5), затем скобки с EU размером (опционально), затем пробел и цена (4+ цифр с пробелами)
                    # Паттерн 1: размер без запятой "37,5 (38,5) 15 720 ₽" или "41 (42) 12 696 ₽" или "37,5(38,5)12 881 ₽"
                    # Убрали обязательный пробел между скобками и ценой, так как в тексте может быть "37,5(38,5)12 881 ₽"
                    size_price_pattern = re.compile(
                        r'(?:^|[^\d])(3[0-9]|4[0-9]|50)(?:[,.]5)?(?:\([^)]+\))?\s*(\d{1,2}(?:\s?\d{3})+)\s*[₽РP]',
                        re.IGNORECASE | re.MULTILINE
                    )
                    
                    # Паттерн 2: размер с запятой "37,5 (38,5) 15 720 ₽" или "39,5 (40,5) 13 728 ₽" или "37,5(38,5)12 881 ₽"
                    size_price_pattern_comma = re.compile(
                        r'(?:^|[^\d])(3[0-9]|4[0-9]|50)[,.]5(?:\([^)]+\))?\s*(\d{1,2}(?:\s?\d{3})+)\s*[₽РP]',
                        re.IGNORECASE | re.MULTILINE
                    )
                    
                    # Паттерн 3: более простой - размер и цена без скобок "37,5 15 720 ₽"
                    size_price_pattern_simple = re.compile(
                        r'(?:^|[^\d])(3[0-9]|4[0-9]|50)(?:[,.]5)?\s+(\d{1,2}(?:\s?\d{3})+)\s*[₽РP]',
                        re.IGNORECASE | re.MULTILINE
                    )
                    
                    matches = size_price_pattern.findall(page_text)
                    matches_comma = size_price_pattern_comma.findall(page_text)
                    matches_simple = size_price_pattern_simple.findall(page_text)
                    # Объединяем результаты, убираем дубликаты
                    all_matches = matches + matches_comma + matches_simple
                    # Убираем дубликаты по размеру
                    seen = set()
                    unique_matches = []
                    for size_str, price_str in all_matches:
                        key = (size_str, price_str)
                        if key not in seen:
                            seen.add(key)
                            unique_matches.append((size_str, price_str))
                    print(f"    Found {len(unique_matches)} potential size-price pairs (main: {len(matches)}, comma: {len(matches_comma)}, simple: {len(matches_simple)}, unique: {len(unique_matches)})")
                    matches = unique_matches
                    
                    for idx, (size_str, price_str) in enumerate(matches):
                        try:
                            # Очищаем размер - оставляем запятую как есть
                            size_clean = size_str.strip()
                            
                            # Очищаем цену - убираем пробелы и неразрывные пробелы
                            price_clean = price_str.replace(' ', '').replace(',', '').replace('\xa0', '').replace('\u2009', '')
                            price_num = float(price_clean)
                            
                            # Цена уже в рублях, конвертируем в копейки
                            price_cents = int(price_num * 100)
                            
                            # Проверяем разумность: размер должен быть от 30 до 50, цена от 1000 до 100000 рублей
                            size_num = float(size_str.replace(',', '.'))
                            
                            # Детальное логирование для отладки
                            if idx < 5:  # Логируем первые 5 для анализа
                                print(f"    DEBUG: size_str='{size_str}', price_str='{price_str}' -> size_num={size_num}, price_cents={price_cents}")
                            
                            if 30 <= size_num <= 50 and 1000 <= price_cents <= 10000000:
                                # Проверяем, нет ли уже такого размера
                                existing = [sp for sp in html_sizes_prices if sp['size'] == size_clean]
                                if not existing:
                                    html_sizes_prices.append({
                                        'size': size_clean,
                                        'price': price_cents
                                    })
                                    print(f"    ✅ Found size-price pair: {size_clean} -> {price_cents} копеек ({price_num} руб)")
                                else:
                                    # Обновляем цену, если нашли более точную
                                    for sp in html_sizes_prices:
                                        if sp['size'] == size_clean:
                                            old_price = sp['price']
                                            sp['price'] = price_cents
                                            print(f"    🔄 Updated price for size {size_clean}: {old_price} -> {price_cents} копеек")
                                            break
                            else:
                                if idx < 5:
                                    print(f"    ⚠️ Rejected: size_num={size_num} (valid: 30-50), price_cents={price_cents} (valid: 1000-10000000)")
                        except Exception as e:
                            print(f"    ⚠️ Error parsing size-price pair '{size_str}' -> '{price_str}': {e}")
                            import traceback
                            traceback.print_exc()
                            pass
                except Exception as e:
                    print(f"  Error in aggressive search: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Если есть вкладки размеров (check_gender в оригинальном коде)
                if not html_sizes_prices:
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
                                            
                                            if not any(sp['size'] == size for sp in html_sizes_prices):
                                                html_sizes_prices.append({
                                                    'size': size,
                                                    'price': price_cents
                                                })
                                                print(f"    ✅ Found size: {size}, price: {price_cents} копеек")
                                    except Exception as e:
                                        pass
                    except Exception as e:
                        print(f"  Error parsing from size tabs: {e}")
                
                # Объединяем размеры из __NEXT_DATA__ с ценами из HTML
                if html_sizes_prices and sizes_prices:
                    print(f"  🔄 Merging {len(sizes_prices)} sizes from __NEXT_DATA__ with {len(html_sizes_prices)} prices from HTML...")
                    print(f"    HTML sizes: {[sp['size'] for sp in html_sizes_prices[:5]]}...")
                    print(f"    __NEXT_DATA__ sizes: {[sp['size'] for sp in sizes_prices[:5]]}...")
                    
                    # Создаем маппинг размер -> цена из HTML
                    html_price_map = {item['size']: item['price'] for item in html_sizes_prices}
                    
                    # Обновляем цены в sizes_prices
                    updated_count = 0
                    for item in sizes_prices:
                        size_key = item['size']
                        original_price = item['price']
                        
                        # Пробуем найти точное совпадение
                        if size_key in html_price_map:
                            item['price'] = html_price_map[size_key]
                            if item['price'] != original_price:
                                print(f"    ✅ Updated price for size {size_key}: {original_price} -> {item['price']} копеек")
                                updated_count += 1
                        else:
                            # Пробуем найти похожий размер (например, "43" и "43,0" или "38" и "38,5")
                            # Извлекаем числовое значение размера (убираем запятые, скобки и т.д.)
                            size_key_clean = size_key.split('(')[0].strip()  # Берем только до скобки
                            size_key_normalized = size_key_clean.replace(',', '.')
                            
                            for html_size, html_price in html_price_map.items():
                                html_size_clean = html_size.split('(')[0].strip()  # Берем только до скобки
                                html_size_normalized = html_size_clean.replace(',', '.')
                                
                                # Сравниваем числовые значения размеров
                                try:
                                    size_key_num = float(size_key_normalized)
                                    html_size_num = float(html_size_normalized)
                                    # Размеры совпадают если разница меньше 0.6 (например, 38 и 38,5)
                                    if abs(size_key_num - html_size_num) < 0.6:
                                        item['price'] = html_price
                                        if item['price'] != original_price:
                                            print(f"    ✅ Updated price for size {size_key} (matched {html_size}): {original_price} -> {item['price']} копеек")
                                            updated_count += 1
                                        break
                                except:
                                    pass
                    
                    print(f"  ✅ Updated prices for {updated_count} sizes")
            
            # Формируем описание из размеров и цен
            if sizes_prices:
                # Сортируем размеры от меньшего к большему
                def sort_key(item):
                    size_str = item['size'].split('(')[0].strip()  # Берем только RU размер
                    try:
                        return float(size_str.replace(',', '.'))
                    except:
                        return 0
                
                sizes_prices.sort(key=sort_key)
                print(f"  📊 Sorted {len(sizes_prices)} sizes from smallest to largest")
                
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
