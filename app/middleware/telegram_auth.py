from fastapi import HTTPException, Header, Request
from typing import Optional
from app.config import settings
from app.utils.telegram_auth import verify_init_data, extract_user_from_init_data
from app.db import queries


async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None, alias="x-telegram-init-data")
) -> dict:
    """Dependency для получения текущего пользователя из initData"""
    if not x_telegram_init_data:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing x-telegram-init-data header"}}
        )
    
    if not verify_init_data(x_telegram_init_data, settings.telegram_bot_token):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid initData signature"}}
        )
    
    telegram_user = extract_user_from_init_data(x_telegram_init_data)
    if not telegram_user:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid user data"}}
        )
    
    tgid = int(telegram_user['id'])
    admin_tgid = int(settings.admin_tgid) if settings.admin_tgid else None
    
    # Сохраняем/обновляем пользователя в БД
    try:
        queries.upsert_user({
            'tgid': tgid,
            'username': telegram_user.get('username'),
            'first_name': telegram_user.get('first_name'),
            'last_name': telegram_user.get('last_name')
        })
    except Exception as e:
        print(f'Error upserting user: {e}')
    
    return {
        'tgid': tgid,
        'username': telegram_user.get('username'),
        'first_name': telegram_user.get('first_name'),
        'last_name': telegram_user.get('last_name'),
        'isAdmin': admin_tgid is not None and tgid == admin_tgid
    }


async def require_admin(current_user: dict = None) -> dict:
    """Dependency для проверки прав администратора"""
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}
        )
    
    if not current_user.get('isAdmin'):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FORBIDDEN", "message": "Admin access required"}}
        )
    
    return current_user

