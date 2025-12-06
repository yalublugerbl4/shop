from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.routes import products, me, admin

app = FastAPI(title="Telegram Shop API")

# CORS configuration
cors_origins = []
if settings.cors_origins:
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(',')]
elif settings.frontend_url:
    cors_origins = [settings.frontend_url]

# Всегда добавляем Telegram WebApp origin
cors_origins.append('https://web.telegram.org')

# Если origins пуст, разрешаем все (для разработки)
final_origins = cors_origins if cors_origins else ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=final_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.node_env == "development"
    )
