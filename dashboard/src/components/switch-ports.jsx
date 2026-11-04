import { EthernetPort } from 'lucide-react'

import { StatusIcon, statusMeta } from '@/components/status-badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ms, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

const RING = {
  ok: 'border-status-good/50',
  degraded: 'border-status-warning/60',
  no_internet: 'border-status-serious/60',
  disconnected: 'border-status-critical/70 bg-status-critical/5',
}

function Port({ port, vlanName }) {
  const meta = statusMeta(port.status)
  const dev = port.device_info
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            'bg-background/40 hover:bg-accent/50 flex flex-col gap-2 rounded-lg border-2 p-3 text-left transition-colors',
            RING[port.status] || 'border-dashed',
          )}
        >
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground font-mono text-xs">PORT {port.port}</span>
            <EthernetPort className="text-muted-foreground size-4" aria-hidden />
          </div>
          <div className="line-clamp-2 min-h-10 text-sm font-medium leading-5">{port.label}</div>
          <div className="text-muted-foreground text-xs">
            VLAN {port.vlan}
            {vlanName ? ` · ${vlanName}` : ''}
          </div>
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <StatusIcon status={port.status} className="size-3.5" />
            {meta.label}
          </div>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-64">
        <div className="font-medium">{port.reason}</div>
        {dev && (
          <div className="opacity-80">
            {dev.name} · {dev.ip} · {ms(dev.rtt_ms)} · seen {timeAgo(dev.last_seen_ts)}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

export function SwitchPorts({ sw, vlans }) {
  const names = Object.fromEntries(vlans.map((v) => [v.id, v.name]))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Switch ports</CardTitle>
        <CardDescription>
          {sw.name || 'Switch'} · each port reflects the device mapped to it in config.json
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          {sw.ports.map((p) => (
            <Port key={p.port} port={p} vlanName={names[p.vlan]} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
