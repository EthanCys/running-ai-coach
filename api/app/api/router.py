from fastapi import APIRouter

from app.api.routes.activities import router as activities_router


api_router = APIRouter()
api_router.include_router(activities_router, prefix="/v1/activities", tags=["activities"])