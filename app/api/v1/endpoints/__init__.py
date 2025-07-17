from fastapi import APIRouter, Depends
from app.util.auth import api_key_auth

from . import xero_auth, xero_reports

router = APIRouter(dependencies=[Depends(api_key_auth)])
router.include_router(xero_auth.router)
router.include_router(xero_reports.router)

__all__ = ["router"] 