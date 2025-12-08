from typing import Optional, List, Dict, Any
from app.db.connection import get_db_connection


def upsert_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Создать или обновить пользователя"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (tgid, username, first_name, last_name)
                VALUES (%(tgid)s, %(username)s, %(first_name)s, %(last_name)s)
                ON CONFLICT (tgid) 
                DO UPDATE SET 
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
                RETURNING *
                """,
                {
                    'tgid': user_data['tgid'],
                    'username': user_data.get('username'),
                    'first_name': user_data.get('first_name'),
                    'last_name': user_data.get('last_name')
                }
            )
            return dict(cur.fetchone())


def get_user_by_tgid(tgid: int) -> Optional[Dict[str, Any]]:
    """Получить пользователя по tgid"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE tgid = %s', (tgid,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_products(
    category: Optional[str] = None,
    season: Optional[str] = None,
    q: Optional[str] = None,
    size: Optional[str] = None,
    brand: Optional[str] = None
) -> List[Dict[str, Any]]:
    from app.utils.category_mapping import MAIN_CATEGORIES_WITH_SUBCATEGORIES
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = 'SELECT * FROM products WHERE is_active = true'
            params = []
            
            if category:
                if category in MAIN_CATEGORIES_WITH_SUBCATEGORIES:
                    subcategories = MAIN_CATEGORIES_WITH_SUBCATEGORIES[category]
                    all_values = [category] + subcategories
                    placeholders = ','.join(['%s'] * len(all_values))
                    query += f' AND category IN ({placeholders})'
                    params.extend(all_values)
                else:
                    query += ' AND category = %s'
                    params.append(category)
            
            if season:
                query += ' AND season = %s'
                params.append(season)
            
            if q:
                query += ' AND (title ILIKE %s OR description ILIKE %s)'
                search_term = f'%{q}%'
                params.extend([search_term, search_term])
            
            if size:
                size_pattern = f'%{size}:%'
                query += ' AND description ILIKE %s'
                params.append(size_pattern)
            
            if brand:
                brand_pattern = f'%{brand}%'
                query += ' AND title ILIKE %s'
                params.append(brand_pattern)
            
            query += ' ORDER BY created_at DESC'
            
            cur.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    """Получить товар по ID"""
    import json
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM products WHERE id = %s AND is_active = true',
                (product_id,)
            )
            row = cur.fetchone()
            if row:
                result = dict(row)
                # Парсим JSON обратно
                if isinstance(result.get('images_base64'), str):
                    result['images_base64'] = json.loads(result['images_base64'])
                if isinstance(result.get('size_guide'), str):
                    result['size_guide'] = json.loads(result['size_guide'])
                return result
            return None


def get_product_by_source_url(source_url: str) -> Optional[Dict[str, Any]]:
    """Получить товар по source_url"""
    import json
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM products WHERE source_url = %s AND is_active = true',
                (source_url,)
            )
            row = cur.fetchone()
            if row:
                result = dict(row)
                # Парсим JSON обратно
                if isinstance(result.get('images_base64'), str):
                    result['images_base64'] = json.loads(result['images_base64'])
                return result
            return None


def create_product(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Создать товар"""
    import json
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products (category, season, title, description, price_cents, images_base64, source_url, size_guide)
                VALUES (%(category)s, %(season)s, %(title)s, %(description)s, %(price_cents)s, %(images_base64)s, %(source_url)s, %(size_guide)s)
                RETURNING *
                """,
                {
                    'category': product_data['category'],
                    'season': product_data.get('season'),
                    'title': product_data['title'],
                    'description': product_data.get('description', ''),
                    'price_cents': product_data['price_cents'],
                    'images_base64': json.dumps(product_data.get('images_base64', [])),
                    'source_url': product_data.get('source_url'),
                    'size_guide': product_data.get('size_guide')
                }
            )
            row = cur.fetchone()
            result = dict(row)
            # Парсим JSON обратно
            if isinstance(result.get('images_base64'), str):
                result['images_base64'] = json.loads(result['images_base64'])
            if isinstance(result.get('size_guide'), str):
                result['size_guide'] = json.loads(result['size_guide'])
            return result


def update_product(
    product_id: str,
    updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Обновить товар"""
    import json
    if not updates:
        return get_product_by_id(product_id)
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Используем параметризованный запрос правильно
            placeholders = []
            params = []
            
            if 'category' in updates:
                placeholders.append('category = %s')
                params.append(updates['category'])
            if 'season' in updates:
                placeholders.append('season = %s')
                params.append(updates.get('season'))
            if 'title' in updates:
                placeholders.append('title = %s')
                params.append(updates['title'])
            if 'description' in updates:
                placeholders.append('description = %s')
                params.append(updates['description'])
            if 'price_cents' in updates:
                placeholders.append('price_cents = %s')
                params.append(updates['price_cents'])
            if 'images_base64' in updates:
                placeholders.append('images_base64 = %s')
                params.append(json.dumps(updates['images_base64']))
            if 'size_guide' in updates:
                placeholders.append('size_guide = %s')
                params.append(updates['size_guide'])
            
            if not placeholders:
                return get_product_by_id(product_id)
            
            params.append(product_id)
            query = f'UPDATE products SET {", ".join(placeholders)} WHERE id = %s RETURNING *'
            
            cur.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            if isinstance(result.get('images_base64'), str):
                result['images_base64'] = json.loads(result['images_base64'])
            if isinstance(result.get('size_guide'), str):
                result['size_guide'] = json.loads(result['size_guide'])
            return result


def delete_product(product_id: str) -> bool:
    """Удалить товар (soft delete)"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE products SET is_active = false WHERE id = %s',
                (product_id,)
            )
            return cur.rowcount > 0


def get_all_products_with_source_url() -> List[Dict[str, Any]]:
    """Получить все товары с source_url для обновления"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT id, source_url, title, price_cents FROM products WHERE is_active = true AND source_url IS NOT NULL'
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
