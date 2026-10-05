from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_student, require_teacher
from app.models import (
    AttendanceDetail,
    AttendanceScoreRule,
    AttendanceSession,
    AttendanceStatus,
    Class,
    Enrollment,
    LateTier,
    ScoreMode,
    Student,
    StudentScore,
    User,
)
from app.schemas import (
    AttendanceScoreRuleCreate,
    AttendanceScoreRuleOut,
    StudentScoreOut,
    StudentScoreOverride,
)

router = APIRouter(prefix="/scores", tags=["scores"])


# ---------------------------------------------------------------------------
# Score rules (ตั้งค่าเกณฑ์การให้คะแนนต่อคลาส)
# ---------------------------------------------------------------------------
@router.put("/rules/{class_id}", response_model=AttendanceScoreRuleOut)
def upsert_score_rule(
    class_id: int,
    payload: AttendanceScoreRuleCreate,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    if payload.class_id != class_id:
        raise HTTPException(status_code=400, detail="class_id ไม่ตรงกับ path")

    class_ = db.query(Class).filter(Class.id == class_id).first()
    if class_ is None:
        raise HTTPException(status_code=404, detail="ไม่พบคลาสเรียนนี้")

    rule = db.query(AttendanceScoreRule).filter(AttendanceScoreRule.class_id == class_id).first()
    if rule is None:
        rule = AttendanceScoreRule(class_id=class_id)
        db.add(rule)

    rule.mode = payload.mode
    rule.full_score = payload.full_score
    rule.session_count = payload.session_count
    rule.session_full_score = payload.session_full_score
    rule.pass_threshold = payload.pass_threshold

    db.flush()

    # แทนที่ late_tiers ทั้งหมดด้วยชุดใหม่
    db.query(LateTier).filter(LateTier.rule_id == rule.id).delete()
    for tier in payload.late_tiers:
        db.add(LateTier(rule_id=rule.id, min_minutes=tier.min_minutes, deduction=tier.deduction))

    db.commit()
    db.refresh(rule)
    return rule


@router.get("/rules/{class_id}", response_model=AttendanceScoreRuleOut | None)
def get_score_rule(class_id: int, db: Session = Depends(get_db)):
    return db.query(AttendanceScoreRule).filter(AttendanceScoreRule.class_id == class_id).first()


# ---------------------------------------------------------------------------
# คำนวณ + ดูคะแนน
# ---------------------------------------------------------------------------
def _compute_score_for_student(db: Session, class_id: int, student_id: int) -> Decimal:
    rule = db.query(AttendanceScoreRule).filter(AttendanceScoreRule.class_id == class_id).first()
    if rule is None:
        return Decimal("0.00")

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.class_id == class_id, Enrollment.student_id == student_id)
        .first()
    )
    if enrollment is None:
        return Decimal("0.00")

    details = (
        db.query(AttendanceDetail)
        .join(AttendanceSession, AttendanceDetail.session_id == AttendanceSession.id)
        .filter(
            AttendanceSession.class_id == class_id,
            AttendanceDetail.enrollment_id == enrollment.id,
        )
        .all()
    )

    late_tiers = sorted(rule.late_tiers, key=lambda t: t.min_minutes)

    def deduction_for_late(check_in_time, start_time) -> Decimal:
        if not late_tiers or check_in_time is None or start_time is None:
            return Decimal("0.00")
        import datetime as _dt

        minutes_late = (
            _dt.datetime.combine(_dt.date.today(), check_in_time)
            - _dt.datetime.combine(_dt.date.today(), start_time)
        ).total_seconds() / 60
        applicable = [t for t in late_tiers if minutes_late >= t.min_minutes]
        if not applicable:
            return Decimal("0.00")
        return max(t.deduction for t in applicable)

    if rule.mode == ScoreMode.direct:
        score = Decimal(rule.full_score)
        for d in details:
            if d.status == AttendanceStatus.absent:
                score -= Decimal(rule.full_score) / max(1, len(details))
            elif d.status == AttendanceStatus.late:
                score -= deduction_for_late(d.check_in_time, d.session.start_time)
        return max(Decimal("0.00"), score)

    # per_session mode
    total = Decimal("0.00")
    sessions_seen = {d.session_id for d in details}
    for d in details:
        if d.status == AttendanceStatus.present:
            total += Decimal(rule.session_full_score)
        elif d.status == AttendanceStatus.late:
            total += max(
                Decimal("0.00"),
                Decimal(rule.session_full_score) - deduction_for_late(d.check_in_time, d.session.start_time),
            )
        # absent -> +0
    # เซสชันที่ยังไม่มี record เลย ถือว่าขาด (+0) อยู่แล้วเพราะไม่ถูกนับบวกเพิ่ม
    return total


