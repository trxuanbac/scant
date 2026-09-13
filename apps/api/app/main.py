from contextlib import asynccontextmanager
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.v1 import api_router
from app.services.observability.metrics_collector import metrics_collector


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure storage folders exist and DB tables initialized
    settings.assert_production_safety()
    settings.init_storage()
    await init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.middleware("http")
async def collect_http_metrics(request, call_next):
    from app.core.usage_context import usage_user_id
    identity_token = usage_user_id.set(None)
    start = time.time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = int((time.time() - start) * 1000)
        metrics_collector.record_http_request(duration_ms, status_code=status_code)
        usage_user_id.reset(identity_token)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8050, reload=True)
