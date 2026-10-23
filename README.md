# CS FaceAttend

ระบบเช็คชื่อเข้าเรียนด้วยการสแกนใบหน้า สำหรับภาควิชาวิทยาการคอมพิวเตอร์

นักศึกษาลงทะเบียนใบหน้าและเช็คชื่อผ่านกล้องในเบราว์เซอร์ ส่วนอาจารย์จัดการรายวิชา อนุมัติใบหน้า
ดูรายงานการเข้าเรียน และคิดคะแนนเข้าเรียนได้ในที่เดียว

## ความสามารถหลัก

**นักศึกษา**
- ลงทะเบียนใบหน้า (รออาจารย์อนุมัติก่อนใช้งาน)
- เช็คชื่อด้วยใบหน้าในช่วงเวลาที่เปิดให้เช็คชื่อ
- ดูตารางเรียน รายวิชา ประวัติการเช็คชื่อ คะแนน และประกาศ

**อาจารย์**
- สร้างรายวิชาและคลาส กำหนดวันและเวลาเรียนประจำสัปดาห์ได้หลายช่วง แล้วกด "เริ่มการสอน"
- ระบบสร้างคาบเช็คชื่อตามตารางเรียนให้อัตโนมัติ (รวมถึงย้อนหลัง) และนับ "ขาด" ให้เองเมื่อหมดเวลา
- ตั้งค่ารายคลาส: เวลาเปิดเช็คชื่อ เส้นแบ่งตรงเวลา/มาสาย ความมั่นใจขั้นต่ำของใบหน้า และการเช็คชื่อแบบ manual
- อนุมัติใบหน้านักศึกษา บันทึกการเข้าเรียนแทนนักศึกษาได้
- แดชบอร์ด รายงานการเข้าเรียน และคะแนนเข้าเรียน (หักคะแนนตามขั้นความสาย และการขาด)
- ส่งออกข้อมูลเป็น CSV / Excel / PDF

## เทคโนโลยีที่ใช้

| ส่วน | เทคโนโลยี |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, PyMySQL, Pydantic 2, JWT (python-jose), bcrypt (passlib) |
| จดจำใบหน้า | face_recognition (dlib) — ไม่บังคับติดตั้ง |
| ฐานข้อมูล | MySQL / MariaDB (เช่น XAMPP + phpMyAdmin) |
| Frontend | React 19, Vite, Tailwind CSS v4, React Router 7, Recharts, lucide-react |
| การทดสอบ | pytest (unit test), สคริปต์ smoke test ของ API, Playwright (end-to-end), ESLint |

## โครงสร้างโปรเจกต์

```
backend/            FastAPI API
  main.py           จุดเริ่มต้นของแอป (รวม router ทั้งหมด)
  app/              models, schemas, routers, กฎการเช็คชื่อ, ระบบจดจำใบหน้า
  seed.py           สร้างบัญชีและรายวิชาตัวอย่าง
  seed_demo.py      เติมข้อมูลการเช็คชื่อตัวอย่าง
  tests/            unit test (pytest) และ e2e_smoke.py
  README.md         คู่มือ backend แบบละเอียด (ตารางฐานข้อมูล, endpoint)
frontend/           React + Vite
  src/components/   หน้าฝั่งนักศึกษา (Student/) และอาจารย์ (Teacher/)
  src/lib/          ตัวเรียก API และฟังก์ชันจัดรูปแบบข้อมูล
  e2e/              Playwright tests
```

## การติดตั้งและรัน

### สิ่งที่ต้องมี

- **Python 3.11 หรือ 3.12** (อย่าใช้ 3.14 เพราะ numpy/dlib ยังไม่มี wheel ให้บน Windows)
- **Node.js 20.19 ขึ้นไป หรือ 22.12 ขึ้นไป** (ตามที่ Vite 8 กำหนด) และ npm
- **MySQL หรือ MariaDB** ที่มีฐานข้อมูล `project_face_ai_db` อยู่แล้ว

> **สำคัญ:** backend ไม่ได้สร้างตารางทั้งหมดให้เอง ฐานข้อมูลถูกสร้างและจัดการผ่าน phpMyAdmin
> (ไม่มี migration) ตอนเริ่มเซิร์ฟเวอร์จะเติมแค่คอลัมน์/ตารางใหม่ที่จำเป็น (`classes.started_at`,
> `class_schedules`) ไฟล์ `project_face_ai_db.sql` **ยังไม่ได้อยู่ใน repo นี้** ขอไฟล์จากทีมแล้ว import
> ผ่าน phpMyAdmin ก่อน รายชื่อตารางทั้ง 15 ตารางอยู่ใน [backend/README.md](backend/README.md)

### 1. Backend

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

