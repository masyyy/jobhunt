import { createContext, useContext, type ReactNode } from 'react'

interface SidebarContextValue {
  sidebarContent: ReactNode
  setSidebarContent: (content: ReactNode) => void
}

export const SidebarContext = createContext<SidebarContextValue>({
  sidebarContent: null,
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  setSidebarContent: () => {},
})

export function useSidebar() {
  return useContext(SidebarContext)
}
