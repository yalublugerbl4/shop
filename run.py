#!/usr/bin/env python3
"""Entry point for the application"""
import uvicorn
import threading
from app.main import start_bot
from app.config import settings

if __name__ == "__main__":
    # Запуск бота в фоне
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False
    )

