"""
Attendance Management Router
Check-in/Check-out, Attendance tracking, Leave management, Attendance analytics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional
from db import sessionLocal, get_db
from models import Attendance, LeaveRequest, User, Worker

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

# ==================== PYDANTIC MODELS FOR WORKERS ====================

class WorkerCreate(BaseModel):
    name: str
    phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    address: Optional[str] = ""
    salary: float = 0
    assigned_work: Optional[str] = ""
    position: Optional[str] = "Staff"
    pin: Optional[str] = ""

class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    address: Optional[str] = None
    salary: Optional[float] = None
    assigned_work: Optional[str] = None
    position: Optional[str] = None
    pin: Optional[str] = None

# ==================== WORKER MANAGEMENT ====================

@router.post("/workers")
def create_worker(
    worker_data: WorkerCreate,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Create a new worker for a shopkeeper"""
    worker = Worker(
        shopkeeper_id=user_id,
        **worker_data.dict()
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker

@router.get("/workers")
def get_workers(
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get all workers for a shopkeeper"""
    return db.query(Worker).filter(Worker.shopkeeper_id == user_id).all()

@router.put("/workers/{worker_id}")
def update_worker(
    worker_id: int,
    data: WorkerUpdate,
    db: Session = Depends(get_db)
):
    """Update worker details"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(worker, key, value)
    
    db.commit()
    db.refresh(worker)
    return worker

@router.delete("/workers/{worker_id}")
def delete_worker(
    worker_id: int,
    db: Session = Depends(get_db)
):
    """Delete a worker from the database"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    db.delete(worker)
    db.commit()
    return {"message": "Worker deleted successfully", "worker_id": worker_id}


# ==================== PYDANTIC MODELS ====================

class CheckInOut(BaseModel):
    employee_id: int
    check_in: bool = True  # True for check-in, False for check-out

class AttendanceRecord(BaseModel):
    employee_id: int
    attendance_date: str
    status: str  # PRESENT, ABSENT, LEAVE, HALF_DAY
    notes: Optional[str] = None

class LeaveRequestCreate(BaseModel):
    employee_id: int
    leave_type: str  # VACATION, SICK, PERSONAL
    from_date: str
    to_date: str
    reason: Optional[str] = None

class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    attendance_date: date
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    status: str
    working_hours: float

    class Config:
        from_attributes = True

# ==================== CHECK-IN/CHECK-OUT ====================

@router.post("/check-in")
def employee_check_in(
    employee_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Employee check-in"""
    employee = db.query(User).filter(User.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    today = date.today()
    attendance = db.query(Attendance).filter(
        and_(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == today
        )
    ).first()
    
    if not attendance:
        attendance = Attendance(
            employee_id=employee_id,
            attendance_date=today,
            check_in_time=datetime.now(),
            status="PRESENT"
        )
        db.add(attendance)
    elif attendance.check_in_time is None:
        attendance.check_in_time = datetime.now()
        if attendance.status == "ABSENT":
            attendance.status = "PRESENT"
    else:
        raise HTTPException(status_code=400, detail="Already checked in today")
    
    db.commit()
    db.refresh(attendance)
    
    return {
        "message": "Check-in successful",
        "employee_id": employee_id,
        "check_in_time": attendance.check_in_time,
        "status": attendance.status
    }

@router.post("/check-out")
def employee_check_out(
    employee_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Employee check-out"""
    employee = db.query(User).filter(User.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    today = date.today()
    attendance = db.query(Attendance).filter(
        and_(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == today
        )
    ).first()
    
    if not attendance or not attendance.check_in_time:
        raise HTTPException(status_code=400, detail="No check-in found for today")
    
    if attendance.check_out_time:
        raise HTTPException(status_code=400, detail="Already checked out today")
    
    attendance.check_out_time = datetime.now()
    
    # Calculate working hours
    if attendance.check_in_time and attendance.check_out_time:
        duration = attendance.check_out_time - attendance.check_in_time
        attendance.working_hours = duration.total_seconds() / 3600  # Convert to hours
    
    db.commit()
    db.refresh(attendance)
    
    return {
        "message": "Check-out successful",
        "employee_id": employee_id,
        "check_out_time": attendance.check_out_time,
        "working_hours": attendance.working_hours
    }

# ==================== ATTENDANCE RECORDS ====================

@router.post("/record-manual")
def record_manual_attendance(
    record: AttendanceRecord,
    db: Session = Depends(get_db)
):
    """Manually record attendance"""
    employee = db.query(User).filter(User.id == record.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    att_date = datetime.strptime(record.attendance_date, "%Y-%m-%d").date()
    
    existing = db.query(Attendance).filter(
        and_(
            Attendance.employee_id == record.employee_id,
            Attendance.attendance_date == att_date
        )
    ).first()
    
    if existing:
        existing.status = record.status
        existing.notes = record.notes
        db.add(existing)
    else:
        attendance = Attendance(
            employee_id=record.employee_id,
            attendance_date=att_date,
            status=record.status,
            notes=record.notes
        )
        db.add(attendance)
    
    db.commit()
    
    return {"message": "Attendance recorded successfully"}

@router.get("/employee/{employee_id}")
def get_employee_attendance(
    employee_id: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get attendance records for an employee"""
    query = db.query(Attendance).filter(Attendance.employee_id == employee_id)
    
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        query = query.filter(Attendance.attendance_date >= from_dt)
    
    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        query = query.filter(Attendance.attendance_date <= to_dt)
    
    records = query.order_by(desc(Attendance.attendance_date)).all()
    
    return {
        "employee_id": employee_id,
        "records": records,
        "total_records": len(records)
    }

@router.get("/date/{date_str}")
def get_attendance_by_date(
    date_str: str,
    db: Session = Depends(get_db)
):
    """Get all attendance records for a specific date"""
    att_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    records = db.query(Attendance).filter(Attendance.attendance_date == att_date).all()
    
    present = sum(1 for r in records if r.status == "PRESENT")
    absent = sum(1 for r in records if r.status == "ABSENT")
    leave = sum(1 for r in records if r.status == "LEAVE")
    
    return {
        "date": att_date,
        "total_records": len(records),
        "present": present,
        "absent": absent,
        "leave": leave,
        "records": records
    }

# ==================== LEAVE MANAGEMENT ====================

@router.post("/leave-request")
def request_leave(
    leave_request: LeaveRequestCreate,
    db: Session = Depends(get_db)
):
    """Request leave"""
    employee = db.query(User).filter(User.id == leave_request.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    from_dt = datetime.strptime(leave_request.from_date, "%Y-%m-%d").date()
    to_dt = datetime.strptime(leave_request.to_date, "%Y-%m-%d").date()
    
    if to_dt < from_dt:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")
    
    db_leave = LeaveRequest(
        employee_id=leave_request.employee_id,
        leave_type=leave_request.leave_type,
        from_date=from_dt,
        to_date=to_dt,
        reason=leave_request.reason,
        status="PENDING"
    )
    
    db.add(db_leave)
    db.commit()
    db.refresh(db_leave)
    
    return db_leave

@router.get("/leave-requests")
def get_leave_requests(
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get leave requests"""
    query = db.query(LeaveRequest)
    
    if employee_id:
        query = query.filter(LeaveRequest.employee_id == employee_id)
    
    if status:
        query = query.filter(LeaveRequest.status == status)
    
    requests = query.order_by(desc(LeaveRequest.created_at)).all()
    
    return {
        "leave_requests": requests,
        "total": len(requests)
    }

@router.put("/leave-request/{leave_id}/approve")
def approve_leave(
    leave_id: int,
    db: Session = Depends(get_db)
):
    """Approve leave request"""
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    
    leave.status = "APPROVED"
    
    # Create attendance records for leave period
    current = leave.from_date
    while current <= leave.to_date:
        existing = db.query(Attendance).filter(
            and_(
                Attendance.employee_id == leave.employee_id,
                Attendance.attendance_date == current
            )
        ).first()
        
        if not existing:
            attendance = Attendance(
                employee_id=leave.employee_id,
                attendance_date=current,
                status="LEAVE"
            )
            db.add(attendance)
        
        current += timedelta(days=1)
    
    db.commit()
    
    return {"message": "Leave approved"}

@router.put("/leave-request/{leave_id}/reject")
def reject_leave(
    leave_id: int,
    db: Session = Depends(get_db)
):
    """Reject leave request"""
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    
    leave.status = "REJECTED"
    db.commit()
    
    return {"message": "Leave rejected"}

# ==================== ANALYTICS ====================

@router.get("/analytics/summary")
def get_attendance_summary(
    days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get attendance summary for past N days"""
    cutoff_date = date.today() - timedelta(days=days)
    
    records = db.query(Attendance).filter(
        Attendance.attendance_date >= cutoff_date
    ).all()
    
    employees = db.query(User).all()
    
    present = sum(1 for r in records if r.status == "PRESENT")
    absent = sum(1 for r in records if r.status == "ABSENT")
    leave = sum(1 for r in records if r.status == "LEAVE")
    
    return {
        "period_days": days,
        "total_records": len(records),
        "present": present,
        "absent": absent,
        "leave": leave,
        "total_employees": len(employees),
        "attendance_percentage": (present / len(records) * 100) if records else 0
    }

@router.get("/analytics/employee/{employee_id}")
def get_employee_analytics(
    employee_id: int,
    days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get analytics for specific employee"""
    cutoff_date = date.today() - timedelta(days=days)
    
    records = db.query(Attendance).filter(
        and_(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date >= cutoff_date
        )
    ).all()
    
    present = sum(1 for r in records if r.status == "PRESENT")
    absent = sum(1 for r in records if r.status == "ABSENT")
    leave = sum(1 for r in records if r.status == "LEAVE")
    total_hours = sum(r.working_hours for r in records if r.working_hours)
    
    return {
        "employee_id": employee_id,
        "period_days": days,
        "present": present,
        "absent": absent,
        "leave": leave,
        "total_working_hours": total_hours,
        "attendance_percentage": (present / len(records) * 100) if records else 0
    }
