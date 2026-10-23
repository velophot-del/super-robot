import { BrowserRouter, Routes, Route, Navigate, Outlet, Link, useLocation } from 'react-router-dom';
import { ConfigProvider, App as AntApp, Spin, Result, Button } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import theme from './theme';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import AppLayout from './components/AppLayout';

// Pages
import ClassesPage from './pages/DataManagement/ClassesPage';
import TeachersPage from './pages/DataManagement/TeachersPage';
import CoursesPage from './pages/DataManagement/CoursesPage';
import ClassroomsPage from './pages/DataManagement/ClassroomsPage';
import AISettingsPage from './pages/AISettingsPage';
import DataDownloadPage from './pages/DataDownloadPage';
import AdminHistoryPage from './pages/AdminHistoryPage';
import TeacherMatchPage from './pages/TeacherMatchPage';
import TeacherTimetablePage from './pages/TeacherTimetablePage';
import Login from './pages/Login';
import DebugPage from './pages/DebugPage';
import { can, requiresAccountSetup } from './lib/accessPolicy';
import PlanningWorkspace, { ManagementPlanningWorkspace } from './pages/PlanningWorkspace';
import TeacherProfilePage from './pages/TeacherProfilePage';

function ManagementRoute() {
  const { user } = useAuth();
  return can(user,'admin') ? <Outlet /> : <Result status="403" title="无权访问管理功能"
    subTitle="教师端仅提供本人教学功能。" extra={<Link to="/timetable"><Button type="primary">返回我的课表</Button></Link>} />;
}

function ReviewWorkspaceRoute(){
  const {user}=useAuth();
  return can(user,'admin')||can(user,'review')||can(user,'publish')?<ManagementPlanningWorkspace section="review"/>:<Result status="403" title="无权访问管理审核工作台"/>;
}

function TimetableRoute(){
  const {user}=useAuth();
  return can(user,'admin')?<AdminHistoryPage/>:can(user,'teaching')?<TeacherTimetablePage/>:<Result status="403" title="无权访问历史课表"/>;
}

function WorkspaceHome() {
  const { user } = useAuth();
  return user?.grants?.length ? <Navigate to="/planning" replace /> : <Result status="403" title="账号尚未获授权" subTitle="请联系管理员授予教学或审核职能。" />;
}

// 路由守卫：未登录重定向到登录页
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requiresAccountSetup(user) && location.pathname !== '/profile') return <Navigate to="/profile" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <AntApp>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              {/* 公开路由 */}
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Navigate to="/login" replace />} />
              <Route path="/debug" element={<DebugPage />} />

              {/* 受保护路由（需要登录） */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<WorkspaceHome />} />
                <Route path="/planning" element={<PlanningWorkspace />} />
                <Route path="/planning/matches" element={<TeacherMatchPage />} />
                <Route path="/planning/review" element={<ReviewWorkspaceRoute />} />
                <Route path="/profile" element={<TeacherProfilePage />} />
                <Route element={<ManagementRoute />}>
                <Route path="/data/classes" element={<ClassesPage />} />
                <Route path="/data/teachers" element={<TeachersPage />} />
                <Route path="/data/courses" element={<CoursesPage />} />
                <Route path="/data/classrooms" element={<ClassroomsPage />} />
                <Route path="/data/download" element={<DataDownloadPage />} />
                <Route path="/settings/ai" element={<AISettingsPage />} />
                </Route>
                <Route path="/timetable" element={<TimetableRoute />} />
                <Route path="*" element={<Navigate to="/planning" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </AntApp>
    </ConfigProvider>
  );
}
