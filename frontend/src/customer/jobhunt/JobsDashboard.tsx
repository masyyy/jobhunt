import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Briefcase,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  MapPin,
  PenLine,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { queryKeys, fetchJobs, updateJobStatus, draftJobApplication } from '@/lib/queries'
import type { Job, JobApplication, JobCategory, JobFilters, JobStatus } from '@/lib/queries'
import { cn, formatRelativeTime } from '@/lib/utils'

const CATEGORY_LABEL: Record<JobCategory, string> = {
  retail: 'Retail',
  craft: 'Crafts',
  bookstore: 'Bookstore',
  library: 'Library',
  museum: 'Museum',
  culture: 'Culture',
  other: 'Other',
}

const CATEGORY_STYLES: Record<JobCategory, string> = {
  retail: 'bg-blue-500/15 text-blue-400',
  craft: 'bg-pink-500/15 text-pink-400',
  bookstore: 'bg-amber-500/15 text-amber-400',
  library: 'bg-emerald-500/15 text-emerald-400',
  museum: 'bg-purple-500/15 text-purple-400',
  culture: 'bg-rose-500/15 text-rose-400',
  other: 'bg-muted text-muted-foreground',
}

const SOURCE_LABEL: Record<string, string> = {
  duunitori: 'Duunitori',
  tyomarkkinatori: 'Job Market FI',
  kuntarekry: 'Kuntarekry',
}

const STATUS_OPTIONS: { value: JobStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'applied', label: 'Applied' },
  { value: 'dismissed', label: 'Dismissed' },
]

const CATEGORY_FILTERS: { value: JobCategory | 'all'; label: string }[] = [
  { value: 'all', label: 'All categories' },
  ...(['retail', 'craft', 'bookstore', 'library', 'museum', 'culture'] as JobCategory[]).map(
    (c) => ({ value: c, label: CATEGORY_LABEL[c] })
  ),
]

export function JobsDashboard() {
  const queryClient = useQueryClient()
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<JobCategory | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<JobStatus | 'all'>('all')

  const filters: JobFilters = useMemo(
    () => ({
      ...(category !== 'all' ? { category } : {}),
      ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
      ...(search ? { search } : {}),
    }),
    [category, statusFilter, search]
  )

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: queryKeys.jobs(filters),
    queryFn: () => fetchJobs(filters),
    staleTime: 60 * 1000,
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: JobStatus }) => updateJobStatus(id, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const stats = useMemo(() => {
    const byCategory = new Map<JobCategory, number>()
    let applied = 0
    for (const j of jobs) {
      byCategory.set(j.category, (byCategory.get(j.category) ?? 0) + 1)
      if (j.status === 'applied') applied += 1
    }
    const sorted = [...byCategory.entries()].sort((a, b) => b[1] - a[1])
    const top = sorted.length > 0 ? sorted[0] : null
    return {
      total: jobs.length,
      applied,
      topCategoryLabel: top ? CATEGORY_LABEL[top[0]] : '—',
      topCategorySub: top ? `${top[1]} jobs` : undefined,
    }
  }, [jobs])

  function submitSearch(e: React.FormEvent) {
    e.preventDefault()
    setSearch(searchInput.trim())
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-gradient-to-b from-secondary/50 via-background to-background">
      <div className="px-4 md:px-8 pt-6 pb-4">
        <h1 className="font-headline text-xl md:text-3xl font-bold tracking-tight mb-6">
          <span className="bg-gradient-to-r from-primary via-chart-5 to-sidebar-primary bg-clip-text text-transparent">
            Job Matches
          </span>
        </h1>

        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard label="Matching Jobs" value={stats.total} icon={Briefcase} tint="sun" />
          <StatCard label="Applied" value={stats.applied} icon={Sparkles} tint="rose" />
          <StatCard
            label="Top Category"
            value={stats.topCategoryLabel}
            sub={stats.topCategorySub}
            icon={MapPin}
            tint="sea"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <form onSubmit={submitSearch} className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search title, employer, description…"
              className="pl-9"
            />
          </form>
          <Select value={category} onValueChange={(v) => setCategory(v as JobCategory | 'all')}>
            <SelectTrigger className="w-full sm:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORY_FILTERS.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as JobStatus | 'all')}
          >
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Job feed */}
      <main className="flex-1 overflow-y-auto px-4 md:px-8 pb-8">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={`s-${i}`} className="h-28 w-full rounded-md" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="rounded-md bg-surface-container p-4 mb-4">
              <Briefcase className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              No jobs yet. The scraper runs every few hours — check back soon.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onStatusChange={(status) => statusMutation.mutate({ id: job.id, status })}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

const STAT_TINTS = {
  sun: 'from-amber-400/25 to-orange-500/10 ring-amber-500/20 text-amber-500',
  rose: 'from-pink-400/25 to-rose-500/10 ring-rose-500/20 text-rose-500',
  sea: 'from-cyan-400/25 to-teal-500/10 ring-teal-500/20 text-teal-500',
} as const

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  tint,
}: {
  label: string
  value: number | string
  sub?: string
  icon: React.ComponentType<{ className?: string }>
  tint: keyof typeof STAT_TINTS
}) {
  const tintClass = STAT_TINTS[tint]
  return (
    <div
      className={cn(
        'rounded-2xl p-5 flex items-center justify-between bg-gradient-to-br ring-1 shadow-sm',
        tintClass
      )}
    >
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-widest text-foreground/60 mb-1">
          {label}
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-headline text-2xl sm:text-4xl font-bold tabular-nums text-foreground">
            {value}
          </span>
          {sub && <span className="text-[11px] text-foreground/60">{sub}</span>}
        </div>
      </div>
      <Icon className={cn('h-8 w-8 opacity-70', tintClass)} />
    </div>
  )
}

