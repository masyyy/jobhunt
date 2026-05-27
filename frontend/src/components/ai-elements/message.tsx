'use client'

import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { cjk } from '@streamdown/cjk'
import { code } from '@streamdown/code'
import { math } from '@streamdown/math'
import { mermaid } from '@streamdown/mermaid'
import type { UIMessage } from 'ai'
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'
import type { ComponentProps, HTMLAttributes, ReactElement, ReactNode } from 'react'
import {
  Children,
  createContext,
  isValidElement,
  memo,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { Streamdown } from 'streamdown'

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage['role']
}

export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      'group flex flex-col gap-2',
      from === 'user' ? 'is-user ml-auto w-fit max-w-[85%] justify-end' : 'is-assistant w-full',
      className
    )}
    {...props}
  />
)

export type MessageContentProps = HTMLAttributes<HTMLDivElement>

export const MessageContent = ({ children, className, ...props }: MessageContentProps) => (
  <div
    className={cn(
      'is-user:dark flex min-w-0 max-w-full flex-col gap-2 overflow-hidden text-sm',
      'group-[.is-user]:w-fit group-[.is-user]:ml-auto group-[.is-user]:rounded-[0.25rem] group-[.is-user]:bg-surface-container group-[.is-user]:px-4 group-[.is-user]:py-3 group-[.is-user]:text-foreground',
      'group-[.is-assistant]:w-full',
      'group-[.is-assistant]:text-foreground',
      className
    )}
    {...props}
  >
    {children}
  </div>
)

export type MessageActionsProps = ComponentProps<'div'>

export const MessageActions = ({ className, children, ...props }: MessageActionsProps) => (
  <div className={cn('flex items-center gap-1', className)} {...props}>
    {children}
  </div>
)

export type MessageActionProps = ComponentProps<typeof Button> & {
  tooltip?: string
  label?: string
}

export const MessageAction = ({
  tooltip,
  children,
  label,
  variant = 'ghost',
  size = 'icon-sm',
  ...props
}: MessageActionProps) => {
  const button = (
    <Button size={size} type="button" variant={variant} {...props}>
      {children}
      <span className="sr-only">{label ?? tooltip}</span>
    </Button>
  )

  if (tooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return button
}

interface MessageBranchContextType {
  currentBranch: number
  totalBranches: number
  goToPrevious: () => void
  goToNext: () => void
  branches: ReactElement[]
  setBranches: (branches: ReactElement[]) => void
}

const MessageBranchContext = createContext<MessageBranchContextType | null>(null)

const useMessageBranch = () => {
  const context = useContext(MessageBranchContext)

  if (!context) {
    throw new Error('MessageBranch components must be used within MessageBranch')
  }

  return context
}

export type MessageBranchProps = HTMLAttributes<HTMLDivElement> & {
  defaultBranch?: number
  onBranchChange?: (branchIndex: number) => void
}

export const MessageBranch = ({
  defaultBranch = 0,
  onBranchChange,
  className,
  ...props
}: MessageBranchProps) => {
  const [currentBranch, setCurrentBranch] = useState(defaultBranch)
  const [branches, setBranches] = useState<ReactElement[]>([])

  const handleBranchChange = (newBranch: number) => {
    setCurrentBranch(newBranch)
    onBranchChange?.(newBranch)
  }

  const goToPrevious = () => {
    const newBranch = currentBranch > 0 ? currentBranch - 1 : branches.length - 1
    handleBranchChange(newBranch)
  }

  const goToNext = () => {
    const newBranch = currentBranch < branches.length - 1 ? currentBranch + 1 : 0
    handleBranchChange(newBranch)
  }

  const contextValue: MessageBranchContextType = {
    currentBranch,
    totalBranches: branches.length,
    goToPrevious,
    goToNext,
    branches,
    setBranches,
  }

  return (
    <MessageBranchContext.Provider value={contextValue}>
      <div className={cn('grid w-full gap-2 [&>div]:pb-0', className)} {...props} />
    </MessageBranchContext.Provider>
  )
}

export type MessageBranchContentProps = HTMLAttributes<HTMLDivElement>

export const MessageBranchContent = ({ children, ...props }: MessageBranchContentProps) => {
  const { currentBranch, setBranches, branches } = useMessageBranch()

  const childrenArray = useMemo(() => {
    const result: ReactElement[] = []
    Children.forEach(children, (child) => {
      if (isValidElement(child)) {
        result.push(child)
      }
    })
    return result
  }, [children])

  // Use useEffect to update branches when they change
  useEffect(() => {
    if (branches.length !== childrenArray.length) {
      setBranches(childrenArray)
    }
  }, [childrenArray, branches, setBranches])

  return childrenArray.map((branch: ReactElement, index: number) => (
    <div
      className={cn(
        'grid gap-2 overflow-hidden [&>div]:pb-0',
        index === currentBranch ? 'block' : 'hidden'
      )}
      key={branch.key}
      {...props}
    >
      {branch as ReactNode}
    </div>
  ))
}

export type MessageBranchSelectorProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage['role']
}

