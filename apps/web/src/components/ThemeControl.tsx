import { useSyncExternalStore } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'

type Preference = 'light' | 'dark' | 'system'
declare global {
  interface Window {
    contentStudioTheme: {
      getSnapshot: () => string
      subscribe: (listener: () => void) => () => void
      choose: (preference: Preference) => void
    }
  }
}
const choices = [{ value: 'light', label: 'Light', Icon: Sun }, { value: 'dark', label: 'Dark', Icon: Moon }, { value: 'system', label: 'System', Icon: Monitor }] as const

/** Only this control subscribes; the workspace and unsaved editors stay mounted. */
export function ThemeControl() {
  const snapshot = useSyncExternalStore(window.contentStudioTheme.subscribe, window.contentStudioTheme.getSnapshot)
  const [preference, resolved] = snapshot.split(':')
  return <div className="theme-control" role="group" aria-label="Appearance">
    {choices.map(({ value, label, Icon }) => <button key={value} type="button" aria-label={`${label} theme`} aria-pressed={preference === value} title={value === 'system' ? `System theme · currently ${resolved}` : `${label} theme`} onClick={() => window.contentStudioTheme.choose(value)}><Icon size={14} /><span>{label}</span></button>)}
  </div>
}
