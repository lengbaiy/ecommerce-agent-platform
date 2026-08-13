from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.products import router as products_router
from app.api.v1.tasks import router as tasks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(products_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(knowledge_router)
