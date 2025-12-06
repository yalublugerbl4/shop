import hmac
import hashlib
import urllib.parse
import json
from typing import Optional, Dict, Any


def parse_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Парсит строку initData от Telegram WebApp"""
    try:
        params = urllib.parse.parse_qs(init_data)
        
        user_param = params.get('user', [None])[0]
        hash_param = params.get('hash', [None])[0]
        auth_date = params.get('auth_date', [None])[0]
        
        if not user_param or not hash_param:
            return None
        
        user = json.loads(urllib.parse.unquote(user_param))
        
        return {
            'user': user,
            'auth_date': int(auth_date) if auth_date else 0,
            'hash': hash_param
        }
    except Exception:
        return None


def verify_init_data(init_data: str, bot_token: str) -> bool:
    """
    Проверяет подпись initData согласно алгоритму Telegram
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        params = urllib.parse.parse_qs(init_data)
        hash_param = params.get('hash', [None])[0]
        
        if not hash_param:
            return False
        
        # Удаляем hash из параметров
        params.pop('hash', None)
        
        # Сортируем параметры по ключу
        sorted_params = sorted(params.items())
        
        # Формируем data-check-string
        data_check_string = '\n'.join([f"{key}={value[0]}" for key, value in sorted_params])
        
        # Вычисляем секретный ключ
        secret_key = hmac.new(
            'WebAppData'.encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # Вычисляем подпись
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Проверяем, что подпись совпадает
        return calculated_hash == hash_param
    except Exception:
        return False


def extract_user_from_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Извлекает информацию о пользователе из initData"""
    parsed = parse_init_data(init_data)
    return parsed.get('user') if parsed else None

