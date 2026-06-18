from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db import get_db
from session_service import SessionService

router = APIRouter(prefix="/api/session", tags=["Session Management"])

class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: Optional[str] = "DefaultDevice"

@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """Refreshes an access token using a valid refresh token (Auto-login for 7 days)"""
    result = SessionService.refresh_access_token(db, req.refresh_token, req.device_id)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result

class LogoutRequest(BaseModel):
    access_token: str

@router.post("/logout")
def logout(req: LogoutRequest, db: Session = Depends(get_db)):
    """Logs the user out of the current device"""
    success = SessionService.logout(db, req.access_token)
    if not success:
        return {"status": "Already logged out or invalid token"}
    return {"status": "Logged out successfully"}

@router.post("/logout-all")
def logout_all_devices(user_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    """Logs the user out of all devices for security"""
    count = SessionService.logout_all_devices(db, user_id)
    return {"status": f"Logged out from {count} devices"}

@router.get("/active/{user_id}")
def get_active_sessions(user_id: int, db: Session = Depends(get_db)):
    """Returns a list of all active sessions for the user"""
    return {"sessions": SessionService.get_active_sessions(db, user_id)}

class OfflineData(BaseModel):
    user_id: int
    data_type: str
    payload: dict

@router.post("/offline/queue")
def sync_offline_data(req: OfflineData, db: Session = Depends(get_db)):
    """Queues offline generated data into the DB for processing"""
    return SessionService.queue_offline_data(db, req.user_id, req.data_type, req.payload)

@router.post("/offline/sync")
def sync_all_offline_data(user_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    """Synchronizes all the offline data that was queued up for the user"""
    return SessionService.sync_offline_queue(db, user_id)
