from fastapi import APIRouter, Depends
from app.middleware.telegram_auth import get_current_user

router = APIRouter()


@router.get("")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    return current_user
