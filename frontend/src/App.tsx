import { useState, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { ThemeProvider } from './components/ThemeProvider'
import { getToolboxConfig, getDefaultToolbox } from './customer/toolboxes'
import AppSidebar from './components/AppSidebar'
import LoginGate from './components/LoginGate'
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

function AppRoutes() {
  const lastToolbox = getLastToolbox()
  const defaultTb = getToolboxConfig(lastToolbox) ?? getDefaultToolbox()
  const defaultRoute = `/${defaultTb.id}/${defaultTb.views[0].id}`

  return (
    <Routes>
      <Route path="/:toolboxId/:viewId" element={<ToolboxViewPage />} />
      <Route path="/" element={<Navigate to={defaultRoute} replace />} />
      <Route path="*" element={<Navigate to={defaultRoute} replace />} />
    </Routes>
  )
}

function App() {
  return (
    <ThemeProvider defaultTheme="dark">
      <LoginGate>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </QueryClientProvider>
      </LoginGate>
    </ThemeProvider>
  )
}

export default App
