import { useState, type RefObject } from 'react'
import { CircleAlert, RefreshCw } from 'lucide-react'
import { apiUrl } from '../api'
import { Button } from './Common'

export function MediaPlayback({ url, title, hasVideo, audioRef, videoRef }: {
  url: string; title: string; hasVideo: boolean
  audioRef: RefObject<HTMLAudioElement | null>; videoRef: RefObject<HTMLVideoElement | null>
}) {
  const [failed, setFailed] = useState(false)
  const retry = () => { setFailed(false); (hasVideo ? videoRef.current : audioRef.current)?.load() }
  return <>
    {hasVideo ? <video ref={videoRef} src={apiUrl(url)} controls preload="metadata" aria-label={`Play ${title}`} onError={() => setFailed(true)} onLoadedMetadata={() => setFailed(false)} />
      : <audio ref={audioRef} src={apiUrl(url)} controls preload="metadata" aria-label={`Play ${title}`} onError={() => setFailed(true)} onLoadedMetadata={() => setFailed(false)} />}
    {failed ? <div className="form-error" role="alert"><CircleAlert size={16} /><span>Playback unavailable. Restore missing source media by uploading the same recording and title in the library, or retry after reconnecting.</span><Button variant="text" onClick={retry}><RefreshCw size={15} />Retry playback</Button></div> : null}
  </>
}
