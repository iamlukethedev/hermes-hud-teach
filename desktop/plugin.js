import { host, PALETTE_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

export default {
  id: 'hud-teach',
  name: 'HUD Teach',
  defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      {
        id: 'chip',
        area: STATUSBAR_AREAS.right,
        order: 140,
        render: () =>
          jsx('span', {
            className: 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
            children: 'teach'
          })
      },
      {
        id: 'clear',
        area: PALETTE_AREA,
        data: {
          id: 'hud-teach.clear',
          keywords: ['teach', 'overlay', 'annotate', 'clear', 'marks'],
          label: 'Clear screen marks',
          run: () => {
            void ctx
              .rest('/clear', { method: 'POST' })
              .then(() => host.notify({ kind: 'info', message: 'Screen marks cleared.' }))
              .catch(err => host.notifyError(err, 'Could not clear screen marks.'))
          }
        }
      }
    ])
  }
}
