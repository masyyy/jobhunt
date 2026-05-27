import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Radio, AlertTriangle, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/use-auth'
import {
  queryKeys,
  fetchTaskOutputs,
  updateTaskOutputState,
  createConversation,
} from '@/lib/queries'
import type { TaskOutput, SignalPayload, SignalSeverity, SignalState } from '@/lib/queries'
import { cn, formatRelativeTime } from '@/lib/utils'

const TASK_NAME = 'generate-signals'

const SEVERITY_LABEL: Record<SignalSeverity, string> = {
  high: 'Critical',
  medium: 'Warning',
  low: 'Optimization',
}

const SEVERITY_CHIP_STYLES: Record<SignalSeverity, string> = {
  high: 'bg-destructive/20 text-red-400',
  medium: 'bg-amber-500/15 text-amber-400',
  low: 'bg-tertiary/15 text-tertiary',
}

const SEVERITY_BAR: Record<SignalSeverity, string> = {
  high: 'bg-destructive',
  medium: 'bg-primary-container',
  low: 'bg-tertiary',
}

const STATE_LABELS: Record<SignalState, string> = {
  active: 'Active',
  acted_on: 'Acted on',
  dismissed: 'Dismissed',
  expired: 'Expired',
}

interface SignalsDashboardProps {
  toolbox: string
}

type SignalOutput = TaskOutput & { payload: SignalPayload }

function asSignal(output: TaskOutput): SignalOutput {
  return output as SignalOutput
}

