"""사용자 알림함."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member, Notification, DailySummary
from app.schemas import NotificationOut
from app.auth import get_current_member

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db),
                       me: Member = Depends(get_current_member)):
    q = (
        db.query(Notification, DailySummary)
        .join(DailySummary, DailySummary.code == Notification.summary_code)
        .filter(DailySummary.member_code == me.code)
    )
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    rows = q.order_by(Notification.sent_at.desc()).all()
    return [NotificationOut(code=n.code, type=n.type, content=n.content, sent_at=n.sent_at,
                            is_read=n.is_read, date=s.date) for n, s in rows]


@router.post("/{code}/read")
def mark_read(code: int, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    row = (
        db.query(Notification)
        .join(DailySummary, DailySummary.code == Notification.summary_code)
        .filter(Notification.code == code, DailySummary.member_code == me.code)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    row.is_read = True
    db.commit()
    return {"ok": True}
