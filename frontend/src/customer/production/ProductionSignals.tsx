import SignalsDashboard from '@/pages/SignalsDashboard'
import { Toolbox } from '../toolboxes'

export function ProductionSignals() {
  return <SignalsDashboard toolbox={Toolbox.Production} />
}