export default function SignalsDashboard({ toolbox }: SignalsDashboardProps) {
  const [showArchive, setShowArchive] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { effectiveRole } = useAuth()
  const canMutate = effectiveRole === 'admin'

  const { data: outputs = [], isLoading } = useQuery({
    queryKey: queryKeys.taskOutputs(TASK_NAME, toolbox),
    queryFn: () => fetchTaskOutputs(TASK_NAME, toolbox),
    staleTime: 2 * 60 * 1000,
  })

  const updateStateMutation = useMutation({
    mutationFn: ({ id, state }: { id: string; state: SignalState }) =>
      updateTaskOutputState(id, state),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.taskOutputs(TASK_NAME, toolbox) })
    },
  })

  const signals: SignalOutput[] = outputs.map(asSignal)
  const activeSignals = signals.filter((s) => s.payload.state === 'active')
  const archivedSignals = signals.filter((s) => s.payload.state !== 'active')
  const displayedSignals = showArchive ? archivedSignals : activeSignals
  const countPool = showArchive ? archivedSignals : activeSignals
  const criticalCount = countPool.filter((s) => s.payload.severity === 'high').length
  const anomalyCount = countPool.filter((s) => s.payload.severity === 'medium').length

  const statCardCopy = showArchive
    ? {
        total: { label: 'Archived Signals', sublabel: null },
        critical: { label: 'Resolved Critical', sublabel: 'Archived' },
        anomaly: { label: 'Resolved Anomalies', sublabel: 'Archived' },
      }
    : {
        total: { label: 'Active Signals', sublabel: null },
        critical: { label: 'Critical Faults', sublabel: 'Unresolved' },
        anomaly: { label: 'Anomalies Detected', sublabel: 'Pending' },
      }

  async function handleAnalyze(output: SignalOutput) {
    const { conversation_id } = await createConversation(toolbox)
    void navigate(`/${toolbox}/chat`, {
      state: { conversationId: conversation_id, initialPrompt: output.payload.prompt },
    })
  }

  function setState(output: SignalOutput, state: SignalState) {
    updateStateMutation.mutate({ id: output.id, state })
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
      {/* Operational Overview */}
      <div className="px-4 md:px-8 pt-6 pb-4">
        <h1 className="font-headline text-xl md:text-3xl font-bold tracking-tight mb-6">
          Operational Overview
        </h1>

        {/* Stats row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
          {/* Total (active or archived) */}
          <div className="bg-surface-container-low rounded-[0.25rem] p-5 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                {statCardCopy.total.label}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-headline text-2xl sm:text-4xl font-bold tabular-nums">
                  {countPool.length.toLocaleString()}
                </span>
              </div>
            </div>
            <Radio className="h-8 w-8 text-muted-foreground/30" />
          </div>

          {/* Critical */}
          <div className="bg-surface-container-low rounded-[0.25rem] p-5 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                {statCardCopy.critical.label}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-headline text-2xl sm:text-4xl font-bold tabular-nums text-destructive">
                  {String(criticalCount).padStart(2, '0')}
                </span>
                {statCardCopy.critical.sublabel && (
                  <span className="text-[10px] text-destructive/80 uppercase tracking-wider">
                    {statCardCopy.critical.sublabel}
                  </span>
                )}
              </div>
            </div>
            <AlertTriangle className="h-8 w-8 text-destructive/20" />
          </div>

          {/* Anomalies */}
          <div className="bg-surface-container-low rounded-[0.25rem] p-5 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                {statCardCopy.anomaly.label}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-headline text-2xl sm:text-4xl font-bold tabular-nums">
                  {anomalyCount}
                </span>
                {statCardCopy.anomaly.sublabel && (
                  <span className="text-[10px] text-primary/80 uppercase tracking-wider">
                    {statCardCopy.anomaly.sublabel}
                  </span>
                )}
              </div>
            </div>
            <Activity className="h-8 w-8 text-muted-foreground/30" />
          </div>
        </div>

        {/* Section header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-headline text-lg font-bold tracking-tight uppercase">
            {showArchive ? 'Archive' : 'Signals'}
          </h2>
          <button
            onClick={() => setShowArchive(!showArchive)}
            className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            {showArchive ? (
              <>
                <ArrowLeft className="h-3 w-3" />
                Back to Signals
              </>
            ) : (
              <>
                View Archive
                <ArrowRight className="h-3 w-3" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Signal feed */}
      <main className="flex-1 overflow-y-auto px-4 md:px-8 pb-8">
        <div className="space-y-0">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={`skeleton-${i}`} className="h-24 w-full rounded-[0.25rem] mb-px" />
            ))
          ) : displayedSignals.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="rounded-[0.25rem] bg-surface-container p-4 mb-4">
                <Radio className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">
                {showArchive ? 'No archived signals.' : 'No active signals.'}
              </p>
            </div>
          ) : (
            displayedSignals.map((signal, idx) => (
              <div
                key={signal.id}
                className={cn(
                  'group relative flex flex-col sm:flex-row items-start gap-2 sm:gap-4 py-5 px-4 transition-colors hover:bg-surface-container-low/50',
                  idx !== displayedSignals.length - 1 && 'border-b border-outline-variant',
                  showArchive && 'opacity-75'
                )}
              >
                {/* Left severity bar */}
                <div
                  className={cn(
                    'absolute left-0 top-4 bottom-4 w-[3px] rounded-full',
                    SEVERITY_BAR[signal.payload.severity]
                  )}
                />

                {/* Timestamp */}
                <div className="hidden sm:block flex-shrink-0 w-16 pt-0.5">
                  <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                    {formatRelativeTime(signal.created_at)}
                  </span>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    {/* Severity chip */}
                    <span
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-[0.125rem] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                        SEVERITY_CHIP_STYLES[signal.payload.severity]
                      )}
                    >
                      <span
                        className={cn(
                          'h-1 w-1 rounded-full',
                          signal.payload.severity === 'high'
                            ? 'bg-destructive'
                            : signal.payload.severity === 'medium'
                              ? 'bg-primary-container'
                              : 'bg-tertiary'
                        )}
                      />
                      {SEVERITY_LABEL[signal.payload.severity]}
                    </span>
                    {showArchive && (
                      <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                        {STATE_LABELS[signal.payload.state]}
                      </span>
                    )}
                  </div>

                  <h3 className="text-sm font-semibold mb-1 text-foreground">
                    {signal.payload.title}
                  </h3>
                  <p className="text-sm text-muted-foreground line-clamp-1">
                    {signal.payload.prompt}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 flex items-center gap-2 pt-1">
                  {canMutate &&
                    (showArchive ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                        onClick={() => setState(signal, 'active')}
                      >
                        Restore
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                        onClick={() => setState(signal, 'dismissed')}
                      >
                        Dismiss
                      </Button>
                    ))}
                  <Button
                    size="sm"
                    variant={showArchive ? 'outline' : 'default'}
                    className="h-7 text-[10px] font-semibold uppercase tracking-wider"
                    onClick={() => handleAnalyze(signal)}
                  >
                    {showArchive ? 'Details' : 'Analyze'}
                    <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  )
}
