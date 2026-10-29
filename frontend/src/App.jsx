import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import AdminPage from './pages/AdminPage.jsx'
import Spinner from './components/common/Spinner.jsx'

function FullScreenSpinner() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-ink">
      <Spinner size={28} />
    </div>
  )
}

function RequireAuth({ children }) {
  const { user, booting } = useAuth()
  if (booting) return <FullScreenSpinner />
  if (!user) return <Navigate to="/login" replace />
  return children
}

function RequireAdmin({ children }) {
  const { user, booting } = useAuth()
  if (booting) return <FullScreenSpinner />
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_admin) return <Navigate to="/" replace />
  return children
}

function RedirectIfAuthed({ children }) {
  const { user, booting } = useAuth()
  if (booting) return <FullScreenSpinner />
  if (user) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthed>
            <RegisterPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAdmin>
            <AdminPage />
          </RequireAdmin>
        }
      />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <ChatPage />
          </RequireAuth>
        }
      />
    </Routes>
  )
}
