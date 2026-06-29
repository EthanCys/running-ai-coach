from fastapi import APIRouter

from app.api.routes.activities import router as activities_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router


api_router = APIRouter()
api_router.include_router(activities_router, prefix="/v1/activities", tags=["activities"])
api_router.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(chat_router, prefix="/v1/chat", tags=["chat"])
