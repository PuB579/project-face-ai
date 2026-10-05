import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_student, require_teacher
from app.face_service import (
    FaceServiceUnavailable,
    MultipleFacesDetected,
    NoFaceDetected,
    embedding_from_json,
    encode_face,
    find_best_match,
    is_confident_enough,
)
from app.models import (
    AttendanceDetail,
    AttendanceMethod,
    AttendanceSession,
    AttendanceStatus,
    Class,
    Enrollment,
    ApprovalStatus,
    User,
)
from app.schemas import (
    AttendanceDetailOut,
    AttendanceSessionCreate,
    AttendanceSessionOut,
    AttendanceSummary,
    CheckinRequest,
    CheckinResponse,
    ManualCheckinRequest,
    MySessionOut,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
@router.post("/sessions", response_model=AttendanceSessionOut, status_code=status.HTTP_201_CREATED)
def open_session(
    payload: AttendanceSessionCreate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    class_ = db.query(Class).filter(Class.id == payload.class_id).first()
    if class_ is None:
        raise HTTPException(status_code=404, detail="ไม่พบคลาสเรียนนี้")

    now = dt.datetime.now()
    session = AttendanceSession(
        class_id=payload.class_id,
        session_date=payload.session_date or now.date(),
        start_time=payload.start_time or now.time().replace(microsecond=0),
        end_time=payload.end_time,
        created_by=current_user.teacher_profile.id if current_user.teacher_profile else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions/{class_id}/today", response_model=AttendanceSessionOut | None)
def get_today_session(class_id: int, db: Session = Depends(get_db)):
    today = dt.date.today()
    session = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.class_id == class_id, AttendanceSession.session_date == today)
        .order_by(AttendanceSession.id.desc())
        .first()
    )
    return session


def _checkin_window(
    session: AttendanceSession, class_: Class
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """ช่วงเวลาที่เปิดให้เช็คชื่อ: [start - open_offset, start + close_offset] ไม่เกิน end_time"""
    if session.start_time is None:
        return None, None
    start_dt = dt.datetime.combine(session.session_date, session.start_time)
    open_dt = start_dt - dt.timedelta(minutes=class_.checkin_open_offset_minutes)
    close_dt = start_dt + dt.timedelta(minutes=class_.checkin_close_offset_minutes)
    if session.end_time is not None:
        close_dt = min(close_dt, dt.datetime.combine(session.session_date, session.end_time))
    return open_dt, close_dt


@router.get("/my-sessions", response_model=list[MySessionOut])
def my_sessions_today(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    """คาบเรียนวันนี้ของทุกคลาสที่นักศึกษาลงทะเบียนไว้"""
    student = current_user.student_profile
    if student is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรไฟล์นักศึกษาของบัญชีนี้")

    now = dt.datetime.now().replace(microsecond=0)
    enrollment_by_class = {e.class_id: e for e in student.enrollments}
    if not enrollment_by_class:
        return []

    sessions = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.class_id.in_(enrollment_by_class.keys()),
            AttendanceSession.session_date == now.date(),
        )
        .order_by(AttendanceSession.start_time)
        .all()
    )

    result = []
    for session in sessions:
        class_ = session.class_
        course = class_.course
        enrollment = enrollment_by_class[session.class_id]
        detail = next(
            (d for d in session.attendance_details if d.enrollment_id == enrollment.id), None
        )
        open_dt, close_dt = _checkin_window(session, class_)
        is_open = (open_dt is None or open_dt <= now) and (close_dt is None or now <= close_dt)
        result.append(
            MySessionOut(
                session_id=session.id,
                class_id=class_.id,
                class_code=class_.class_code,
                course_code=course.course_code,
                course_name=course.course_name,
                teacher_name=course.teacher.full_name if course.teacher else None,
                session_date=session.session_date,
                start_time=session.start_time,
                end_time=session.end_time,
                open_at=open_dt,
                close_at=close_dt,
                is_open=is_open,
                my_status=detail.status if detail else None,
                my_check_in_time=detail.check_in_time if detail else None,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Check-in (face)
# ---------------------------------------------------------------------------
def _determine_status(
    session: AttendanceSession, check_in_time: dt.time, late_threshold_minutes: int
) -> AttendanceStatus:
    if session.start_time is None:
        return AttendanceStatus.present

    start_dt = dt.datetime.combine(session.session_date, session.start_time)
    checkin_dt = dt.datetime.combine(session.session_date, check_in_time)
    late_cutoff = start_dt + dt.timedelta(minutes=late_threshold_minutes)

    if checkin_dt <= late_cutoff:
        return AttendanceStatus.present
    return AttendanceStatus.late


@router.post("/checkin", response_model=CheckinResponse)
async def checkin_with_face(
    session_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = current_user.student_profile
    if student is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรไฟล์นักศึกษาของบัญชีนี้")

    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="ไม่พบคาบเรียนนี้")

    class_ = db.query(Class).filter(Class.id == session.class_id).first()
    if class_ is None:
        raise HTTPException(status_code=404, detail="ไม่พบคลาสเรียนของคาบนี้")

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.class_id == class_.id, Enrollment.student_id == student.id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="คุณไม่ได้ลงทะเบียนเรียนวิชานี้")

    # เช็คชื่อได้เฉพาะคาบของวันนี้ และอยู่ในช่วงเวลาเรียนเท่านั้น
    now = dt.datetime.now().replace(microsecond=0)
    if session.session_date != now.date():
        raise HTTPException(status_code=400, detail="คาบเรียนนี้ไม่ใช่ของวันนี้ ไม่สามารถเช็คชื่อได้")
    open_dt, close_dt = _checkin_window(session, class_)
    if open_dt is not None and now < open_dt:
        raise HTTPException(
            status_code=400,
            detail=f"ยังไม่ถึงเวลาเปิดเช็คชื่อ (เปิดเวลา {open_dt.strftime('%H:%M')})",
        )
    if close_dt is not None and now > close_dt:
        raise HTTPException(
            status_code=400,
            detail=f"หมดเวลาเช็คชื่อแล้ว (ปิดเวลา {close_dt.strftime('%H:%M')})",
        )

    existing_detail = (
        db.query(AttendanceDetail)
        .filter(
            AttendanceDetail.session_id == session_id,
            AttendanceDetail.enrollment_id == enrollment.id,
        )
        .first()
    )
    if existing_detail is not None:
        raise HTTPException(status_code=400, detail="คุณเช็คชื่อคาบนี้ไปแล้ว")

    image_bytes = await file.read()
    try:
        probe_encoding = encode_face(image_bytes)
    except FaceServiceUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except (NoFaceDetected, MultipleFacesDetected) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # เทียบกับใบหน้าของ "ตัวเอง" เท่านั้น ที่สถานะอนุมัติแล้ว (approved) และ active
    candidates: list[tuple[int, list[float]]] = []
    for fp in student.face_profiles:
        if not fp.is_active or not fp.embedding:
            continue
        if not fp.approvals or fp.approvals[-1].status != ApprovalStatus.approved:
            continue
        candidates.append((student.id, embedding_from_json(fp.embedding)))

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="ยังไม่มีใบหน้าที่ได้รับการอนุมัติ กรุณาลงทะเบียนใบหน้าและรอการอนุมัติก่อน",
        )

    matched_student_id, confidence = find_best_match(probe_encoding, candidates)
    threshold = class_.face_confidence_threshold

    if matched_student_id != student.id or not is_confident_enough(confidence, threshold):
        raise HTTPException(
            status_code=400,
            detail=f"ใบหน้าไม่ตรงกับที่ลงทะเบียนไว้ (ความมั่นใจ {confidence:.2f}% ต่ำกว่าเกณฑ์ {threshold}%)",
        )

    now_time = now.time()
    att_status = _determine_status(session, now_time, class_.late_threshold_minutes)

    detail = AttendanceDetail(
        session_id=session_id,
        enrollment_id=enrollment.id,
        status=att_status,
        method=AttendanceMethod.face,
        check_in_time=now_time,
        confidence=confidence,
    )
    db.add(detail)
    db.commit()

    return CheckinResponse(
        status=att_status,
        method=AttendanceMethod.face,
        confidence=confidence,
        student_name=student.full_name,
        message="เช็คชื่อด้วยใบหน้าสำเร็จ",
    )


@router.post("/manual", response_model=AttendanceDetailOut)
def manual_checkin(
    payload: ManualCheckinRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == payload.session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="ไม่พบคาบเรียนนี้")

    class_ = db.query(Class).filter(Class.id == session.class_id).first()
    if class_ is not None and not class_.allow_manual_fallback:
        raise HTTPException(
            status_code=400, detail="คลาสนี้ไม่อนุญาตให้เช็คชื่อแบบ manual"
        )

    enrollment = db.query(Enrollment).filter(Enrollment.id == payload.enrollment_id).first()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="ไม่พบการลงทะเบียนนี้")

    existing_detail = (
        db.query(AttendanceDetail)
        .filter(
            AttendanceDetail.session_id == payload.session_id,
            AttendanceDetail.enrollment_id == payload.enrollment_id,
        )
        .first()
    )
    if existing_detail is not None:
        existing_detail.status = payload.status
        existing_detail.method = AttendanceMethod.manual
        existing_detail.check_in_time = dt.datetime.now().time().replace(microsecond=0)
        existing_detail.confidence = None
        db.commit()
        db.refresh(existing_detail)
        return _to_detail_out(existing_detail)

    detail = AttendanceDetail(
        session_id=payload.session_id,
        enrollment_id=payload.enrollment_id,
        status=payload.status,
        method=AttendanceMethod.manual,
        check_in_time=dt.datetime.now().time().replace(microsecond=0),
        confidence=None,
    )
    db.add(detail)
    db.commit()
    db.refresh(detail)
    return _to_detail_out(detail)


