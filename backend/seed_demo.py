"""
Demo data — เติมข้อมูลตัวอย่างให้หน้าจอมีอะไรแสดง (ใช้กับรายวิชาที่มีอยู่แล้วในระบบ)
รันด้วย: python seed_demo.py

สิ่งที่ทำ (รันซ้ำได้ ไม่สร้างข้อมูลซ้ำ):
- ลงทะเบียนนักศึกษาทุกคนเข้าทุกคลาสของอาจารย์ T0001
- คลาสที่ "เริ่มการสอน" แล้ว: ย้อนเวลาเริ่มการสอนไปเป็นวันเริ่มการสอน (start_date)
  แล้วให้ระบบสร้างคาบตามตารางเรียนย้อนหลัง
- สุ่มผลเช็คชื่อของคาบที่ผ่านไปแล้ว (เข้าเรียน / มาสาย / ขาด) โดยแต่ละคนมีนิสัยต่างกัน
- เพิ่มประกาศตัวอย่าง
"""
import datetime as dt
import random

from app.attendance_utils import sync_scheduled_sessions
from app.database import SessionLocal
from app.models import (
    Announcement,
    AttendanceDetail,
    AttendanceMethod,
    AttendanceSession,
    AttendanceStatus,
    Class,
    Course,
    Enrollment,
    Student,
    Teacher,
)

TEACHER_CODE = "T0001"
rng = random.Random(42)


def add_minutes(t: dt.time, minutes: int) -> dt.time:
    return (dt.datetime.combine(dt.date.min, t) + dt.timedelta(minutes=minutes)).time()


def run():
    db = SessionLocal()
    try:
        teacher = db.query(Teacher).filter(Teacher.teacher_code == TEACHER_CODE).first()
        if teacher is None:
            raise SystemExit(f"ไม่พบอาจารย์ {TEACHER_CODE} — รัน python seed.py ก่อน")
        classes = db.query(Class).join(Course).filter(Course.teacher_id == teacher.id).all()
        students = db.query(Student).all()
        if not classes:
            raise SystemExit("อาจารย์ยังไม่มีรายวิชา — สร้างรายวิชาจากหน้าเว็บก่อน")

        # 1) ลงทะเบียน
        for class_ in classes:
            enrolled = {e.student_id for e in class_.enrollments}
            for student in students:
                if student.id not in enrolled:
                    db.add(Enrollment(class_id=class_.id, student_id=student.id))
            print(f"✔ ลงทะเบียน {len(students)} คน ใน {class_.course.course_code}")
        db.flush()

        # 2) ย้อนวันเริ่มการสอนเพื่อให้มีประวัติ แล้วสร้างคาบตามตารางเรียน
        for class_ in classes:
            if class_.started_at is not None and class_.start_date is not None:
                start_dt = dt.datetime.combine(class_.start_date, dt.time(8, 0))
                if class_.started_at > start_dt:
                    class_.started_at = start_dt
        db.commit()
        sync_scheduled_sessions(db)

        # 3) สุ่มผลเช็คชื่อของคาบที่จบไปแล้ว
        now = dt.datetime.now()
        # นิสัยของแต่ละคน: (โอกาสขาด, โอกาสสาย)
        habit = {s.id: (rng.choice([0.02, 0.05, 0.08, 0.15, 0.3]), rng.choice([0.05, 0.1, 0.2, 0.35])) for s in students}
        created = 0
        for class_ in classes:
            sessions = db.query(AttendanceSession).filter(AttendanceSession.class_id == class_.id).all()
            for session in sessions:
                end = dt.datetime.combine(session.session_date, session.end_time or dt.time(23, 59))
                if end > now:
                    continue
                done = {d.enrollment_id for d in session.attendance_details}
                for enrollment in class_.enrollments:
                    if enrollment.id in done:
                        continue
                    p_absent, p_late = habit[enrollment.student_id]
                    roll = rng.random()
                    if roll < p_absent:
                        continue  # ไม่มีแถว = ขาด (ระบบอนุมานเอง)
                    late = roll < p_absent + p_late
                    threshold = class_.late_threshold_minutes
                    minutes = rng.randint(threshold + 1, threshold + 45) if late else rng.randint(0, threshold)
                    manual = rng.random() < 0.05
                    db.add(
                        AttendanceDetail(
                            session_id=session.id,
                            enrollment_id=enrollment.id,
                            status=AttendanceStatus.late if late else AttendanceStatus.present,
                            method=AttendanceMethod.manual if manual else AttendanceMethod.face,
                            check_in_time=add_minutes(session.start_time, minutes),
                            confidence=None if manual else round(rng.uniform(86, 99.5), 2),
                        )
                    )
                    created += 1
            print(f"✔ {class_.course.course_code}: {len(sessions)} คาบ")
        print(f"✔ บันทึกผลเช็คชื่อ {created} รายการ")

        # 4) ประกาศ
        if not db.query(Announcement).filter(Announcement.teacher_id == teacher.id).first():
            first, second = classes[0], classes[-1]
            db.add_all([
                Announcement(
                    teacher_id=teacher.id,
                    class_id=first.id,
                    title="แจ้งสอบกลางภาค",
                    body=f"สอบกลางภาควิชา {first.course.course_name} ตามตารางสอบของมหาวิทยาลัย กรุณามาก่อนเวลา 15 นาที",
                    pinned=True,
                ),
                Announcement(
                    teacher_id=teacher.id,
                    class_id=second.id,
                    title="ลงทะเบียนใบหน้าก่อนเริ่มเรียน",
                    body="นักศึกษาที่ยังไม่ได้ลงทะเบียนใบหน้า กรุณาลงทะเบียนในเมนูโปรไฟล์ก่อนคาบแรก",
                ),
                Announcement(
                    teacher_id=teacher.id,
                    class_id=None,
                    title="ยินดีต้อนรับสู่ภาคเรียนใหม่",
                    body="ตรวจสอบตารางเรียนและเวลาเช็คชื่อของแต่ละวิชาได้ที่เมนูรายวิชาของฉัน",
                ),
            ])
            print("✔ เพิ่มประกาศ 3 รายการ")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
