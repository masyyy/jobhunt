import type { ComponentType } from 'react'
import { Briefcase } from 'lucide-react'
import { JobsDashboard } from './jobhunt/JobsDashboard'

export const Toolbox = {
  Jobhunt: 'jobhunt',
} as const

export type Toolbox = (typeof Toolbox)[keyof typeof Toolbox]

export interface ToolboxView {
  id: string
  label: string
  component: ComponentType
}

export interface ToolboxConfig {
  id: Toolbox
  label: string
  icon: ComponentType<{ className?: string }>
  description: string
  views: ToolboxView[]
  /** Whether to show this toolbox in the sidebar. Defaults to true. */
  visible_in_sidebar?: boolean
}

export const toolboxes: ToolboxConfig[] = [
  {
    id: Toolbox.Jobhunt,
    label: 'Job Hunt',
    icon: Briefcase,
    description: 'Finnish retail, craft, library, museum & culture jobs',
    views: [{ id: 'jobs', label: 'Jobs', component: JobsDashboard }],
  },
]

export function getToolboxConfig(toolboxId: string): ToolboxConfig | undefined {
  return toolboxes.find((t) => t.id === toolboxId)
}

export function getDefaultToolbox(): ToolboxConfig {
  return toolboxes[0]
}
