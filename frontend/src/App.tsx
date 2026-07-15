import { useEffect } from 'react';
import { Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/shared/hooks/useAuth';
import { AppLayout } from '@/layouts/AppLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import LoginPage from '@/modules/auth/LoginPage';
import DashboardPage from '@/modules/dashboard/DashboardPage';
import CamerasPage from '@/modules/cameras/CamerasPage';
import LiveWallPage from '@/modules/live-wall/LiveWallPage';
import FloorPlansPage from '@/modules/floor-plan/FloorPlansPage';
import FloorPlanEditPage from '@/modules/floor-plan/FloorPlanEditPage';
import AlertsPage from "@/modules/alerts/AlertsPage";
import RecordingsPage from "@/modules/recordings/RecordingsPage";
import SettingsPage from "@/modules/settings/SettingsPage";
import TenantSettingsPage from "@/modules/settings/TenantSettingsPage";
import UsersListPage from "@/modules/users/UsersListPage";
import RolesListPage from "@/modules/roles/RolesListPage";
import AnalyticsPage from "@/modules/analytics/AnalyticsPage";
import DailyReportPage from "@/modules/analytics/DailyReportPage";
import EmployeesPage from "@/modules/employees/EmployeesPage";
import ZonesPage from "@/modules/zones/ZonesPage";
import PersonsPage from "@/modules/persons/PersonsPage";
import PersonDetailPage from "@/modules/persons/PersonDetailPage";
import BEVTrackingPage from "@/modules/bev/BEVTrackingPage";
import CameraCalibrationPage from "@/modules/bev/CameraCalibrationPage";

function ProtectedRoute() {
  const { accessToken } = useAuth();
  if (!accessToken) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function PublicOnlyRoute() {
  const { accessToken } = useAuth();
  if (accessToken) return <Navigate to="/" replace />;
  return <Outlet />;
}

export default function App() {
  const { i18n } = useTranslation();

  useEffect(() => {
    // Update <html> attributes when language changes — for RTL Arabic
    document.documentElement.lang = i18n.language;
    document.documentElement.dir = i18n.language === 'ar' ? 'rtl' : 'ltr';
  }, [i18n.language]);

  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute />}>
        {/* Bare, chrome-less route for the print-friendly PDF report. */}
        <Route path="reports/daily" element={<DailyReportPage />} />
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="live" element={<LiveWallPage />} />
          <Route path="floor-plan" element={<FloorPlansPage />} />
          <Route path="floor-plan/edit/:planId" element={<FloorPlanEditPage />} />
          <Route path="cameras" element={<CamerasPage />} />
          <Route path="persons" element={<PersonsPage />} />
          <Route path="persons/:personId" element={<PersonDetailPage />} />
          <Route path="bev" element={<BEVTrackingPage />} />
          <Route path="calibration" element={<CameraCalibrationPage />} />
          <Route path="zones" element={<ZonesPage />} />
          <Route path="employees" element={<EmployeesPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="recordings" element={<RecordingsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="users" element={<UsersListPage />} />
          <Route path="roles" element={<RolesListPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="settings/organization" element={<TenantSettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
