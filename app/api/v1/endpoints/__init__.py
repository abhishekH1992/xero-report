from fastapi import APIRouter

from . import xero_auth, xero_reports, xero_callback, xero_category

router = APIRouter()
router.include_router(xero_auth.router)
router.include_router(xero_reports.router)
router.include_router(xero_callback.router)
router.include_router(xero_category.router)

__all__ = ["router"] 