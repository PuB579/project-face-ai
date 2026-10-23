from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ensure_course_owner, require_teacher
from app.models import Course
from app.schemas import CourseCreate, CourseOut

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseOut])
def list_courses(
    teacher_id: int | None = None,
    department_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Course)
    if teacher_id is not None:
        query = query.filter(Course.teacher_id == teacher_id)
    if department_id is not None:
        query = query.filter(Course.department_id == department_id)
    return query.order_by(Course.course_code).all()


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_teacher),
):
    # รายวิชาที่สร้างต้องเป็นของอาจารย์ที่ login อยู่เสมอ
    teacher = current_user.teacher_profile
    if teacher is None:
        raise HTTPException(status_code=403, detail="ไม่พบข้อมูลอาจารย์ของบัญชีนี้")
    if payload.teacher_id not in (None, teacher.id):
        raise HTTPException(status_code=403, detail="สร้างรายวิชาให้อาจารย์คนอื่นไม่ได้")
    payload.teacher_id = teacher.id
    existing = db.query(Course).filter(Course.course_code == payload.course_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="รหัสวิชานี้ถูกใช้งานแล้ว")
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายวิชานี้")
    return course


@router.put("/{course_id}", response_model=CourseOut)
def update_course(
    course_id: int,
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_teacher),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายวิชานี้")
    ensure_course_owner(current_user, course)
    # ห้ามโอนรายวิชาไปให้อาจารย์คนอื่นผ่านการแก้ไข
    payload.teacher_id = course.teacher_id
    for key, value in payload.model_dump().items():
        setattr(course, key, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_teacher),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายวิชานี้")
    ensure_course_owner(current_user, course)
    db.delete(course)
    db.commit()