function JobCard({
  job,
  onStatusChange,
}: {
  job: Job
  onStatusChange: (status: JobStatus) => void
}) {
  const [applyOpen, setApplyOpen] = useState(false)
  return (
    <div
      className={cn(
        'group rounded-md border border-outline-variant bg-surface-container-low/40 p-4 transition-colors hover:bg-surface-container-low',
        job.status === 'dismissed' && 'opacity-50'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <Badge className={cn('rounded-sm', CATEGORY_STYLES[job.category])}>
              {CATEGORY_LABEL[job.category]}
            </Badge>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {SOURCE_LABEL[job.source] ?? job.source}
            </span>
            {job.posted_at && (
              <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                {formatRelativeTime(job.posted_at)}
              </span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-foreground truncate">{job.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {job.employer && <span>{job.employer}</span>}
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {job.location}
              </span>
            )}
          </div>
          {job.match_reason && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground/90">
              <Sparkles className="h-3 w-3 mt-0.5 shrink-0 text-amber-400" />
              <span className="italic">{job.match_reason}</span>
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={() => setApplyOpen(true)}
          >
            <PenLine className="h-3 w-3 mr-1" />
            Apply
          </Button>
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            <Button size="sm" variant="outline" className="h-7 text-xs">
              View
              <ExternalLink className="h-3 w-3 ml-1" />
            </Button>
          </a>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-1.5">
        {STATUS_OPTIONS.map((s) => (
          <Button
            key={s.value}
            size="sm"
            variant={job.status === s.value ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px] font-semibold uppercase tracking-wider"
            onClick={() => onStatusChange(s.value)}
          >
            {s.label}
          </Button>
        ))}
      </div>

      <ApplyDialog job={job} open={applyOpen} onOpenChange={setApplyOpen} />
    </div>
  )
}

function ApplyDialog({
  job,
  open,
  onOpenChange,
}: {
  job: Job
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<JobApplication | null>(null)
  const [letter, setLetter] = useState('')
  const [copied, setCopied] = useState(false)

  const mutation = useMutation({
    mutationFn: (regenerate: boolean) => draftJobApplication(job.id, regenerate),
    onSuccess: (data) => {
      setDraft(data)
      setLetter(data.cover_letter)
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const { mutate } = mutation
  const isPending = mutation.isPending

  // Generate (or load the saved draft) the first time the dialog opens. This
  // runs on the actual open transition, not just Radix's onOpenChange (which
  // doesn't fire when the parent flips `open` directly via the Apply button).
  useEffect(() => {
    if (open && draft === null && !isPending) {
      mutate(false)
    }
  }, [open, draft, isPending, mutate])

  async function copyLetter() {
    await navigator.clipboard.writeText(letter)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="text-base">Apply: {job.title}</DialogTitle>
          <DialogDescription>
            {job.employer ?? 'Unknown employer'}
            {job.location ? ` · ${job.location}` : ''}
          </DialogDescription>
        </DialogHeader>

        {mutation.isPending && draft === null ? (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Drafting your application…
          </div>
        ) : mutation.isError ? (
          <div className="py-10 text-center text-sm text-destructive">
            Could not draft the application. Try again.
            <div className="mt-3">
              <Button size="sm" variant="outline" onClick={() => mutation.mutate(false)}>
                Retry
              </Button>
            </div>
          </div>
        ) : draft ? (
          <div className="space-y-4">
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Cover letter
                </h4>
                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    onClick={() => void copyLetter()}
                  >
                    {copied ? (
                      <Check className="h-3 w-3 mr-1 text-emerald-500" />
                    ) : (
                      <Copy className="h-3 w-3 mr-1" />
                    )}
                    {copied ? 'Copied' : 'Copy'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate(true)}
                  >
                    <RefreshCw className={cn('h-3 w-3 mr-1', mutation.isPending && 'animate-spin')} />
                    Regenerate
                  </Button>
                </div>
              </div>
              <Textarea
                value={letter}
                onChange={(e) => setLetter(e.target.value)}
                className="min-h-[440px] text-sm leading-relaxed"
              />
            </section>

            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                How to apply
              </h4>
              <p className="whitespace-pre-line rounded-md bg-surface-container-low p-3 text-sm text-muted-foreground">
                {draft.how_to_apply}
              </p>
              <a href={job.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block">
                <Button size="sm" variant="outline" className="h-7 text-xs">
                  Open posting
                  <ExternalLink className="h-3 w-3 ml-1" />
                </Button>
              </a>
            </section>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