@router.post("/recalculate/{class_id}", response_model=list[StudentScoreOut])
def recalculate_scores(
    class_id: int,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    enrollments = db.query(Enrollment).filter(Enrollment.class_id == class_id).all()
    results = []
    for e in enrollments:
        computed = _compute_score_for_student(db, class_id, e.student_id)

        score_row = (
            db.query(StudentScore)
            .filter(StudentScore.class_id == class_id, StudentScore.student_id == e.student_id)
            .first()
        )
        if score_row is None:
            score_row = StudentScore(class_id=class_id, student_id=e.student_id, score=computed)
            db.add(score_row)
        elif not score_row.is_manual_override:
            score_row.score = computed

        db.flush()
        results.append(score_row)

    db.commit()

    output = []
    for row in results:
        student = db.query(Student).filter(Student.id == row.student_id).first()
        output.append(
            StudentScoreOut(
                id=row.id,
                student_id=row.student_id,
                class_id=row.class_id,
                score=row.score,
                note=row.note,
                is_manual_override=row.is_manual_override,
                updated_at=row.updated_at,
                student_name=student.full_name if student else None,
                student_code=student.student_code if student else None,
            )
        )
    return output


@router.get("/class/{class_id}", response_model=list[StudentScoreOut])
def list_class_scores(
    class_id: int,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    rows = db.query(StudentScore).filter(StudentScore.class_id == class_id).all()
    output = []
    for row in rows:
        student = db.query(Student).filter(Student.id == row.student_id).first()
        output.append(
            StudentScoreOut(
                id=row.id,
                student_id=row.student_id,
                class_id=row.class_id,
                score=row.score,
                note=row.note,
                is_manual_override=row.is_manual_override,
                updated_at=row.updated_at,
                student_name=student.full_name if student else None,
                student_code=student.student_code if student else None,
            )
        )
    return output


@router.put("/class/{class_id}/student/{student_id}", response_model=StudentScoreOut)
def override_student_score(
    class_id: int,
    student_id: int,
    payload: StudentScoreOverride,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    row = (
        db.query(StudentScore)
        .filter(StudentScore.class_id == class_id, StudentScore.student_id == student_id)
        .first()
    )
    if row is None:
        row = StudentScore(class_id=class_id, student_id=student_id)
        db.add(row)

    row.score = payload.score
    row.note = payload.note
    row.is_manual_override = True
    db.commit()
    db.refresh(row)

    student = db.query(Student).filter(Student.id == student_id).first()
    return StudentScoreOut(
        id=row.id,
        student_id=row.student_id,
        class_id=row.class_id,
        score=row.score,
        note=row.note,
        is_manual_override=row.is_manual_override,
        updated_at=row.updated_at,
        student_name=student.full_name if student else None,
        student_code=student.student_code if student else None,
    )


@router.get("/me/{class_id}", response_model=StudentScoreOut | None)
def get_my_score(
    class_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = current_user.student_profile
    if student is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรไฟล์นักศึกษาของบัญชีนี้")

    row = (
        db.query(StudentScore)
        .filter(StudentScore.class_id == class_id, StudentScore.student_id == student.id)
        .first()
    )
    if row is None:
        return None

    return StudentScoreOut(
        id=row.id,
        student_id=row.student_id,
        class_id=row.class_id,
        score=row.score,
        note=row.note,
        is_manual_override=row.is_manual_override,
        updated_at=row.updated_at,
        student_name=student.full_name,
        student_code=student.student_code,
    )
