import { Activity, CircleX, Moon, RefreshCw, Sun, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'

import { AlertsView } from '@/components/alerts-view'
import { FirewallView } from '@/components/firewall-view'
import { InternetChart } from '@/components/internet-chart'
import { SummaryCards } from '@/components/summary-cards'
import { SwitchPorts } from '@/components/switch-ports'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/sonner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { VlanCards } from '@/components/vlan-cards'
import { usePoll } from '@/lib/api'
import { clock, RANGES, timeAgo } from '@/lib/format'

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem('theme', theme)
  }, [theme])
  return [theme, setTheme]
}

function Banners({ health, overview }) {
  return (
    <>
      {health?.collector_stale && (
        <Alert>
          <TriangleAlert className="text-status-warning" />
          <AlertTitle>Collector isn’t reporting</AlertTitle>
          <AlertDescription>
            Last check was {timeAgo(health.last_check_ts)}. Statuses below are “unknown” until it runs
            again: <code>python -m netmon.runner --config config.json</code>
          </AlertDescription>
        </Alert>
      )}
      {overview?.open_alerts?.map((a) => (
        <Alert key={a.id} variant="destructive">
          <CircleX />
          <AlertTitle>{a.title}</AlertTitle>
          <AlertDescription>
            {a.detail} Since {clock(a.opened_ts, true)}.
          </AlertDescription>
        </Alert>
      ))}
    </>
  )
}

export default function App() {
  const [theme, setTheme] = useTheme()
  const [range, setRange] = useState('1')
  // Active tab lives in the URL hash so views can be bookmarked (/#firewall).
  const [tab, setTab] = useState(() => window.location.hash.slice(1) || 'overview')
  const changeTab = (t) => {
    setTab(t)
    window.history.replaceState(null, '', `#${t}`)
  }
  const hours = Number(range)
  const overview = usePoll('/overview', { hours })
  const health = usePoll('/health')
  const o = overview.data
  const rangeLabel = RANGES.find((r) => r.value === range)?.label || ''

  return (
    <TooltipProvider>
      <div className="mx-auto flex min-h-svh max-w-[1500px] flex-col gap-6 p-4 md:p-8">
        <header className="flex flex-wrap items-center gap-3">
          <Activity className="size-6" aria-hidden />
          <div className="mr-auto">
            <h1 className="text-xl font-semibold tracking-tight">Home Network Monitor</h1>
            <p className="text-muted-foreground text-sm">
              OPNsense VLANs · {o ? `updated ${clock(o.generated_ts)}` : 'connecting…'}
            </p>
          </div>
          {overview.error && <Badge variant="destructive">API unreachable</Badge>}
          <Select value={range} onValueChange={setRange}>
            <SelectTrigger className="w-40" aria-label="Time range">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RANGES.map((r) => (
                <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" aria-label="Refresh"
            onClick={() => { overview.reload(); health.reload() }}>
            <RefreshCw />
          </Button>
          <Button variant="outline" size="icon" aria-label="Toggle theme"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun /> : <Moon />}
          </Button>
        </header>

        <Banners health={health.data} overview={o} />

        {!o ? (
          overview.error ? (
            <Alert variant="destructive">
              <CircleX />
              <AlertTitle>Can’t reach the API</AlertTitle>
              <AlertDescription>
                {overview.error}. Start it with <code>python -m netmon.api --config config.json</code> from
                the collector folder.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
            </div>
          )
        ) : (
          <Tabs value={tab} onValueChange={changeTab} className="gap-4">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="firewall">Firewall logs</TabsTrigger>
              <TabsTrigger value="alerts">
                Alerts
                {o.open_alerts.length > 0 && (
                  <Badge variant="destructive" className="h-5 min-w-5 rounded-full px-1">
                    {o.open_alerts.length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="flex flex-col gap-4">
              <SummaryCards overview={o} rangeLabel={rangeLabel} />
              <SwitchPorts sw={o.switch} vlans={o.vlans} />
              <VlanCards vlans={o.vlans} />
              <InternetChart hours={hours} internet={o.internet} />
            </TabsContent>

            <TabsContent value="firewall">
              <FirewallView hours={hours} vlans={o.vlans} />
            </TabsContent>

            <TabsContent value="alerts">
              <AlertsView notifications={o.notifications} now={o.generated_ts} />
            </TabsContent>
          </Tabs>
        )}
      </div>
      <Toaster theme={theme} position="bottom-right" />
    </TooltipProvider>
  )
}
