import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Eye, EyeOff, LogOut, Menu, Moon, Settings, Sun, User } from 'lucide-react'
import { useTheme } from '@/hooks/use-theme'
import { useIsMobile } from '@/hooks/use-mobile'
import { useAuth } from '@/hooks/use-auth'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import { toolboxes, type ToolboxConfig } from '@/customer/toolboxes'
import { cn } from '@/lib/utils'

function getDisplayName(email: string | undefined): string {
  if (!email) return 'User'
  return email.split('@')[0]
}

interface AppSidebarProps {
  activeToolbox: string
  activeView: string
  children?: ReactNode
}

function SidebarContent({ activeToolbox, activeView, children }: AppSidebarProps) {
  const { theme, toggleTheme } = useTheme()
  const { user, role, effectiveRole, previewAsRegular, setPreviewAsRegular, logout } = useAuth()
  const email = user?.email
  const displayName = getDisplayName(email)
  const isAdmin = role === 'admin'

  return (
    <div className="flex flex-col h-full pt-6">
      {/* Branding */}
      <div className="flex items-center gap-3 px-5 mb-8">
        <img src="/fulcrum-logo.png" alt="Fulcrum" className="h-11 w-11" />
        <div>
          <div className="font-headline text-base font-bold tracking-tight uppercase">Fulcrum</div>
          <div className="text-[10px] text-muted-foreground tracking-widest uppercase">
            Industrial Intel
          </div>
        </div>
      </div>

      {/* Toolbox Navigation */}
      <nav className="flex flex-col gap-1 px-3">
        {toolboxes
          .filter((tb) => tb.visible_in_sidebar !== false)
          .map((tb) => (
            <ToolboxSection
              key={tb.id}
              config={tb}
              isActive={tb.id === activeToolbox}
              activeView={activeView}
            />
          ))}
        {effectiveRole === 'admin' && (
          <Link
            to="/admin"
            className={cn(
              'flex items-center gap-2.5 px-3 py-2 rounded-[0.25rem] text-sm font-medium transition-colors',
              'text-muted-foreground hover:text-foreground hover:bg-accent/30'
            )}
          >
            <Settings className="h-4 w-4 flex-shrink-0" />
            <span className="flex-1">Admin</span>
          </Link>
        )}
      </nav>

      {/* Page-specific sidebar content */}
      {children && <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">{children}</div>}

      {/* Footer */}
      <div className="mt-auto px-3 pb-4">
        <div className="flex items-center gap-1 rounded-[0.25rem]">
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex flex-1 items-center gap-3 px-3 py-2.5 rounded-[0.25rem] hover:bg-accent/30 transition-colors min-w-0 text-left"
              aria-label="User menu"
            >
              <div className="h-8 w-8 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0">
                <User className="h-4 w-4 text-on-primary-fixed" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{displayName}</div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {previewAsRegular ? 'Previewing as regular' : (email ?? '')}
                </div>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="top">
              {isAdmin && (
                <DropdownMenuItem onClick={() => setPreviewAsRegular(!previewAsRegular)}>
                  {previewAsRegular ? (
                    <>
                      <EyeOff className="mr-2 h-4 w-4" />
                      Stop previewing
                    </>
                  ) : (
                    <>
                      <Eye className="mr-2 h-4 w-4" />
                      Preview as regular user
                    </>
                  )}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={() => void logout()}>
                <LogOut className="mr-2 h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <button
            onClick={toggleTheme}
            className="h-7 w-7 flex items-center justify-center rounded-[0.25rem] hover:bg-accent transition-colors flex-shrink-0"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? (
              <Moon className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Sun className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function ToolboxSection({
  config,
  isActive,
  activeView,
}: {
  config: ToolboxConfig
  isActive: boolean
  activeView: string
}) {
  const Icon = config.icon

  return (
    <div className="mb-1">
      {/* Toolbox header */}
      <Link
        to={`/${config.id}/${config.views[0].id}`}
        className={cn(
          'flex items-center gap-2.5 px-3 py-2 rounded-[0.25rem] text-sm font-medium transition-colors',
          isActive
            ? 'text-foreground bg-accent/50'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent/30'
        )}
      >
        <Icon className="h-4 w-4 flex-shrink-0" />
        <span className="flex-1">{config.label}</span>
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 transition-transform text-muted-foreground',
            isActive && 'rotate-90'
          )}
        />
      </Link>

      {/* Views (expanded when active) */}
      {isActive && (
        <div className="ml-4 mt-0.5 flex flex-col gap-0.5">
          {config.views.map((view) => {
            const isActiveView = view.id === activeView
            return (
              <Link
                key={view.id}
                to={`/${config.id}/${view.id}`}
                className={cn(
                  'flex items-center px-3 py-1.5 rounded-[0.25rem] text-sm transition-colors',
                  isActiveView
                    ? 'text-foreground font-medium bg-accent border-l-2 border-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                )}
              >
                {view.label}
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MobileSidebarContent({
  activeToolbox,
  activeView,
  onNavigate,
}: AppSidebarProps & { onNavigate?: () => void }) {
  const { theme, toggleTheme } = useTheme()
  const { user, role, effectiveRole, previewAsRegular, setPreviewAsRegular, logout } = useAuth()
  const email = user?.email
  const displayName = getDisplayName(email)
  const isAdmin = role === 'admin'

  return (
    <div className="flex flex-col h-full pt-6">
      {/* Branding */}
      <div className="flex items-center gap-3 px-5 mb-6">
        <img src="/fulcrum-logo.png" alt="Fulcrum" className="h-9 w-9" />
        <div>
          <div className="font-headline text-sm font-bold tracking-tight uppercase">Fulcrum</div>
        </div>
      </div>

      {/* Flat list grouped by toolbox */}
      <nav className="flex flex-col gap-0.5 px-3 overflow-y-auto flex-1">
        {toolboxes
          .filter((tb) => tb.visible_in_sidebar !== false)
          .map((tb) => {
            const Icon = tb.icon
            return (
              <div key={tb.id}>
                {/* Toolbox label (non-interactive) */}
                <div className="flex items-center gap-2 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mt-2 first:mt-0">
                  <Icon className="h-3.5 w-3.5" />
                  {tb.label}
                </div>
                {/* Views */}
                {tb.views.map((view) => {
                  const isActiveView = tb.id === activeToolbox && view.id === activeView
                  return (
                    <Link
                      key={`${tb.id}-${view.id}`}
                      to={`/${tb.id}/${view.id}`}
                      onClick={onNavigate}
                      className={cn(
                        'flex items-center px-3 py-2 ml-2 rounded-[0.25rem] text-sm transition-colors',
                        isActiveView
                          ? 'text-foreground font-medium bg-accent border-l-2 border-primary'
                          : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                      )}
                    >
                      {view.label}
                    </Link>
                  )
                })}
              </div>
            )
          })}
        {effectiveRole === 'admin' && (
          <Link
            to="/admin"
            onClick={onNavigate}
            className="flex items-center gap-2 px-3 py-2 ml-2 mt-3 rounded-[0.25rem] text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            Admin
          </Link>
        )}
      </nav>

      {/* Footer */}
      <div className="mt-auto px-3 pb-4">
        <div className="flex items-center gap-2 px-3 py-2">
          <div className="h-7 w-7 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0">
            <User className="h-3.5 w-3.5 text-on-primary-fixed" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium truncate">{displayName}</div>
            <div className="text-[10px] text-muted-foreground truncate">
              {previewAsRegular ? 'Previewing as regular' : (email ?? '')}
            </div>
          </div>
          {isAdmin && (
            <button
              onClick={() => setPreviewAsRegular(!previewAsRegular)}
              className="h-7 w-7 flex items-center justify-center rounded-[0.25rem] hover:bg-accent transition-colors flex-shrink-0"
              aria-label={
                previewAsRegular ? 'Stop previewing as regular user' : 'Preview as regular user'
              }
            >
              {previewAsRegular ? (
                <EyeOff className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <Eye className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </button>
          )}
          <button
            onClick={() => void logout()}
            className="h-7 w-7 flex items-center justify-center rounded-[0.25rem] hover:bg-accent transition-colors flex-shrink-0"
            aria-label="Sign out"
          >
            <LogOut className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={toggleTheme}
            className="h-7 w-7 flex items-center justify-center rounded-[0.25rem] hover:bg-accent transition-colors flex-shrink-0"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? (
              <Moon className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <Sun className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AppSidebar(props: AppSidebarProps) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)

  if (isMobile) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-card border-b border-outline-variant flex-shrink-0">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <button
              className="h-8 w-8 flex items-center justify-center rounded-[0.25rem] hover:bg-accent transition-colors"
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-[260px] p-0 border-r border-outline-variant"
            aria-describedby={undefined}
          >
            <VisuallyHidden>
              <SheetTitle>Navigation</SheetTitle>
            </VisuallyHidden>
            <MobileSidebarContent {...props} onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
        <img src="/fulcrum-logo.png" alt="Fulcrum" className="h-7 w-7" />
        <span className="font-headline text-sm font-bold tracking-tight uppercase">Fulcrum</span>
      </div>
    )
  }

  return (
    <aside className="flex w-[260px] flex-shrink-0 bg-card flex-col">
      <SidebarContent {...props} />
    </aside>
  )
}