export const MessageBranchSelector = ({
  className: _className,
  from: _from,
  ...props
}: MessageBranchSelectorProps) => {
  const { totalBranches } = useMessageBranch()

  // Don't render if there's only one branch
  if (totalBranches <= 1) {
    return null
  }

  return (
    <ButtonGroup
      className="[&>*:not(:first-child)]:rounded-l-md [&>*:not(:last-child)]:rounded-r-md"
      orientation="horizontal"
      {...props}
    />
  )
}

export type MessageBranchPreviousProps = ComponentProps<typeof Button>

export const MessageBranchPrevious = ({ children, ...props }: MessageBranchPreviousProps) => {
  const { goToPrevious, totalBranches } = useMessageBranch()

  return (
    <Button
      aria-label="Previous branch"
      disabled={totalBranches <= 1}
      onClick={goToPrevious}
      size="icon-sm"
      type="button"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronLeftIcon size={14} />}
    </Button>
  )
}

export type MessageBranchNextProps = ComponentProps<typeof Button>

export const MessageBranchNext = ({
  children,
  className: _className,
  ...props
}: MessageBranchNextProps) => {
  const { goToNext, totalBranches } = useMessageBranch()

  return (
    <Button
      aria-label="Next branch"
      disabled={totalBranches <= 1}
      onClick={goToNext}
      size="icon-sm"
      type="button"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronRightIcon size={14} />}
    </Button>
  )
}

export type MessageBranchPageProps = HTMLAttributes<HTMLSpanElement>

export const MessageBranchPage = ({ className, ...props }: MessageBranchPageProps) => {
  const { currentBranch, totalBranches } = useMessageBranch()

  return (
    <ButtonGroupText
      className={cn('border-none bg-transparent text-muted-foreground shadow-none', className)}
      {...props}
    >
      {currentBranch + 1} of {totalBranches}
    </ButtonGroupText>
  )
}

const compareCells = (a: string, b: string): number => {
  const aNum = Number(a.replace(/,/g, ''))
  const bNum = Number(b.replace(/,/g, ''))
  if (a !== '' && b !== '' && !Number.isNaN(aNum) && !Number.isNaN(bNum)) {
    return aNum - bNum
  }
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
}

const SORT_INDICATOR_CLASS = 'streamdown-sort-indicator'

const setHeaderIndicator = (th: HTMLTableCellElement, direction: 'asc' | 'desc' | null) => {
  th.querySelector(`.${SORT_INDICATOR_CLASS}`)?.remove()
  if (!direction) {
    th.removeAttribute('aria-sort')
    return
  }
  th.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : 'descending')
  const indicator = document.createElement('span')
  indicator.className = SORT_INDICATOR_CLASS
  indicator.setAttribute('aria-hidden', 'true')
  indicator.textContent = direction === 'asc' ? ' ▲' : ' ▼'
  th.appendChild(indicator)
}

