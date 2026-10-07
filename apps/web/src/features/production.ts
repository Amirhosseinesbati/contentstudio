import type { ContentAsset } from '../types'

/** Advisory UI preflight. The API remains the authority for exact approval hashes,
 * registered files, content validation, source rights and package integrity. */
export function packagePreflight(assets: ContentAsset[]) {
  const approved = assets.filter((asset) => ['approved', 'rendered'].includes(asset.status))
  const withWarnings = approved.filter((asset) => asset.warnings.length > 0)
  const withoutEvidence = approved.filter((asset) => asset.source_segment_ids.length === 0)
  const waitingForRender = approved.filter((asset) => {
    if (asset.asset_type === 'carousel') return asset.status !== 'rendered' || !asset.render_urls?.png?.length || !asset.render_urls.pdf
    if (['clip', 'video_clip'].includes(asset.asset_type)) return asset.status !== 'rendered' || !asset.render_urls?.mp4
    return false
  })
  const blockers = [
    ...(!approved.length ? ['Approve at least one asset.'] : []),
    ...(withWarnings.length ? [`Resolve validation warnings on ${withWarnings.length} approved asset(s).`] : []),
    ...(withoutEvidence.length ? [`Link source evidence on ${withoutEvidence.length} approved asset(s).`] : []),
    ...(waitingForRender.length ? [`Render production files for ${waitingForRender.length} approved media asset(s).`] : []),
  ]
  return { approved, waitingForRender, blockers, ready: blockers.length === 0 }
}
