/* Same-origin blocking prepaint bootstrap: no inline script or business requests. */
(function () {
  'use strict'
  var key = 'contentstudio.theme'
  var valid = function (value) { return value === 'light' || value === 'dark' || value === 'system' }
  var preference = 'dark'
  try { var saved = window.localStorage.getItem(key); if (valid(saved)) preference = saved } catch (_) { /* Memory-only preference remains usable. */ }
  var media = null
  try { media = window.matchMedia('(prefers-color-scheme: dark)') } catch (_) { /* Dark fallback. */ }
  var resolved = preference === 'system' ? (media && !media.matches ? 'light' : 'dark') : preference
  var listeners = new Set()
  var listening = false
  function apply() {
    document.documentElement.dataset.theme = resolved
    document.documentElement.dataset.themePreference = preference
    var meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', resolved === 'dark' ? '#0b1017' : '#f1f4f8')
  }
  function emit() { apply(); listeners.forEach(function (listener) { listener() }) }
  function systemChanged(event) { if (preference === 'system') { resolved = event.matches ? 'dark' : 'light'; emit() } }
  function syncListener() {
    if (!media) return
    var needed = preference === 'system'
    if (needed === listening) return
    if (media.addEventListener) {
      if (needed) media.addEventListener('change', systemChanged)
      else media.removeEventListener('change', systemChanged)
    } else if (media.addListener) {
      if (needed) media.addListener(systemChanged)
      else media.removeListener(systemChanged)
    }
    listening = needed
  }
  function choose(value, persist) {
    if (!valid(value)) return
    preference = value
    resolved = value === 'system' ? (media && !media.matches ? 'light' : 'dark') : value
    syncListener()
    if (persist) { try { window.localStorage.setItem(key, value) } catch (_) { /* Storage is optional for this session. */ } }
    emit()
  }
  window.contentStudioTheme = {
    getSnapshot: function () { return preference + ':' + resolved },
    subscribe: function (listener) { listeners.add(listener); return function () { listeners.delete(listener) } },
    choose: function (value) { choose(value, true) },
  }
  window.addEventListener('storage', function (event) {
    if (event.key === key && (event.newValue === null || valid(event.newValue))) choose(event.newValue || 'dark', false)
  })
  syncListener()
  apply()
})()
