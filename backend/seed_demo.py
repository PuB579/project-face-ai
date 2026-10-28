"""
Demo data — เติมข้อมูลตัวอย่างให้หน้าจอมีอะไรแสดง (ใช้กับรายวิชาที่มีอยู่แล้วในระบบ)
รันด้วย: python seed_demo.py

สิ่งที่ทำ (รันซ้ำได้ ไม่สร้างข้อมูลซ้ำ):
- ลงทะเบียนนักศึกษาทุกคนเข้าทุกคลาสของอาจารย์ T0001
- คลาสที่ "เริ่มการสอน" แล้ว: ย้อนเวลาเริ่มการสอนไปเป็นวันเริ่มการสอน (start_date)
  แล้วให้ระบบสร้างคาบตามตารางเรียนย้อนหลัง
- สุ่มผลเช็คชื่อของคาบที่ผ่านไปแล้ว (เข้าเรียน / มาสาย / ขาด) โดยแต่ละคนมีนิสัยต่างกัน
- เพิ่มประกาศตัวอย่าง
- ใส่สถานะใบหน้า/บัญชีให้นักศึกษาตัวอย่าง (ปกติ / รออนุมัติ / ใบหน้าถูกปฏิเสธ / ยังไม่ลงทะเบียน / ถูกระงับ)
  เฉพาะคนที่ยังไม่มีใบหน้าในระบบ รูปเป็นภาพวาดแทนใบหน้า ไม่มี embedding จึงเช็คชื่อด้วยใบหน้าจริงไม่ได้
"""
import datetime as dt
import os
import random
import uuid

from PIL import Image, ImageDraw

from app.attendance_utils import sync_scheduled_sessions
from app.config import settings
from app.database import SessionLocal
from app.models import (
    Announcement,
    ApprovalStatus,
    AttendanceDetail,
    AttendanceMethod,
    AttendanceSession,
    AttendanceStatus,
    Class,
    Course,
    Enrollment,
    FaceApproval,
    FaceProfile,
    Student,
    Teacher,
)

TEACHER_CODE = "T0001"
rng = random.Random(42)

# สถานะตัวอย่างของนักศึกษาจาก seed.py (approved / pending / rejected / none / suspended)
DEMO_FACE_STATUS = {
    "6604101301": "approved", "6604101302": "approved", "6604101303": "pending",
    "6604101304": "approved", "6604101305": "rejected", "6604101306": "approved",
    "6604101307": "none", "6604101308": "pending", "6604101309": "approved",
    "6604101310": "suspended", "6704101311": "approved", "6704101312": "pending",
    "6704101313": "rejected", "6704101314": "approved", "6704101315": "none",
    "6704101316": "approved", "6704101317": "pending", "6704101318": "rejected",
    "6704101319": "suspended", "6704101320": "none",
}
REJECT_REMARKS = ["รูปไม่ชัด กรุณาถ่ายใหม่ในที่แสงสว่าง", "ใบหน้าถูกบังบางส่วน", "ไม่ใช่รูปหน้าตรง"]


def add_minutes(t: dt.time, minutes: int) -> dt.time:
    return (dt.datetime.combine(dt.date.min, t) + dt.timedelta(minutes=minutes)).time()


def save_placeholder_face() -> str:
    """วาดรูปคนแบบง่าย ๆ แทนรูปใบหน้าจริง แล้วบันทึกในโฟลเดอร์ uploads/faces"""
    bg = tuple(rng.randint(190, 235) for _ in range(3))
    skin = rng.choice([(241, 204, 170), (224, 172, 125), (198, 140, 95)])
    hair = rng.choice([(40, 30, 25), (70, 50, 35), (25, 25, 30)])
    img = Image.new("RGB", (320, 400), bg)
    d = ImageDraw.Draw(img)
    d.ellipse((40, 300, 280, 520), fill=rng.choice([(60, 90, 160), (90, 90, 90), (150, 60, 60)]))
    d.ellipse((95, 70, 225, 230), fill=hair)
    d.ellipse((100, 95, 220, 250), fill=skin)
    d.ellipse((130, 155, 145, 170), fill=(40, 40, 40))
    d.ellipse((175, 155, 190, 170), fill=(40, 40, 40))
    d.arc((135, 185, 185, 220), 20, 160, fill=(150, 70, 70), width=3)

    face_dir = os.path.join(settings.uploads_dir, settings.face_uploads_subdir)
    os.makedirs(face_dir, exist_ok=True)
    path = os.path.join(face_dir, f"demo-{uuid.uuid4().hex}.png")
    img.save(path)
    return path


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

        # 5) สถานะใบหน้า/บัญชีของนักศึกษาตัวอย่าง (ข้ามคนที่มีใบหน้าในระบบแล้ว)
        tagged = 0
        for student in students:
            kind = DEMO_FACE_STATUS.get(student.student_code)
            if kind is None or student.face_profiles:
                continue
            if kind == "suspended":
                student.user.is_active = False
                kind = "approved"
            if kind != "none":
                profile = FaceProfile(student_id=student.id, image_path=save_placeholder_face(), is_active=True)
                db.add(profile)
                db.flush()
                db.add(
                    FaceApproval(
                        face_profile_id=profile.id,
                        teacher_id=teacher.id,
                        status=ApprovalStatus(kind),
                        remark=rng.choice(REJECT_REMARKS) if kind == "rejected" else None,
                    )
                )
            tagged += 1
        print(f"✔ ใส่สถานะใบหน้าให้นักศึกษาตัวอย่าง {tagged} คน")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
