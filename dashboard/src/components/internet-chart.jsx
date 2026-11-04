import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { usePoll } from '@/lib/api'
import { clock, ms, pct, tick } from '@/lib/format'

// Series colors follow the target's position in config (fixed order, never
// re-ranked), so filtering never repaints a line.
const SLOTS = ['var(--chart-1)', 'var(--chart-2)']

export function InternetChart({ hours, internet }) {
  const { data, loading } = usePoll('/timeseries/internet', { hours })
  const targetsKey = internet.targets.map((t) => t.target).join(',')

  const { rows, config } = useMemo(() => {
    const targets = targetsKey.split(',')
    const cfg = {}
    targets.forEach((t, i) => {
      cfg[`t${i}`] = { label: t, color: SLOTS[i % SLOTS.length] }
    })
    const byTs = new Map()
    for (const p of data?.points || []) {
      const i = targets.indexOf(p.target)
      if (i < 0) continue
      const row = byTs.get(p.ts) || { ts: p.ts }
      row[`t${i}`] = p.avg_rtt
      byTs.set(p.ts, row)
    }
    return { rows: [...byTs.values()], config: cfg }
  }, [data, targetsKey])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Internet latency</CardTitle>
        <CardDescription>Average ping round-trip per target (ms). Gaps mean no reply.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[1fr_16rem]">
        {loading && !data ? (
          <Skeleton className="aspect-[3/1] w-full" />
        ) : rows.length ? (
          <ChartContainer config={config} className="aspect-auto h-64 w-full">
            <LineChart data={rows} margin={{ left: 4, right: 12, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="0" stroke="var(--chart-grid)" />
              <XAxis
                dataKey="ts"
                tickLine={false}
                axisLine={false}
                minTickGap={40}
                tickFormatter={(v) => tick(v, hours)}
              />
              <YAxis tickLine={false} axisLine={false} width={44} unit=" ms" />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(v) => clock(v, hours > 24)}
                    valueFormatter={(v) => ms(v)}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              {Object.keys(config).map((k) => (
                <Line
                  key={k}
                  dataKey={k}
                  type="monotone"
                  stroke={`var(--color-${k})`}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ChartContainer>
        ) : (
          <div className="text-muted-foreground flex h-64 items-center justify-center text-sm">
            No internet checks in this range.
          </div>
        )}

        <dl className="grid content-start gap-3 text-sm">
          {internet.targets.map((t) => (
            <div key={t.target} className="rounded-lg border p-3">
              <dt className="font-mono text-xs">{t.target}</dt>
              <dd className="mt-1 flex justify-between tabular-nums">
                <span>{t.up_now === false ? 'no reply' : ms(t.rtt_ms)}</span>
                <span className="text-muted-foreground">{pct(t.loss_pct)} loss</span>
              </dd>
            </div>
          ))}
          {internet.dns && (
            <div className="rounded-lg border p-3">
              <dt className="font-mono text-xs">
                DNS {internet.dns.server} → {internet.dns.name}
              </dt>
              <dd className="mt-1 flex justify-between tabular-nums">
                <span>{internet.dns.ms == null ? 'failed' : ms(internet.dns.ms)}</span>
                <span className="text-muted-foreground">avg {ms(internet.dns.avg_ms)}</span>
              </dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  )
}
