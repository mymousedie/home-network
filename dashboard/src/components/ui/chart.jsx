import { createContext, useContext, useId, useMemo } from 'react'
import * as RechartsPrimitive from 'recharts'

import { cn } from '@/lib/utils'

// shadcn/ui chart: config maps each series key to { label, color }.
const ChartContext = createContext(null)

function useChart() {
  const ctx = useContext(ChartContext)
  if (!ctx) throw new Error('useChart must be used within a <ChartContainer />')
  return ctx
}

function ChartContainer({ id, className, children, config, ...props }) {
  const uniqueId = useId()
  const chartId = `chart-${id || uniqueId.replace(/:/g, '')}`
  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-slot="chart"
        data-chart={chartId}
        className={cn(
          "[&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-[var(--chart-grid)] [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-rectangle.recharts-tooltip-cursor]:fill-muted/60 [&_.recharts-layer]:outline-hidden [&_.recharts-surface]:outline-hidden flex aspect-video justify-center text-xs",
          className,
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer>{children}</RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

function ChartStyle({ id, config }) {
  const vars = Object.entries(config)
    .filter(([, c]) => c.color)
    .map(([key, c]) => `  --color-${key}: ${c.color};`)
    .join('\n')
  if (!vars) return null
  return <style>{`[data-chart=${id}] {\n${vars}\n}`}</style>
}

const ChartTooltip = RechartsPrimitive.Tooltip

function ChartTooltipContent({
  active,
  payload,
  label,
  labelFormatter,
  valueFormatter = (v) => v,
  className,
  hideLabel = false,
}) {
  const { config } = useChart()
  const header = useMemo(() => {
    if (hideLabel || !payload?.length) return null
    return labelFormatter ? labelFormatter(label, payload) : label
  }, [hideLabel, label, labelFormatter, payload])

  if (!active || !payload?.length) return null

  return (
    <div
      className={cn(
        'border-border/50 bg-background grid min-w-[9rem] items-start gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs shadow-xl',
        className,
      )}
    >
      {header && <div className="font-medium">{header}</div>}
      <div className="grid gap-1.5">
        {payload.map((item) => {
          const key = item.dataKey || item.name
          const cfg = config[key] || {}
          return (
            <div key={key} className="flex w-full items-center gap-2">
              <div
                className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
                style={{ backgroundColor: item.color || `var(--color-${key})` }}
              />
              <span className="text-muted-foreground flex-1">{cfg.label || item.name}</span>
              <span className="text-foreground font-mono font-medium tabular-nums">
                {item.value == null ? '–' : valueFormatter(item.value, key)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const ChartLegend = RechartsPrimitive.Legend

function ChartLegendContent({ className, payload, verticalAlign = 'bottom' }) {
  const { config } = useChart()
  if (!payload?.length) return null
  return (
    <div
      className={cn(
        'flex items-center justify-center gap-4',
        verticalAlign === 'top' ? 'pb-3' : 'pt-3',
        className,
      )}
    >
      {payload.map((item) => {
        const key = item.dataKey || item.value
        return (
          <div key={key} className="text-muted-foreground flex items-center gap-1.5">
            <div className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
            {config[key]?.label || item.value}
          </div>
        )
      })}
    </div>
  )
}

export { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent, ChartStyle }
