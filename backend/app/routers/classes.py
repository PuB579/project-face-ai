import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ensure_course_owner, get_current_user, require_teacher
from app.models import Class, ClassSchedule, Course, Enrollment, Student, User, UserRole
from app.routers.students import to_student_out
from app.schemas import ClassCreate, ClassOut, ClassUpdate, EnrollmentCreate, EnrollmentOut

router = APIRouter(prefix="/classes", tags=["classes"])


def get_owned_course(db: Session, course_id: int, current_user: User) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายวิชานี้")
    ensure_course_owner(current_user, course)
    return course


def get_owned_class(db: Session, class_id: int, current_user: User) -> Class:
    class_ = db.query(Class).filter(Class.id == class_id).first()
    if class_ is None:
        raise HTTPException(status_code=404, detail="ไม่พบคลาสเรียนนี้")
    ensure_course_owner(current_user, class_.course)
    return class_


def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def validate_schedules(class_: Class) -> None:
    """
    แต่ละช่วงเรียน: เวลาเลิกต้องหลังเวลาเริ่ม, ช่วงเช็คชื่อตรงเวลาต้องไม่เกินเวลาเรียน
    และช่วงเรียนในวันเดียวกันต้องไม่ทับกัน
    """
    slots = sorted(class_.schedules, key=lambda s: (s.weekday, s.start_time))
    for i, slot in enumerate(slots):
        if slot.end_time <= slot.start_time:
            raise HTTPException(status_code=400, detail="เวลาเลิกเรียนต้องหลังเวลาเริ่มเรียน")
        if not 0 <= class_.late_threshold_minutes <= _minutes(slot.end_time) - _minutes(slot.start_time):
            raise HTTPException(
                status_code=400, detail="เวลาเช็คชื่อตรงเวลาต้องไม่เกินระยะเวลาเรียนของทุกช่วง"
            )
        prev = slots[i - 1] if i else None
        if prev and prev.weekday == slot.weekday and slot.start_time < prev.end_time:
            raise HTTPException(status_code=400, detail="ช่วงเวลาเรียนในวันเดียวกันทับกัน")


def build_schedules(items) -> list[ClassSchedule]:
    return [ClassSchedule(**item.model_dump()) for item in items]


@router.get("", response_model=list[ClassOut])
def list_classes(course_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Class)
    if course_id is not None:
        query = query.filter(Class.course_id == course_id)
    return query.all()


@router.post("", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    get_owned_course(db, payload.course_id, current_user)
    class_ = Class(**payload.model_dump(exclude={"schedules"}))
    class_.schedules = build_schedules(payload.schedules)
    validate_schedules(class_)
    db.add(class_)
    db.commit()
    db.refresh(class_)
    return class_


@router.get("/mine", response_model=list[ClassOut])
def list_my_classes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """คลาสของนักศึกษาที่ login อยู่ (เฉพาะที่ลงทะเบียนแล้ว) หรือของอาจารย์ (วิชาที่สอน)"""
    if current_user.role == UserRole.student and current_user.student_profile:
        student_id = current_user.student_profile.id
        class_ids = (
            db.query(Enrollment.class_id).filter(Enrollment.student_id == student_id).subquery()
        )
        return db.query(Class).filter(Class.id.in_(class_ids)).all()

    if current_user.role == UserRole.teacher and current_user.teacher_profile:
        teacher_id = current_user.teacher_profile.id
        return (
            db.query(Class)
            .join(Class.course)
            .filter(Class.course.has(teacher_id=teacher_id))
            .all()
        )

    return []


@router.get("/{class_id}", response_model=ClassOut)
def get_class(class_id: int, db: Session = Depends(get_db)):
    class_ = db.query(Class).filter(Class.id == class_id).first()
    if class_ is None:
        raise HTTPException(status_code=404, detail="ไม่พบคลาสเรียนนี้")
    return class_


@router.put("/{class_id}", response_model=ClassOut)
def update_class(
    class_id: int,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    class_ = get_owned_class(db, class_id, current_user)
    data = payload.model_dump(exclude_unset=True, exclude={"schedules"})
    # ย้ายคลาสไปรายวิชาอื่นได้เฉพาะรายวิชาที่ตัวเองเป็นเจ้าของ
    if data.get("course_id") not in (None, class_.course_id):
        get_owned_course(db, data["course_id"], current_user)
    for key, value in data.items():
        setattr(class_, key, value)
    if payload.schedules is not None:
        class_.schedules = build_schedules(payload.schedules)
    validate_schedules(class_)
    db.commit()
    db.refresh(class_)
    return class_


@router.post("/{class_id}/start", response_model=ClassOut)
def start_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    """เริ่มการสอน: ย้ายจาก "รอเริ่มสอน" ไป "กำลังสอน" (สิ้นสุดอัตโนมัติเมื่อเลย end_date)"""
    class_ = get_owned_class(db, class_id, current_user)
    if class_.started_at is not None:
        raise HTTPException(status_code=400, detail="รายวิชานี้เริ่มการสอนไปแล้ว")
    if class_.end_date is None:
        raise HTTPException(status_code=400, detail="กรุณากำหนดวันสิ้นสุดการสอนก่อนเริ่มการสอน")
    if not class_.schedules:
        raise HTTPException(status_code=400, detail="กรุณากำหนดวันเรียนและเวลาเรียนก่อนเริ่มการสอน")
    class_.started_at = dt.datetime.now()
    db.commit()
    db.refresh(class_)
    return class_


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    class_ = get_owned_class(db, class_id, current_user)
    db.delete(class_)
    db.commit()


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------
@router.get("/{class_id}/students", response_model=list[EnrollmentOut])
def list_class_students(class_id: int, db: Session = Depends(get_db)):
    enrollments = db.query(Enrollment).filter(Enrollment.class_id == class_id).all()
    result = []
    for e in enrollments:
        result.append(
            EnrollmentOut(
                id=e.id,
                class_id=e.class_id,
                student_id=e.student_id,
                enroll_date=e.enroll_date,
                status=e.status,
                student=to_student_out(e.student) if e.student else None,
            )
        )
    return result


@router.post(
    "/{class_id}/students",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
)
def enroll_student(
    class_id: int,
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    if payload.class_id != class_id:
        raise HTTPException(status_code=400, detail="class_id ไม่ตรงกับ path")

    get_owned_class(db, class_id, current_user)

    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="ไม่พบนักศึกษานี้")

    existing = (
        db.query(Enrollment)
        .filter(Enrollment.class_id == class_id, Enrollment.student_id == payload.student_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="นักศึกษาคนนี้ลงทะเบียนคลาสนี้ไปแล้ว")

    enrollment = Enrollment(class_id=class_id, student_id=payload.student_id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return EnrollmentOut(
        id=enrollment.id,
        class_id=enrollment.class_id,
        student_id=enrollment.student_id,
        enroll_date=enrollment.enroll_date,
        status=enrollment.status,
        student=to_student_out(student),
    )


@router.delete(
    "/{class_id}/students/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def unenroll_student(
    class_id: int,
    enrollment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    get_owned_class(db, class_id, current_user)
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id, Enrollment.class_id == class_id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="ไม่พบการลงทะเบียนนี้")
    db.delete(enrollment)
    db.commit()