def _to_detail_out(detail: AttendanceDetail) -> AttendanceDetailOut:
    student = detail.enrollment.student if detail.enrollment else None
    return AttendanceDetailOut(
        id=detail.id,
        session_id=detail.session_id,
        enrollment_id=detail.enrollment_id,
        status=detail.status,
        method=detail.method,
        check_in_time=detail.check_in_time,
        confidence=detail.confidence,
        created_at=detail.created_at,
        student_id=student.id if student else None,
        student_name=student.full_name if student else None,
        student_code=student.student_code if student else None,
    )


@router.get("/history", response_model=list[AttendanceDetailOut])
def my_attendance_history(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = current_user.student_profile
    if student is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรไฟล์นักศึกษาของบัญชีนี้")

    enrollment_ids = [e.id for e in student.enrollments]
    if not enrollment_ids:
        return []

    details = (
        db.query(AttendanceDetail)
        .filter(AttendanceDetail.enrollment_id.in_(enrollment_ids))
        .order_by(AttendanceDetail.created_at.desc())
        .all()
    )
    return [_to_detail_out(d) for d in details]


@router.get("/class/{class_id}", response_model=list[AttendanceDetailOut])
def class_attendance(
    class_id: int,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    query = (
        db.query(AttendanceDetail)
        .join(AttendanceSession, AttendanceDetail.session_id == AttendanceSession.id)
        .filter(AttendanceSession.class_id == class_id)
    )
    if session_id is not None:
        query = query.filter(AttendanceDetail.session_id == session_id)

    details = query.order_by(AttendanceDetail.created_at.desc()).all()
    return [_to_detail_out(d) for d in details]


@router.get("/summary/{class_id}", response_model=AttendanceSummary)
def class_summary(
    class_id: int,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    total_sessions = (
        db.query(AttendanceSession).filter(AttendanceSession.class_id == class_id).count()
    )
    total_students = db.query(Enrollment).filter(Enrollment.class_id == class_id).count()

    details = (
        db.query(AttendanceDetail)
        .join(AttendanceSession, AttendanceDetail.session_id == AttendanceSession.id)
        .filter(AttendanceSession.class_id == class_id)
        .all()
    )

    present_count = sum(1 for d in details if d.status == AttendanceStatus.present)
    late_count = sum(1 for d in details if d.status == AttendanceStatus.late)
    absent_count = sum(1 for d in details if d.status == AttendanceStatus.absent)

    return AttendanceSummary(
        class_id=class_id,
        total_sessions=total_sessions,
        total_students=total_students,
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
    )
