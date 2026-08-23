/**
 * 路由与守卫（06 §7）：无 token 一律重定向 /login。
 */
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import AdminPage from "@/pages/Admin";
import ChatPage from "@/pages/Chat";
import DesignSystemPage from "@/pages/DesignSystem";
import GraphExplorerPage from "@/pages/GraphExplorer";
import LoginPage from "@/pages/Login";
import { useAuthStore } from "@/stores/authStore";

function RequireAuth() {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/graph" element={<GraphExplorerPage />} />
          <Route path="/admin" element={<AdminPage />} />
          {import.meta.env.DEV ? (
            <Route path="/design" element={<DesignSystemPage />} />
          ) : null}
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
