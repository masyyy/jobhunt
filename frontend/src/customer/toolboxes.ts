import type { ComponentType } from 'react'
import { Factory, TrendingUp } from 'lucide-react'
import { SalesChat } from './sales/SalesChat'
import { SalesSignals } from './sales/SalesSignals'
import { ProductionChat } from './production/ProductionChat'
import { ProductionSignals } from './production/ProductionSignals'

export const Toolbox = {
  Sales: 'sales',
  Production: 'production',
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
    id: Toolbox.Sales,
    label: 'Sales',
    icon: TrendingUp,
    description: 'Sales operations and account management',
    views: [
      { id: 'chat', label: 'Chat', component: SalesChat },
      { id: 'signals', label: 'Signals', component: SalesSignals },
    ],
  },
  {
    id: Toolbox.Production,
    label: 'Production',
    icon: Factory,
    description: 'Production monitoring and efficiency',
    views: [
      { id: 'chat', label: 'Chat', component: ProductionChat },
      { id: 'signals', label: 'Signals', component: ProductionSignals },
    ],
  },
]

export function getToolboxConfig(toolboxId: string): ToolboxConfig | undefined {
  return toolboxes.find((t) => t.id === toolboxId)
}

export function getDefaultToolbox(): ToolboxConfig {
  return toolboxes[0]
}