const sortTable = (table: HTMLTableElement, th: HTMLTableCellElement) => {
  const headerRow = th.parentElement
  if (!headerRow) return
  const headers = Array.from(headerRow.children) as HTMLTableCellElement[]
  const colIndex = headers.indexOf(th)
  if (colIndex < 0) return

  const tbody = table.tBodies[0] as HTMLTableSectionElement | undefined
  if (!tbody) return

  // Cycle: none -> asc -> desc -> none, scoped to this table.
  const current = th.getAttribute('aria-sort')
  let nextDirection: 'asc' | 'desc' | null
  if (current === 'ascending') nextDirection = 'desc'
  else if (current === 'descending') nextDirection = null
  else nextDirection = 'asc'

  for (const h of headers) setHeaderIndicator(h, null)

  if (!nextDirection) {
    // Restore original order using stored row indices.
    const rows = Array.from(tbody.rows)
    rows.sort((a, b) => {
      const ai = Number(a.dataset.streamdownOriginalIndex ?? '0')
      const bi = Number(b.dataset.streamdownOriginalIndex ?? '0')
      return ai - bi
    })
    for (const row of rows) tbody.appendChild(row)
    return
  }

  setHeaderIndicator(th, nextDirection)
  const rows = Array.from(tbody.rows)
  // Remember original order on first sort.
  rows.forEach((row, i) => {
    row.dataset.streamdownOriginalIndex ??= String(i)
  })
  rows.sort((a, b) => {
    const aText = (a.cells[colIndex].textContent ?? '').trim()
    const bText = (b.cells[colIndex].textContent ?? '').trim()
    const cmp = compareCells(aText, bText)
    return nextDirection === 'asc' ? cmp : -cmp
  })
  for (const row of rows) tbody.appendChild(row)
}

const useSortableTables = (root: HTMLElement | null) => {
  useEffect(() => {
    if (!root) return
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      const th = target?.closest('th')
      if (!th) return
      const table = th.closest('table')
      if (!table || !root.contains(table)) return
      // Only treat the first thead row as sort headers.
      const headerRow = table.tHead?.rows[0]
      if (!headerRow || th.parentElement !== headerRow) return
      sortTable(table, th)
    }
    root.addEventListener('click', handleClick)
    return () => root.removeEventListener('click', handleClick)
  }, [root])
}

export type MessageResponseProps = ComponentProps<typeof Streamdown>

export const MessageResponse = memo(
  ({ className, ...props }: MessageResponseProps) => {
    const [rootEl, setRootEl] = useState<HTMLDivElement | null>(null)
    useSortableTables(rootEl)
    return (
      <div
        ref={setRootEl}
        className={cn(
          'size-full [&_table_thead_th]:cursor-pointer [&_table_thead_th]:select-none',
          '[&_table_thead_th:hover]:bg-surface-container',
          className
        )}
      >
        <Streamdown
          className={cn(
            '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
            '[&_h1]:mt-6 [&_h1]:mb-3 [&_h1]:font-semibold [&_h1]:text-xl',
            '[&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:font-semibold [&_h2]:text-lg',
            '[&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:font-semibold [&_h3]:text-base',
            '[&_h4]:mt-3 [&_h4]:mb-1.5 [&_h4]:font-semibold',
            '[&_p]:my-3 [&_p]:leading-relaxed',
            '[&_ul]:my-3 [&_ul]:pl-6 [&_ul]:list-disc [&_ul]:space-y-1',
            '[&_ol]:my-3 [&_ol]:pl-6 [&_ol]:list-decimal [&_ol]:space-y-1',
            '[&_li]:leading-relaxed [&_li>p]:my-0',
            '[&_blockquote]:my-3 [&_blockquote]:border-l-2 [&_blockquote]:border-muted [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground',
            '[&_hr]:my-6 [&_hr]:border-border',
            '[&_table]:my-3',
            '[&_pre]:my-3',
            '[&_code:not(pre>code)]:rounded [&_code:not(pre>code)]:bg-muted [&_code:not(pre>code)]:px-1.5 [&_code:not(pre>code)]:py-0.5 [&_code:not(pre>code)]:text-[0.9em]',
            '[&_a]:underline [&_a]:underline-offset-2 [&_a:hover]:text-primary'
          )}
          plugins={{ code, mermaid, math, cjk }}
          {...props}
        />
      </div>
    )
  },
  (prevProps, nextProps) => prevProps.children === nextProps.children
)

MessageResponse.displayName = 'MessageResponse'

export type MessageToolbarProps = ComponentProps<'div'>

export const MessageToolbar = ({ className, children, ...props }: MessageToolbarProps) => (
  <div className={cn('mt-4 flex w-full items-center justify-between gap-4', className)} {...props}>
    {children}
  </div>
)
