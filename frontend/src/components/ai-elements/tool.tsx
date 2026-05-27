'use client'

import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { DynamicToolUIPart, ToolUIPart } from 'ai'
import {
  CheckCircleIcon,
  ChevronDownIcon,
  CircleIcon,
  ClockIcon,
  WrenchIcon,
  XCircleIcon,
} from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'
import { isValidElement } from 'react'
import { CodeBlock } from './code-block'

export type ToolProps = ComponentProps<typeof Collapsible>

export const Tool = ({ className, ...props }: ToolProps) => (
  <Collapsible
    className={cn(
      'group not-prose mb-1.5 w-full rounded-[0.25rem] bg-surface-container-low',
      className
    )}
    {...props}
  />
)

export type ToolPart = ToolUIPart | DynamicToolUIPart

export type ToolHeaderProps = {
  title?: string
  className?: string
} & (
  | { type: ToolUIPart['type']; state: ToolUIPart['state']; toolName?: never }
  | {
      type: DynamicToolUIPart['type']
      state: DynamicToolUIPart['state']
      toolName: string
    }
)

const TOOL_LABELS: Record<string, string> = {
  execute_sql: 'Querying data',
  read_file: 'Reading file',
  list_files: 'Listing files',
  search_files: 'Searching files',
}

export const getToolLabel = (name: string): string => TOOL_LABELS[name] ?? name

export const getStatusBadge = (status: ToolPart['state']) => {
  const labels: Record<ToolPart['state'], string> = {
    'input-streaming': 'Pending',
    'input-available': 'Running',
    'approval-requested': 'Awaiting Approval',
    'approval-responded': 'Responded',
    'output-available': 'Completed',
    'output-error': 'Error',
    'output-denied': 'Denied',
  }

  const icons: Record<ToolPart['state'], ReactNode> = {
    'input-streaming': <CircleIcon className="size-4" />,
    'input-available': <ClockIcon className="size-4 animate-pulse" />,
    'approval-requested': <ClockIcon className="size-4 text-yellow-600" />,
    'approval-responded': <CheckCircleIcon className="size-4 text-blue-600" />,
    'output-available': <CheckCircleIcon className="size-4 text-green-600" />,
    'output-error': <XCircleIcon className="size-4 text-red-600" />,
    'output-denied': <XCircleIcon className="size-4 text-orange-600" />,
  }

  return (
    <Badge className="gap-1.5 rounded-full text-xs" variant="secondary">
      {icons[status]}
      {labels[status]}
    </Badge>
  )
}

export const ToolHeader = ({
  className,
  title,
  type,
  state,
  toolName,
  ...props
}: ToolHeaderProps) => {
  const derivedName = type === 'dynamic-tool' ? toolName : type.split('-').slice(1).join('-')
  const displayName = getToolLabel(title ?? derivedName)

  return (
    <CollapsibleTrigger
      className={cn('flex w-full items-center justify-between gap-4 p-3', className)}
      {...props}
    >
      <div className="flex items-center gap-2">
        <WrenchIcon className="size-4 text-muted-foreground" />
        <span className="font-medium text-sm">{displayName}</span>
        {getStatusBadge(state)}
      </div>
      <ChevronDownIcon className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
    </CollapsibleTrigger>
  )
}

export type ToolContentProps = ComponentProps<typeof CollapsibleContent>

export const ToolContent = ({ className, ...props }: ToolContentProps) => (
  <CollapsibleContent
    className={cn(
      'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 text-popover-foreground outline-none data-[state=closed]:animate-out data-[state=open]:animate-in',
      className
    )}
    {...props}
  />
)

export type ToolInputProps = ComponentProps<'div'> & {
  input: ToolPart['input']
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

// On reload, persisted history serializes tool input as a JSON string
// (PydanticAI's VercelAIAdapter uses args_as_json_str). Live streaming
// delivers it as a parsed object. Normalize to an object so rendering matches.
const normalizeInput = (input: ToolPart['input']): unknown => {
  if (typeof input !== 'string') return input
  const trimmed = input.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return input
  try {
    return JSON.parse(trimmed)
  } catch {
    return input
  }
}

const renderInputBody = (input: ToolPart['input']) => {
  const normalized = normalizeInput(input)
  if (isPlainObject(normalized) && typeof normalized.sql === 'string') {
    const { sql, ...rest } = normalized
    const hasRest = Object.keys(rest).length > 0
    return (
      <div className="space-y-2">
        <CodeBlock code={sql} language="sql" />
        {hasRest && <CodeBlock code={JSON.stringify(rest, null, 2)} language="json" />}
      </div>
    )
  }

  return <CodeBlock code={JSON.stringify(normalized ?? {}, null, 2)} language="json" />
}

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => (
  <div className={cn('space-y-2 overflow-hidden p-4', className)} {...props}>
    <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
      Parameters
    </h4>
    <div className="rounded-md bg-muted/50">{renderInputBody(input)}</div>
  </div>
)

export type ToolOutputProps = ComponentProps<'div'> & {
  output: ToolPart['output']
  errorText: ToolPart['errorText']
}

export const ToolOutput = ({ className, output, errorText, ...props }: ToolOutputProps) => {
  if (!(output || errorText)) {
    return null
  }

  let Output = <div>{output as ReactNode}</div>

  if (output === undefined || output === null) {
    // Handle undefined/null output
    Output = <CodeBlock code="{}" language="json" />
  } else if (typeof output === 'object' && !isValidElement(output)) {
    Output = <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />
  } else if (typeof output === 'string') {
    const trimmed = output.trim()
    const looksLikeJson = trimmed.startsWith('{') || trimmed.startsWith('[')
    if (looksLikeJson) {
      try {
        const parsed: unknown = JSON.parse(trimmed)
        Output = <CodeBlock code={JSON.stringify(parsed, null, 2)} language="json" />
      } catch {
        Output = <CodeBlock code={output} language="markdown" />
      }
    } else {
      Output = <CodeBlock code={output} language="markdown" />
    }
  }

  return (
    <div className={cn('space-y-2 p-4', className)} {...props}>
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {errorText ? 'Error' : 'Result'}
      </h4>
      <div
        className={cn(
          'overflow-x-auto rounded-md text-xs [&_table]:w-full',
          errorText ? 'bg-destructive/10 text-destructive' : 'bg-muted/50 text-foreground'
        )}
      >
        {errorText && <div>{errorText}</div>}
        {Output}
      </div>
    </div>
  )
}
