import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { Button, ErrorNotice, Label } from '../components/Common'
import type { BrandProfile } from '../types'

export function BrandManager({ brands, canEdit, notify }: {
  brands: BrandProfile[]; canEdit: boolean; notify: (message: string) => void
}) {
  const [selected, setSelected] = useState<BrandProfile | null>(null)
  const [creating, setCreating] = useState(false)
  const latest = brands.filter((brand) => !brands.some((other) => other.name === brand.name && other.version > brand.version))
  return <details className="source-actions brand-manager"><summary>Brand profiles and version history</summary>
    <p>New batches use the selected brand version. Saving a revision preserves the brand and approval history of existing batches.</p>
    {latest.map((brand) => <div key={brand.id} className="batch-create"><strong>{brand.name} · v{brand.version}</strong><p>{brand.tone}</p>
      <Button variant="outline" disabled={!canEdit} onClick={() => { setCreating(false); setSelected(brand) }}>Revise {brand.name}</Button>
      <details><summary>Saved versions</summary><ul>{brands.filter((item) => item.name === brand.name).map((item) => <li key={item.id}>Version {item.version}: {item.tone}</li>)}</ul></details>
    </div>)}
    <Button variant="outline" disabled={!canEdit} onClick={() => { setSelected(null); setCreating(true) }}>Create brand profile</Button>
    {creating || selected ? <BrandForm key={selected?.id ?? 'new'} brand={selected} onClose={() => { setCreating(false); setSelected(null) }} notify={notify} /> : null}
    {!canEdit ? <p>Viewer access is read only.</p> : null}
  </details>
}

function BrandForm({ brand, onClose, notify }: { brand: BrandProfile | null; onClose: () => void; notify: (message: string) => void }) {
  const queryClient = useQueryClient()
  const rules = brand?.rules && !Array.isArray(brand.rules) ? brand.rules : {}
  const [name, setName] = useState(brand?.name ?? '')
  const [tone, setTone] = useState(brand?.tone ?? '')
  const [accent, setAccent] = useState(typeof rules.accent === 'string' ? rules.accent : '#D26634')
  const [phrases, setPhrases] = useState(Array.isArray(rules.prohibited_phrases) ? rules.prohibited_phrases.join('\n') : '')
  const [limit, setLimit] = useState(typeof rules.max_social_chars === 'number' ? Math.min(500, rules.max_social_chars) : 500)
  const save = useMutation({ mutationFn: () => {
    const revision = { tone: tone.trim(), rules: { accent, prohibited_phrases: phrases.split('\n').map((value) => value.trim()).filter(Boolean), max_social_chars: limit } }
    return brand ? api.reviseBrand(brand.id, revision) : api.createBrand({ name: name.trim(), ...revision })
  }, onSuccess: async (result) => { await queryClient.invalidateQueries({ queryKey: ['brands'] }); notify(`${result.name} version ${result.version} saved. Existing batches keep their pinned brand.`); onClose() } })
  return <form className="asset-edit-form" onSubmit={(event) => { event.preventDefault(); save.mutate() }}>
    <Label htmlFor="brand-name">Brand name</Label><input id="brand-name" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={45} readOnly={!!brand} />
    <Label htmlFor="brand-tone">Voice and tone</Label><textarea id="brand-tone" value={tone} onChange={(event) => setTone(event.target.value)} required minLength={2} maxLength={300} rows={3} />
    <Label htmlFor="brand-accent">Media accent color</Label><input id="brand-accent" type="color" value={accent} onChange={(event) => setAccent(event.target.value)} />
    <Label htmlFor="brand-phrases">Prohibited phrases · one per line</Label><textarea id="brand-phrases" value={phrases} onChange={(event) => setPhrases(event.target.value)} rows={4} />
    <Label htmlFor="brand-social-limit">Social draft character limit</Label><input id="brand-social-limit" type="number" min={80} max={500} value={limit} onChange={(event) => setLimit(Number(event.target.value))} required />
    <div className="edit-actions"><Button type="submit" loading={save.isPending}>Save {brand ? `version ${brand.version + 1}` : 'brand'}</Button><Button type="button" variant="text" onClick={onClose}>Cancel</Button></div>
    {save.isError ? <ErrorNotice error={save.error} title="Brand was not saved" /> : null}
  </form>
}
