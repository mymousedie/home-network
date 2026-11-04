import {
  CircleCheck,
  CircleHelp,
  CircleX,
  Minus,
  TriangleAlert,
  Unplug,
  WifiOff,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Status colors are reserved for state and always ship with an icon + label,
// so meaning never rides on color alone.
const STATUS = {
  online: { label: 'Online', icon: CircleCheck, tone: 'text-status-good' },
  ok: { label: 'OK', icon: CircleCheck, tone: 'text-status-good' },
  degraded: { label: 'Degraded', icon: TriangleAlert, tone: 'text-status-warning' },
  no_internet: { label: 'No internet', icon: WifiOff, tone: 'text-status-serious' },
  offline: { label: 'Offline', icon: CircleX, tone: 'text-status-critical' },
  disconnected: { label: 'Disconnected', icon: Unplug, tone: 'text-status-critical' },
  down: { label: 'Down', icon: CircleX, tone: 'text-status-critical' },
  unknown: { label: 'Unknown', icon: CircleHelp, tone: 'text-muted-foreground' },
  unmonitored: { label: 'Not monitored', icon: Minus, tone: 'text-muted-foreground' },
}

export function statusMeta(status) {
  return STATUS[status] || STATUS.unknown
}

export function StatusIcon({ status, className }) {
  const { icon: Icon, tone } = statusMeta(status)
  return <Icon className={cn('size-4 shrink-0', tone, className)} aria-hidden />
}

export function StatusBadge({ status, className }) {
  const { label, icon: Icon, tone } = statusMeta(status)
  return (
    <Badge variant="outline" className={cn('gap-1.5', className)}>
      <Icon className={tone} aria-hidden />
      {label}
    </Badge>
  )
}
