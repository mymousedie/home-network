import { BellRing, CircleCheck, CircleX, Send } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { apiPost, usePoll } from '@/lib/api'
import { clock, duration } from '@/lib/format'

const DELIVERY = { 0: 'pending', 1: 'sent', 2: 'skipped' }

function Delivery({ a }) {
  const open = DELIVERY[a.notified_open]
  const res = a.resolved_ts ? DELIVERY[a.notified_resolved] : null
  return (
    <span className="text-muted-foreground text-xs">
      {open}
      {res ? ` / ${res}` : ''}
    </span>
  )
}

export function AlertsView({ notifications, now }) {
  const { data, reload } = usePoll('/alerts', { state: 'all', limit: 200 })
  const [sending, setSending] = useState(false)

  async function sendTest() {
    setSending(true)
    try {
      await apiPost('/notifications/test')
      toast.success('Test message sent to Discord')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSending(false)
      reload()
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BellRing className="size-4" aria-hidden /> Discord notifications
          </CardTitle>
          <CardDescription>
            A critical alert fires when a device misses {notifications.down_after_failures} pings in a row,
            every internet target stops replying, or DNS stops answering. You get one message when it
            starts and one when it clears.
          </CardDescription>
          <CardAction>
            <Button onClick={sendTest} disabled={sending || !notifications.discord_configured}>
              <Send /> {sending ? 'Sending…' : 'Send test message'}
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3 text-sm">
          {notifications.discord_configured ? (
            <Badge variant="outline" className="gap-1.5">
              <CircleCheck className="text-status-good" aria-hidden /> Webhook configured
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5">
              <CircleX className="text-status-critical" aria-hidden /> No webhook: set NETMON_DISCORD_WEBHOOK
              in collector/.env
            </Badge>
          )}
          {notifications.mention && (
            <span className="text-muted-foreground">
              Mentions <code className="bg-muted rounded px-1">{notifications.mention}</code> so your phone
              gets a push
            </span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alert history</CardTitle>
          <CardDescription>Newest first. Discord delivery: open message / recovery message.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>State</TableHead>
                <TableHead>Alert</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Discord</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.alerts?.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    {a.resolved_ts ? (
                      <Badge variant="outline" className="gap-1.5">
                        <CircleCheck className="text-status-good" aria-hidden /> Resolved
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1.5">
                        <CircleX className="text-status-critical" aria-hidden /> Open
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <div className="font-medium">{a.title}</div>
                    <div className="text-muted-foreground text-xs">{a.detail}</div>
                  </TableCell>
                  <TableCell className="tabular-nums">{clock(a.opened_ts, true)}</TableCell>
                  <TableCell className="tabular-nums">
                    {duration((a.resolved_ts || now) - a.opened_ts)}
                    {!a.resolved_ts && ' so far'}
                  </TableCell>
                  <TableCell><Delivery a={a} /></TableCell>
                </TableRow>
              ))}
              {data && !data.alerts.length && (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                    No alerts yet. That’s a good thing.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
