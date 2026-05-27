import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-[0.25rem] bg-surface-container', className)}
      {...props}
    />
  )
}

export { Skeleton }
