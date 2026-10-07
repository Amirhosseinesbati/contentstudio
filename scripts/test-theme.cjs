/* Runtime-level appearance and production-boundary tests; no network. */
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { pathToFileURL } = require('node:url')
const root = path.resolve(__dirname, '..')
const bootstrap = fs.readFileSync(path.join(root, 'apps/web/public/theme-init.js'), 'utf8')
test('real application entry loads same-origin bootstrap and canvas before the bundle', () => {
  const html = fs.readFileSync(path.join(root, 'apps/web/index.html'), 'utf8')
  const script = html.indexOf('<script src="/theme-init.js"></script>')
  const canvas = html.indexOf('<link rel="stylesheet" href="/theme-base.css" />')
  const bundle = html.indexOf('type="module"')
  assert(script > 0 && canvas > script && bundle > canvas)
  assert(!html.includes('fonts.googleapis.com'), 'Prepaint must not need external font requests')
})
function setup({ saved, osDark = false, blocked = false } = {}) {
  let storageValue = saved
  const mediaListeners = new Set()
  const media = { matches: osDark, addEventListener(event, callback) { mediaListeners.add(callback) }, removeEventListener(event, callback) { mediaListeners.delete(callback) } }
  const events = {}
  const document = { documentElement: { dataset: {} }, querySelector() { return { setAttribute() {} } } }
  const window = { localStorage: { getItem() { if (blocked) throw Error('Blocked'); return storageValue }, setItem(key, value) { if (blocked) throw Error('Blocked'); storageValue = value } }, matchMedia() { return media }, addEventListener(event, callback) { events[event] = callback } }
  vm.runInNewContext(bootstrap, { window, document, Set })
  return { document, window, mediaListeners, events, stored: () => storageValue, osChange(matches) { media.matches = matches; mediaListeners.forEach((callback) => callback({ matches })) } }
}
test('fresh and invalid preferences default to dark on a light OS', () => {
  for (const saved of [undefined, null, '', 'invalid']) assert.equal(setup({ saved }).document.documentElement.dataset.theme, 'dark')
})
test('saved explicit preferences ignore OS changes', () => {
  for (const saved of ['light', 'dark']) {
    const env = setup({ saved, osDark: saved === 'light' })
    assert.equal(env.document.documentElement.dataset.theme, saved)
    assert.equal(env.mediaListeners.size, 0)
    env.osChange(saved === 'dark')
    assert.equal(env.window.contentStudioTheme.getSnapshot(), `${saved}:${saved}`)
  }
})
test('System follows OS live and detaches when an explicit mode is selected', () => {
  const env = setup({ saved: 'system' })
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'system:light')
  env.osChange(true)
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'system:dark')
  env.window.contentStudioTheme.choose('light')
  assert.equal(env.mediaListeners.size, 0)
  env.osChange(true)
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'light:light')
  assert.equal(env.stored(), 'light')
})
test('blocked storage keeps a usable in-memory preference and subscriptions', () => {
  const env = setup({ blocked: true })
  let updates = 0
  const unsubscribe = env.window.contentStudioTheme.subscribe(() => updates++)
  env.window.contentStudioTheme.choose('light')
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'light:light')
  assert.equal(updates, 1)
  unsubscribe()
  env.window.contentStudioTheme.choose('dark')
  assert.equal(updates, 1)
})
test('valid cross-tab changes synchronize; invalid preferences are ignored', () => {
  const env = setup()
  env.events.storage({ key: 'contentstudio.theme', newValue: 'light' })
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'light:light')
  env.events.storage({ key: 'contentstudio.theme', newValue: 'invalid' })
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'light:light')
  env.events.storage({ key: 'contentstudio.theme', newValue: null })
  assert.equal(env.window.contentStudioTheme.getSnapshot(), 'dark:dark')
})
test('preflight requires approved evidence, clean warnings and complete media', async () => {
  const { packagePreflight } = await import(pathToFileURL(path.join(root, 'apps/web/src/features/production.ts')).href)
  const base = { id: 'one', asset_type: 'article', status: 'approved', warnings: [], source_segment_ids: ['span'] }
  assert.equal(packagePreflight([]).ready, false)
  assert.equal(packagePreflight([base]).ready, true)
  assert.equal(packagePreflight([{ ...base, warnings: ['Unverified claim'] }]).ready, false)
  assert.equal(packagePreflight([{ ...base, source_segment_ids: [] }]).ready, false)
  assert.equal(packagePreflight([{ ...base, asset_type: 'clip' }]).ready, false)
  assert.equal(packagePreflight([{ ...base, asset_type: 'clip', status: 'rendered', render_urls: { mp4: '/registered.mp4' } }]).ready, true)
  assert.equal(packagePreflight([{ ...base, asset_type: 'carousel', status: 'rendered', render_urls: { png: ['/slide.png'] } }]).ready, false)
  assert.equal(packagePreflight([{ ...base, asset_type: 'carousel', status: 'rendered', render_urls: { png: ['/slide.png'], pdf: '/deck.pdf' } }]).ready, true)
  assert.equal(packagePreflight([{ ...base, status: 'stale' }]).ready, false)
})
