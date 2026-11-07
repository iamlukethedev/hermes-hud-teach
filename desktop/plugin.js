import { host, PALETTE_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

const POLL_MS = 5000

function createStatusStore() {
  let current = { visible: false }
  const listeners = new Set()
  return {
    get: () => current,
    set(next) {
      current = next || { visible: false }
      listeners.forEach(fn => fn(current))
    },
    subscribe(fn) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    }
  }
}

function chipText(status) {
  if (!status.visible) return 'teach'
  if (status.current_step && status.steps) return `teach · step ${status.current_step}/${status.steps}`
  const n = status.shapes || status.drawn || 0
  return `teach · ${n} mark${n === 1 ? '' : 's'}`
}

function chipTitle(status) {
  if (!status.visible) return 'HUD Teach: no marks on screen'
  const parts = [status.title ? `Lesson: ${status.title}` : 'Marks on screen']
  if (typeof status.expires_in === 'number') parts.push(`clears in ${status.expires_in}s`)
  parts.push('click to clear')
  return parts.join(' · ')
}

export default {
  id: 'hud-teach',
  name: 'HUD Teach',
  defaultEnabled: false,
  register(ctx) {
    const store = createStatusStore()

    const refresh = () =>
      ctx
        .rest('/status')
        .then(data => store.set(data && data.ok ? data : { visible: false }))
        .catch(() => store.set({ visible: false }))

    const clearMarks = () =>
      ctx
        .rest('/clear', { method: 'POST' })
        .then(() => {
          store.set({ visible: false })
          host.notify({ kind: 'info', message: 'Screen marks cleared.' })
        })
        .catch(err => host.notifyError(err, 'Could not clear screen marks.'))

    const checkSetup = () =>
      ctx
        .rest('/check')
        .then(data => {
          if (data && data.ok && data.ready) {
            host.notify({ kind: 'info', message: 'HUD Teach is ready: permissions, Tk and overlay look good.' })
            return
          }
          const steps = (data && data.next_steps) || []
          const message = steps.length ? `HUD Teach needs setup: ${steps[0]}` : `HUD Teach check failed: ${(data && data.error) || 'unknown error'}`
          host.notify({ kind: 'warning', message })
        })
        .catch(err => host.notifyError(err, 'Could not run the HUD Teach check.'))

    ctx.onEvent('plugin.hud-teach.marks.changed', () => void refresh())
    ctx.setInterval(() => void refresh(), POLL_MS)
    void refresh()

    function Chip() {
      const [status, setStatus] = useState(store.get())
      useEffect(() => store.subscribe(setStatus), [])
      const active = Boolean(status.visible)
      return jsx('button', {
        type: 'button',
        title: chipTitle(status),
        disabled: !active,
        onClick: active ? () => void clearMarks() : undefined,
        className: active
          ? 'px-1.5 text-[0.6875rem] text-(--ui-text-primary) hover:underline'
          : 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
        children: chipText(status)
      })
    }

    ctx.registerMany([
      {
        id: 'chip',
        area: STATUSBAR_AREAS.right,
        order: 140,
        render: () => jsx(Chip, {})
      },
      {
        id: 'clear',
        area: PALETTE_AREA,
        data: {
          id: 'hud-teach.clear',
          keywords: ['teach', 'overlay', 'annotate', 'clear', 'marks', 'lesson'],
          label: 'Clear screen marks',
          run: () => void clearMarks()
        }
      },
      {
        id: 'check',
        area: PALETTE_AREA,
        data: {
          id: 'hud-teach.check',
          keywords: ['teach', 'hud', 'permissions', 'screen recording', 'setup', 'check'],
          label: 'Check HUD Teach setup',
          run: () => void checkSetup()
        }
      }
    ])
  }
}
