"""FastAPI application entrypoint, CORS configuration, and lifespan initialization."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from newcode.api.routes.stream import router as stream_router
from newcode.api.routes.feedback import router as feedback_router
from newcode.api.routes.workbench import router as workbench_router
from newcode.core.config import settings
from newcode.core.database import init_db

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing database tables on application startup...")
    await init_db()
    logger.info("Database initialization completed.")
    yield
    logger.info("Application shutdown.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(stream_router)
    application.include_router(feedback_router)
    application.include_router(workbench_router)

    static_dir = Path(__file__).resolve().parent / "ui" / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @application.get("/chat", include_in_schema=False)
        async def chat_page():
            return RedirectResponse(url="/static/chat.html")

        @application.get("/workbench", include_in_schema=False)
        async def workbench_page():
            return RedirectResponse(url="/static/workbench.html")

    @application.get("/health", tags=["system"])
    @application.get("/api/health", tags=["system"])
    async def health_check():
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
        }

    return application


app: FastAPI = create_app()

