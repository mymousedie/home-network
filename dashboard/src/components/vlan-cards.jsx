import { ShieldBan, ShieldCheck } from 'lucide-react'

import { StatusBadge, StatusIcon } from '@/components/status-badge'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ms, num, pct, timeAgo } from '@/lib/format'

function DeviceRow({ d }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <li className="hover:bg-accent/50 flex items-center gap-3 rounded-md px-2 py-1.5">
          <StatusIcon status={d.status} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{d.name}</div>
            <div className="text-muted-foreground font-mono text-xs">{d.ip}</div>
          </div>
          <div className="text-right text-xs tabular-nums">
            <div>{d.status === 'offline' ? 'no reply' : ms(d.rtt_ms)}</div>
            <div className="text-muted-foreground">{pct(d.loss_pct)} loss</div>
          </div>
        </li>
      </TooltipTrigger>
      <TooltipContent side="left">
        <div className="font-medium">{d.reason}</div>
        <div className="opacity-80">
          last reply {timeAgo(d.last_seen_ts)} · avg {ms(d.avg_rtt_ms)}
          {!d.alerts_enabled && ' · alerts off'}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

export function VlanCards({ vlans }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {vlans.map((v) => (
        <Card key={v.id ?? 'none'} className="gap-4">
          <CardHeader>
            <CardTitle>
              {v.name} <span className="text-muted-foreground font-normal">· VLAN {v.id ?? '–'}</span>
            </CardTitle>
            <CardDescription className="font-mono text-xs">
              {v.subnet || 'no subnet'}
              {v.iface ? ` · ${v.iface}` : ''}
            </CardDescription>
            <CardAction>
              <StatusBadge status={v.status} />
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            {v.devices.length ? (
              <ul className="-mx-2 flex flex-col gap-0.5">
                {v.devices.map((d) => (
                  <DeviceRow key={d.id} d={d} />
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">No monitored devices. Add one to config.json.</p>
            )}
            {v.iface && (
              <div className="text-muted-foreground mt-auto flex gap-4 border-t pt-3 text-xs">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck className="size-3.5" aria-hidden /> {num(v.firewall.pass)} passed
                </span>
                <span className="flex items-center gap-1.5">
                  <ShieldBan className="size-3.5" aria-hidden /> {num(v.firewall.block)} blocked
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
