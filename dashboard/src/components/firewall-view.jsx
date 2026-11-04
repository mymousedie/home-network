import { ChevronLeft, ChevronRight, Search, ShieldBan, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePoll } from '@/lib/api'
import { clock, num, tick, timeAgo } from '@/lib/format'

const PAGE = 50
const chartConfig = {
  pass: { label: 'Passed', color: 'var(--chart-1)' },
  block: { label: 'Blocked', color: 'var(--chart-2)' },
}

function Action({ action }) {
  const Icon = action === 'block' ? ShieldBan : ShieldCheck
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon
        className={action === 'block' ? 'text-[var(--chart-2)] size-4' : 'text-[var(--chart-1)] size-4'}
        aria-hidden
      />
      {action === 'block' ? 'Block' : 'Pass'}
    </span>
  )
}

function addr(ip, port) {
  return port == null ? ip : `${ip}:${port}`
}

function useDebounced(value, delay = 300) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}

export function FirewallView({ hours, vlans }) {
  const [vlan, setVlan] = useState('all')
  const [action, setAction] = useState('all')
  const [query, setQuery] = useState('')
  const q = useDebounced(query.trim())
  // Any filter change sends you back to page 1.
  const filterKey = JSON.stringify([vlan, action, q, hours])
  const [paging, setPaging] = useState({ key: filterKey, page: 0 })
  const page = paging.key === filterKey ? paging.page : 0
  const setPage = (fn) => setPaging({ key: filterKey, page: fn(page) })

  const vlanParam = vlan === 'all' ? undefined : vlan
  const actionParam = action === 'all' ? undefined : action
  const events = usePoll('/firewall/events', {
    hours, vlan: vlanParam, action: actionParam, q, limit: PAGE, offset: page * PAGE,
  })
  const series = usePoll('/timeseries/firewall', { hours, vlan: vlanParam })
  const top = usePoll('/firewall/top', { hours, vlan: vlanParam, action: 'block', by: 'src' })

  const shown = actionParam ? [actionParam] : ['pass', 'block']
  const points = useMemo(() => series.data?.points || [], [series.data])
  const total = events.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE))
  const fwVlans = vlans.filter((v) => v.iface)

  return (
    <div className="flex flex-col gap-4">
      {/* One filter row drives every panel below it. */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={vlan} onValueChange={setVlan}>
          <SelectTrigger className="w-44" aria-label="Interface">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All interfaces</SelectItem>
            {fwVlans.map((v) => (
              <SelectItem key={v.id} value={String(v.id)}>
                {v.name} (VLAN {v.id})
              </SelectItem>
            ))}
            <SelectItem value="0">WAN</SelectItem>
          </SelectContent>
        </Select>
        <Select value={action} onValueChange={setAction}>
          <SelectTrigger className="w-36" aria-label="Action">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Pass + block</SelectItem>
            <SelectItem value="block">Blocked only</SelectItem>
            <SelectItem value="pass">Passed only</SelectItem>
          </SelectContent>
        </Select>
        <div className="relative w-full sm:w-72">
          <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" aria-hidden />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by IP, protocol or port"
            className="pl-8"
          />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Card>
          <CardHeader>
            <CardTitle>Firewall activity</CardTitle>
            <CardDescription>Logged packets per {Math.round((series.data?.bucket_s || 60) / 60)} min</CardDescription>
          </CardHeader>
          <CardContent>
            {series.loading && !series.data ? (
              <Skeleton className="h-80 w-full" />
            ) : points.length ? (
              <ChartContainer config={chartConfig} className="aspect-auto h-80 w-full">
                <BarChart data={points} margin={{ left: 4, right: 4, top: 8 }} barCategoryGap={2}>
                  <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                  <XAxis dataKey="ts" tickLine={false} axisLine={false} minTickGap={40}
                    tickFormatter={(v) => tick(v, hours)} />
                  <YAxis tickLine={false} axisLine={false} width={48} allowDecimals={false} />
                  <ChartTooltip
                    content={<ChartTooltipContent labelFormatter={(v) => clock(v, hours > 24)}
                      valueFormatter={(v) => num(v)} />}
                  />
                  {shown.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
                  {shown.map((k, i) => (
                    <Bar
                      key={k}
                      dataKey={k}
                      stackId="a"
                      fill={`var(--color-${k})`}
                      stroke="var(--card)"
                      strokeWidth={1}
                      radius={i === shown.length - 1 ? [4, 4, 0, 0] : 0}
                      isAnimationActive={false}
                    />
                  ))}
                </BarChart>
              </ChartContainer>
            ) : (
              <div className="text-muted-foreground flex h-80 items-center justify-center text-center text-sm">
                No firewall events in this range. Only rules with “Log” ticked in OPNsense are recorded.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top blocked sources</CardTitle>
            <CardDescription>Who keeps hitting block rules</CardDescription>
          </CardHeader>
          <CardContent>
            {top.data?.rows?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Interface</TableHead>
                    <TableHead className="text-right">Blocks</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {top.data.rows.map((r) => (
                    <TableRow key={`${r.addr}-${r.iface}`} title={`last ${timeAgo(r.last_ts)}`}>
                      <TableCell className="font-mono text-xs">{r.addr}</TableCell>
                      <TableCell><Badge variant="secondary">{r.iface_label}</Badge></TableCell>
                      <TableCell className="text-right tabular-nums">{num(r.n)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-muted-foreground text-sm">No blocked traffic in this range.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Firewall log</CardTitle>
          <CardDescription>
            {events.error ? `Couldn't load: ${events.error}` : `${num(total)} matching events, newest first`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Interface</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Dir</TableHead>
                <TableHead>Proto</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Destination</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data?.rows?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="tabular-nums">{clock(r.ts, true)}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{r.iface_label}</Badge>
                    <span className="text-muted-foreground ml-1.5 font-mono text-xs">{r.iface}</span>
                  </TableCell>
                  <TableCell><Action action={r.action} /></TableCell>
                  <TableCell className="text-muted-foreground">{r.direction}</TableCell>
                  <TableCell className="uppercase">{r.proto}</TableCell>
                  <TableCell className="font-mono text-xs">{addr(r.src, r.src_port)}</TableCell>
                  <TableCell className="font-mono text-xs">{addr(r.dst, r.dst_port)}</TableCell>
                </TableRow>
              ))}
              {events.data && !events.data.rows.length && (
                <TableRow>
                  <TableCell colSpan={7} className="text-muted-foreground py-8 text-center">
                    Nothing matches these filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex items-center justify-end gap-2 text-sm">
            <span className="text-muted-foreground">Page {page + 1} of {pages}</span>
            <Button variant="outline" size="icon" aria-label="Previous page"
              disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="icon" aria-label="Next page"
              disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
