import { BellRing, Globe, Server, ShieldBan } from 'lucide-react'

import { StatusBadge } from '@/components/status-badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ms, num } from '@/lib/format'

function Tile({ icon: Icon, title, value, children }) {
  return (
    <Card className="gap-3 py-5">
      <CardHeader className="px-5">
        <CardDescription className="flex items-center gap-2">
          <Icon className="size-4" aria-hidden />
          {title}
        </CardDescription>
        <CardTitle className="text-2xl font-semibold">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-muted-foreground px-5 text-sm">{children}</CardContent>
    </Card>
  )
}

export function SummaryCards({ overview, rangeLabel }) {
  const { internet, device_counts: dc, firewall, open_alerts: open } = overview
  const best = internet.targets.filter((t) => t.rtt_ms != null).map((t) => t.rtt_ms)
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile icon={Globe} title="Internet" value={<StatusBadge status={internet.status} className="text-sm" />}>
        {internet.status === 'online' || internet.status === 'degraded'
          ? `${best.length ? ms(Math.min(...best)) : '–'} ping · DNS ${ms(internet.dns?.ms)}`
          : internet.reason}
      </Tile>
      <Tile icon={Server} title="Devices online" value={`${dc.online + dc.degraded} / ${dc.total}`}>
        {dc.offline ? `${dc.offline} offline` : 'none offline'}
        {dc.degraded ? ` · ${dc.degraded} degraded` : ''}
        {dc.unknown ? ` · ${dc.unknown} unknown` : ''}
      </Tile>
      <Tile icon={ShieldBan} title="Firewall blocks" value={num(firewall.block)}>
        {num(firewall.pass)} passed · {rangeLabel.toLowerCase()}
      </Tile>
      <Tile icon={BellRing} title="Active alerts" value={open.length}>
        {open.length ? open[0].title : 'all clear'}
      </Tile>
    </div>
  )
}
