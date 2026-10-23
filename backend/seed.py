"""
Seed script — สร้างข้อมูลตัวอย่างสำหรับทดสอบระบบ
รันด้วย: python seed.py

จะสร้าง:
- ภาควิชา 1 ภาค (วิทยาการคอมพิวเตอร์)
- อาจารย์ 1 คน: teacher01@example.com / Teach123!
- นักศึกษา 1 คน: student01@example.com / Passw0rd!
- รายวิชา 4 วิชาของสาขาวิทยาการคอมพิวเตอร์ แต่ละวิชามี 1 คลาส (กลุ่ม 01)
- ลบรายวิชาตัวอย่างชุดเก่า (CS-201 ถึง CS-205) ถ้ายังมีอยู่
- ลงทะเบียนนักศึกษาในทุกคลาส
- นักศึกษาตัวอย่างเพิ่มอีก 20 คน (student02 ถึง student21 / Passw0rd!) ลงทะเบียนตามชั้นปี
"""
from datetime import datetime

from app.database import SessionLocal
from app.models import Class, Course, Department, Enrollment, Student, Teacher, User, UserRole
from app.security import hash_password


def run():
    db = SessionLocal()
    try:
        department = db.query(Department).filter(Department.name == "วิทยาการคอมพิวเตอร์").first()
        if department is None:
            department = Department(
                name="วิทยาการคอมพิวเตอร์",
                description="ภาควิชาวิทยาการคอมพิวเตอร์ มหาวิทยาลัยแม่โจ้",
            )
            db.add(department)
            db.flush()
            print(f"✔ สร้างภาควิชา: {department.name}")

        teacher_user = db.query(User).filter(User.email == "teacher01@example.com").first()
        if teacher_user is None:
            teacher_user = User(
                email="teacher01@example.com",
                password_hash=hash_password("Teach123!"),
                role=UserRole.teacher,
            )
            db.add(teacher_user)
            db.flush()

            teacher = Teacher(
                user_id=teacher_user.id,
                teacher_code="T0001",
                first_name="สมชาย",
                last_name="ใจดี",
                department_id=department.id,
                position="อาจารย์ประจำ",
            )
            db.add(teacher)
            db.flush()
            print(f"✔ สร้างอาจารย์: {teacher_user.email} / Teach123!")
        else:
            teacher = teacher_user.teacher_profile

        student_user = db.query(User).filter(User.email == "student01@example.com").first()
        if student_user is None:
            student_user = User(
                email="student01@example.com",
                password_hash=hash_password("Passw0rd!"),
                role=UserRole.student,
            )
            db.add(student_user)
            db.flush()

            student = Student(
                user_id=student_user.id,
                student_code="6500001",
                first_name="สมหญิง",
                last_name="ตั้งใจเรียน",
                faculty="วิทยาศาสตร์",
                major="วิทยาการคอมพิวเตอร์",
            )
            db.add(student)
            db.flush()
            print(f"✔ สร้างนักศึกษา: {student_user.email} / Passw0rd!")
        else:
            student = student_user.student_profile

        # รายวิชาตัวอย่างชุดเก่า -> ลบทิ้ง (คลาส/การเช็คชื่อที่ผูกอยู่จะถูกลบตามไปด้วย)
        for old_code in ("CS-201", "CS-202", "CS-203", "CS-204", "CS-205"):
            old = db.query(Course).filter(Course.course_code == old_code).first()
            if old is not None:
                db.delete(old)
                db.flush()
                print(f"✘ ลบรายวิชาเก่า: {old_code}")

        # (รหัส, ชื่อไทย, หน่วยกิต, รายละเอียด, ภาคเรียน, ปีการศึกษา)
        course_defs = [
            (
                "10301211",
                "คณิตศาสตร์สำหรับวิทยาการคอมพิวเตอร์",
                3,
                "Mathematics for Computer Science | หน่วยกิต 3 (3-0-6)\n"
                "กลุ่ม 01: อังคาร 08:30-10:00 ห้อง 3203 อาคาร 141, "
                "ศุกร์ 08:30-10:00 ห้อง 3203 อาคาร 141",
                "1",
                "2569",
            ),
            (
                "10301371",
                "ปัญญาประดิษฐ์",
                3,
                "Artificial Intelligence | หน่วยกิต 3 (2-3-5)\n"
                "กลุ่ม 01: อังคาร 10:00-12:00 ห้อง 3203 อาคาร 141 (บรรยาย), "
                "ศุกร์ 13:00-16:00 Lab คอม2 อาคาร 105 (ปฏิบัติ)",
                "1",
                "2569",
            ),
            (
                "10301376",
                "การเรียนรู้ของเครื่องจักร",
                3,
                "Machine Learning | หน่วยกิต 3 (2-3-5)\n"
                "กลุ่ม 01: พฤหัสบดี 10:00-12:00 Lab คอม2 อาคาร 105 (บรรยาย), "
                "ศุกร์ 09:00-12:00 Lab คอม2 อาคาร 105 (ปฏิบัติ)",
                "2",
                "2568",
            ),
            (
                "10301113",
                "คณิตศาสตร์ดีสครีต",
                3,
                "Discrete Mathematics | หน่วยกิต 3 (3-0-6)\n"
                "กลุ่ม 01: จันทร์ 10:30-12:00 ห้อง 3203 อาคาร 141, "
                "พฤหัสบดี 14:00-15:30 ห้อง 3203 อาคาร 141",
                "2",
                "2568",
            ),
        ]

        classes_by_code = {}
        for code, name, credit, description, semester, year in course_defs:
            course = db.query(Course).filter(Course.course_code == code).first()
            if course is None:
                course = Course(
                    course_code=code,
                    course_name=name,
                    teacher_id=teacher.id,
                    department_id=department.id,
                    credit=credit,
                    description=description,
                )
                db.add(course)
                db.flush()
                print(f"✔ สร้างรายวิชา: {code} - {name}")

            class_ = db.query(Class).filter(Class.course_id == course.id).first()
            if class_ is None:
                class_ = Class(
                    course_id=course.id,
                    class_code=f"{code}-01",
                    class_name=f"{name} (กลุ่ม 01)",
                    semester=semester,
                    academic_year=year,
                    started_at=datetime.now(),
                )
                db.add(class_)
                db.flush()
                print(f"  ↳ สร้างคลาส: {class_.class_code}")

            enrollment = (
                db.query(Enrollment)
                .filter(Enrollment.class_id == class_.id, Enrollment.student_id == student.id)
                .first()
            )
            if enrollment is None:
                db.add(Enrollment(class_id=class_.id, student_id=student.id))
                print(f"  ↳ ลงทะเบียน {student.student_code} ในคลาส {class_.class_code}")
            classes_by_code[code] = class_

        # นักศึกษาตัวอย่าง 20 คน: ปี 3 (รหัส 66) เรียน AI/ML, ปี 2 (รหัส 67) เรียนคณิตฯ
        fake_students = [
            ("6604101301", "กิตติพัฒน์", "วงศ์ใหญ่", 3),
            ("6604101302", "ณัฐธิดา", "แก้วมณี", 3),
            ("6604101303", "ธนกร", "ศรีสุข", 3),
            ("6604101304", "พิมพ์ชนก", "บุญมา", 3),
            ("6604101305", "ภูมิพัฒน์", "คำแสน", 3),
            ("6604101306", "วรรณวิสา", "อินทร์แก้ว", 3),
            ("6604101307", "ศุภกร", "ปัญญาดี", 3),
            ("6604101308", "สุชานันท์", "ทองคำ", 3),
            ("6604101309", "อภิสิทธิ์", "จันทร์เพ็ญ", 3),
            ("6604101310", "ชลธิชา", "สายสุนีย์", 3),
            ("6704101311", "จิรายุ", "มณีวงศ์", 2),
            ("6704101312", "ปุณยวีร์", "ศรีวิชัย", 2),
            ("6704101313", "ธีรภัทร", "ใจคำ", 2),
            ("6704101314", "กัญญาณัฐ", "ดวงแก้ว", 2),
            ("6704101315", "รัชชานนท์", "สมบูรณ์", 2),
            ("6704101316", "เบญจมาศ", "ไชยวงศ์", 2),
            ("6704101317", "ปฏิภาณ", "นันทวงศ์", 2),
            ("6704101318", "อรอุมา", "เรือนแก้ว", 2),
            ("6704101319", "ณัฐวุฒิ", "ทิพย์มงคล", 2),
            ("6704101320", "ศิริลักษณ์", "พรหมวงศ์", 2),
        ]
        class_codes_by_year = {
            3: ["10301371", "10301376", "10301211"],
            2: ["10301113", "10301211"],
        }
        for i, (code, first, last, year) in enumerate(fake_students, start=2):
            email = f"student{i:02d}@example.com"
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, password_hash=hash_password("Passw0rd!"), role=UserRole.student)
                db.add(user)
                db.flush()
                db.add(
                    Student(
                        user_id=user.id,
                        student_code=code,
                        first_name=first,
                        last_name=last,
                        faculty="วิทยาศาสตร์",
                        major="วิทยาการคอมพิวเตอร์",
                        phone=f"08{i:02d}{int(code[-4:]):06d}",
                    )
                )
                db.flush()
                print(f"✔ สร้างนักศึกษา: {code} {first} {last} ({email})")
            s = user.student_profile
            for course_code in class_codes_by_year[year]:
                cls = classes_by_code[course_code]
                exists = (
                    db.query(Enrollment)
                    .filter(Enrollment.class_id == cls.id, Enrollment.student_id == s.id)
                    .first()
                )
                if exists is None:
                    db.add(Enrollment(class_id=cls.id, student_id=s.id))

        db.commit()
        print("\n เสร็จสิ้น! ข้อมูลตัวอย่างพร้อมใช้งาน")
        print("   อาจารย์: teacher01@example.com / Teach123!")
        print("   นักศึกษา: student01@example.com / Passw0rd!")

    finally:
        db.close()


if __name__ == "__main__":
    run()
