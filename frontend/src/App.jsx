import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, Outlet } from "react-router-dom";
import { getToken, getUser } from "./lib/api";

const FaceAttendLanding = lazy(() => import("./components/FaceAttendLanding"));
const LoginPage = lazy(() => import("./components/LoginPage"));

const StudentDashboard = lazy(() => import("./components/Student/StudentDashboard"));
const CheckinHistory = lazy(() => import("./components/Student/CheckinHistory"));
const Faceregistration = lazy(() => import("./components/Student/Faceregistration"));
const StudentCheckin = lazy(() => import("./components/Student/StudentCheckin"));
const MyCourses = lazy(() => import("./components/Student/MyCourses"));
const Schedule = lazy(() => import("./components/Student/Schedule"));
const Profile = lazy(() => import("./components/Student/Profile"));
const Settings = lazy(() => import("./components/Student/Settings"));
const Announcements = lazy(() => import("./components/Student/Announcements"));

const TeacherDashboard = lazy(() => import("./components/Teacher/TeacherDashboard"));
const TeacherCourses = lazy(() => import("./components/Teacher/TeacherCourses"));
const TeacherCheckinHistory = lazy(() => import("./components/Teacher/TeacherCheckinHistory"));
const TeacherAttendanceReport = lazy(() => import("./components/Teacher/TeacherAttendanceReport"));
const TeacherAttendanceScore = lazy(() => import("./components/Teacher/TeacherAttendanceScore"));
const TeacherStudents = lazy(() => import("./components/Teacher/TeacherStudents"));
const TeacherExportData = lazy(() => import("./components/Teacher/TeacherExportData"));
const TeacherProfile = lazy(() => import("./components/Teacher/TeacherProfile"));
const TeacherSettings = lazy(() => import("./components/Teacher/TeacherSettings"));
const TeacherAnnouncements = lazy(() => import("./components/Teacher/TeacherAnnouncements"));

// ยังไม่ login -> ไปหน้า login, login แล้วแต่ผิดบทบาท -> ไปหน้าหลักของบทบาทตัวเอง
function RequireRole({ role }) {
  const user = getUser();
  if (!getToken() || !user) return <Navigate to="/login" replace />;
  if (user.role !== role) {
    return <Navigate to={user.role === "teacher" ? "/teacher-dashboard" : "/dashboard"} replace />;
  }
  return <Outlet />;
}

// แต่ละหน้าโหลดแยกไฟล์ (code splitting) ระหว่างรอโหลดแสดงข้อความนี้
function PageFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-slate-400 dark:text-slate-500">
      กำลังโหลด...
    </div>
  );
}

function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<FaceAttendLanding />} />
        <Route path="/login" element={<LoginPage />} />

        {/* Student */}
        <Route element={<RequireRole role="student" />}>
          <Route path="/dashboard" element={<StudentDashboard />} />
          <Route path="/checkin" element={<StudentCheckin />} />
          <Route path="/history" element={<CheckinHistory />} />
          <Route path="/face-registration" element={<Faceregistration />} />
          <Route path="/courses" element={<MyCourses />} />
          <Route path="/schedule" element={<Schedule />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/announcements" element={<Announcements />} />
        </Route>

        {/* Teacher */}
        <Route element={<RequireRole role="teacher" />}>
          <Route path="/teacher-dashboard" element={<TeacherDashboard />} />
          <Route path="/teacher-courses" element={<TeacherCourses />} />
          <Route path="/teacher-history" element={<TeacherCheckinHistory />} />
          <Route path="/teacher-report" element={<TeacherAttendanceReport />} />
          <Route path="/teacher-scores" element={<TeacherAttendanceScore />} />
          <Route path="/teacher-students" element={<TeacherStudents />} />
          <Route path="/teacher-export" element={<TeacherExportData />} />
          <Route path="/teacher-announcements" element={<TeacherAnnouncements />} />
          <Route path="/teacher-profile" element={<TeacherProfile />} />
          <Route path="/teacher-settings" element={<TeacherSettings />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default App;