ติดตั้งระบบจดจำใบหน้า (ไม่บังคับ — ถ้าไม่ติดตั้ง ส่วนอื่นยังใช้งานได้ เฉพาะ endpoint ใบหน้าจะตอบ HTTP 503):

```powershell
pip install dlib-bin
pip install --no-deps face_recognition==1.3.0
pip install git+https://github.com/ageitgey/face_recognition_models
pip install "setuptools<81"
```

ตั้งค่าการเชื่อมต่อ: คัดลอก `.env.example` เป็น `.env` แล้วแก้ค่า

```
DATABASE_URL=mysql+pymysql://root:@localhost:3306/project_face_ai_db?charset=utf8mb4
SECRET_KEY=ตั้งเป็นข้อความสุ่มยาวๆ
```

สร้างข้อมูลตัวอย่าง แล้วรันเซิร์ฟเวอร์:

```powershell
python seed.py          # บัญชีทดสอบและรายวิชาตัวอย่าง (รันซ้ำได้)
python seed_demo.py     # ไม่บังคับ: ข้อมูลการเช็คชื่อตัวอย่างให้หน้าจอมีอะไรแสดง
uvicorn main:app --reload
```

เปิด http://127.0.0.1:8000/docs เพื่อดูและทดลอง API (Swagger UI)

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

เปิด http://localhost:5173

frontend เรียก backend ที่ `http://127.0.0.1:8000` เป็นค่าเริ่มต้น ถ้า backend อยู่ที่อื่นให้สร้างไฟล์
`frontend/.env.local` แล้วใส่ `VITE_API_URL=http://<host>:<port>`
(ถ้าเปลี่ยนพอร์ตของ frontend ต้องเพิ่ม origin นั้นใน `cors_origins` ของ `backend/app/config.py` ด้วย)

### บัญชีทดสอบ (จาก `seed.py`)

| บทบาท | อีเมล | รหัสผ่าน |
|---|---|---|
| อาจารย์ | teacher01@example.com (รหัส T0001) | Teach123! |
| นักศึกษา | student01@example.com | Passw0rd! |
| นักศึกษาเพิ่มเติม | student02 ถึง student21 @example.com | Passw0rd! |

login ได้ทั้งด้วยอีเมล รหัสนักศึกษา หรือรหัสอาจารย์ ถ้า login ผิด 5 ครั้งภายใน 15 นาที
บัญชีนั้นจะถูกล็อกชั่วคราวจากเครื่องเดิม (รีสตาร์ต backend เพื่อล้างตัวนับระหว่างพัฒนาได้)

## การทดสอบ

| การทดสอบ | คำสั่ง | ต้องเปิดอะไรไว้ |
|---|---|---|
| Unit test ของ backend | `cd backend` แล้ว `pip install -r requirements-dev.txt` และ `py -3.12 -m pytest` | ไม่ต้องใช้ฐานข้อมูลหรือเซิร์ฟเวอร์ |
| Smoke test ของ API | `cd backend` แล้ว `python tests/e2e_smoke.py [รูปใบหน้า.jpg]` | MySQL + backend และรัน `seed.py` แล้ว |
| End-to-end (Playwright) | `cd frontend` แล้ว `npm run test:e2e` | MySQL + backend และรัน `seed.py` แล้ว (frontend เปิดให้อัตโนมัติ) |
| Lint / Build ของ frontend | `npm run lint` และ `npm run build` | — |

- **Unit test** ครอบคลุมกฎช่วงเวลาเช็คชื่อ เส้นแบ่งตรงเวลา/มาสาย การนับขาด สูตรคะแนน และการจำกัดการ login ผิด
  รันเฉพาะบางไฟล์ได้ เช่น `py -3.12 -m pytest tests/test_scores.py -k per_session`
- **Smoke test** เรียก API จริงทุกกลุ่ม ข้อมูลที่สร้างขึ้นระหว่างทดสอบขึ้นต้นด้วย `TEST-` และถูกลบเมื่อจบ
  ส่วนทดสอบใบหน้าต้องให้ student01 มีใบหน้าที่อนุมัติแล้ว
- **Playwright** ใช้กล้องปลอมของ Chromium รันเฉพาะไฟล์ได้ด้วย `npx playwright test e2e/auth.spec.js`
  หรือเฉพาะชื่อเทสต์ด้วย `npx playwright test -g "ชื่อเทสต์"` (ติดตั้งเบราว์เซอร์ครั้งแรกด้วย `npx playwright install chromium`)

## เอกสารเพิ่มเติม

- [backend/README.md](backend/README.md) — ตารางฐานข้อมูล ค่าตั้งรายคลาส ลำดับการทดสอบระบบ และรายการ endpoint
- [CLAUDE.md](CLAUDE.md) — สรุปสถาปัตยกรรมของโค้ด (ภาษาอังกฤษ)
