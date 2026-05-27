import { useState, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { ThemeProvider } from './components/ThemeProvider'
import { AuthProvider } from './components/AuthProvider'
import { useAuth } from './hooks/use-auth'
import LoginPage from './pages/LoginPage'
import AcceptInvitePage from './pages/AcceptInvitePage'
import AdminPage from './pages/AdminPage'
import { getToolboxConfig, getDefaultToolbox } from './customer/toolboxes'
import AppSidebar from './components/AppSidebar'
import { SidebarContext } from './contexts/sidebar-context'

const queryClient = new QueryClient()

function getLastToolbox(): string {
  try {
    return localStorage.getItem('fulcrum-last-toolbox') ?? getDefaultToolbox().id
  } catch {
    return getDefaultToolbox().id
  }
}

function setLastToolbox(toolboxId: string) {
  try {
    localStorage.setItem('fulcrum-last-toolbox', toolboxId)
  } catch {
    // localStorage unavailable
  }
}

function ToolboxViewPage() {
  const { toolboxId, viewId } = useParams<{ toolboxId: string; viewId: string }>()
  const [sidebarContent, setSidebarContent] = useState<ReactNode>(null)

  const config = getToolboxConfig(toolboxId ?? '')
  if (!config) {
    const defaultTb = getDefaultToolbox()
    return <Navigate to={`/${defaultTb.id}/${defaultTb.views[0].id}`} replace />
  }

  // Remember last used toolbox
  setLastToolbox(config.id)

  const view = config.views.find((v) => v.id === viewId)
  if (!view) {
    return <Navigate to={`/${config.id}/${config.views[0].id}`} replace />
  }

  const ViewComponent = view.component

  return (
    <SidebarContext value={{ sidebarContent, setSidebarContent }}>
      <div className="h-dvh flex flex-col md:flex-row overflow-hidden">
        <AppSidebar activeToolbox={config.id} activeView={view.id}>
          {sidebarContent}
        </AppSidebar>
        <main className="flex-1 flex flex-col min-w-0 min-h-0">
          <ViewComponent key={`${config.id}-${view.id}`} />
        </main>
      </div>
    </SidebarContext>
  )
}

function AdminRoute() {
  const { effectiveRole } = useAuth()
  if (effectiveRole !== 'admin') return <Navigate to="/" replace />
  return <AdminPage />
}

function AuthenticatedRoutes() {
  const lastToolbox = getLastToolbox()
  const defaultTb = getToolboxConfig(lastToolbox) ?? getDefaultToolbox()
  const defaultRoute = `/${defaultTb.id}/${defaultTb.views[0].id}`

  return (
    <Routes>
      <Route path="/admin" element={<AdminRoute />} />
      <Route path="/:toolboxId/:viewId" element={<ToolboxViewPage />} />

      <Route path="/" element={<Navigate to={defaultRoute} replace />} />
      <Route path="/chat" element={<Navigate to={`/${lastToolbox}/chat`} replace />} />

      <Route path="*" element={<Navigate to={defaultRoute} replace />} />
    </Routes>
  )
}

function AppRoutes() {
  const { isAuthenticated, loading } = useAuth()
  if (loading) {
    return <div className="flex min-h-screen items-center justify-center bg-background" />
  }

  return (
    <Routes>
      {/* Always reachable: invite acceptance puts the user in a half-authenticated
          state, so this route must render regardless of isAuthenticated. */}
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route path="*" element={isAuthenticated ? <AuthenticatedRoutes /> : <LoginPage />} />
    </Routes>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="dark">
        <AuthProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

export default App
