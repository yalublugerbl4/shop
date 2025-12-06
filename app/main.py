from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.routes import products, me, admin
import threading
from app.bot import run_bot

app = FastAPI(title="Telegram Shop API")

# CORS configuration
cors_origins = []
if settings.cors_origins:
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(',')]
elif settings.frontend_url:
    cors_origins = [settings.frontend_url]

cors_origins.append('https://web.telegram.org')

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


# API routes
app.include_router(me.router, prefix="/me", tags=["me"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик ошибок"""
    print(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "SERVER_ERROR", "message": "Internal server error"}}
    )


# Запуск бота в отдельном потоке (будет вызван при старте приложения)


if __name__ == "__main__":
    import uvicorn
    
    # Запуск бота в фоне
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.node_env == "development"
    )
else:
    # Для production (gunicorn/uvicorn)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

