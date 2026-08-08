<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '@/composables/useApi'

const devices = ref<any[]>([])
const selectedDevice = ref('')
const selectedIsIos = computed(() => isIosDevice(selectedDevice.value))
const hasIosDevices = computed(() => devices.value.some(d => isIosDevice(d.serial)))
const hasAndroidDevices = computed(() => devices.value.some(d => !isIosDevice(d.serial)))
const streaming = ref(false)
const subTab = ref<'single' | 'multi'>('single')
const nickname = ref('')
const editingNickname = ref(false)
let logTimer: number | null = null
const srvLogs = ref<string[]>([])
const botLogs = ref<string[]>([])
let srvSeq = 0
const statusText = ref('')

/* Ã¢â€â‚¬Ã¢â€â‚¬ log level filter Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
const logFilter = ref<string>('All')
const LOG_FILTERS = ['All', 'Error', 'Warn', 'App', 'Flask'] as const
const logsOpen = ref(false)

const filteredSrvLogs = computed(() => {
  const logs = srvLogs.value.slice(-50)
  const f = logFilter.value
  if (f === 'All') return logs
  if (f === 'Error') return logs.filter(l => l.includes('[ERROR]') || l.includes('[CRITICAL]'))
  if (f === 'Warn') return logs.filter(l => l.includes('[WARN') || l.includes('[WARNING]'))
  if (f === 'App') return logs.filter(l => !l.includes('[Flask]') && !l.includes('werkzeug'))
  if (f === 'Flask') return logs.filter(l => l.includes('[Flask]') || l.includes('werkzeug') || l.includes('HTTP'))
  return logs
})

/* Ã¢â€â‚¬Ã¢â€â‚¬ bot log type selector Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
const botLogType = ref('bot')
const BOT_LOG_TYPES = [
  { value: 'bot', label: 'Bot' },
  { value: 'post', label: 'Post Bot' },
]

/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
   WebRTC streaming Ã¢â‚¬â€ shared logic for single + multi device
   Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */
interface RtcSession { pc: RTCPeerConnection; sessionId: string; pollTimer: number; sse: EventSource | null; status: string }
const rtcSessions = ref<Record<string, RtcSession>>({})
const rtcStatus = ref<Record<string, string>>({})

interface RecordingResponse {
  ok?: boolean
  running?: boolean
  filename?: string
  mode?: string
  url?: string
  error?: string
}

type NewsResult = {
  ok?: boolean
  error?: string
  current_url?: string
  headlines?: any[]
  articles?: any[]
  errors?: any[]
  extraction?: any
  completion?: any
  screenshots?: Record<string, string>
}

type StreamMode = 'rtc' | 'mjpeg' | 'h264'

type StreamInfo = {
  ok?: boolean
  platform?: string
  requested_mode?: string
  effective_mode?: string
  recommended_mode?: string
  fallback_mode?: string
  stream_url?: string
  mjpeg_url?: string
  mjpeg_settings?: Record<string, unknown>
  unsupported_actions?: string[]
  recovery?: Record<string, unknown>
  error?: string
}

function isIosSerial(serial: string | null | undefined): boolean {
  return !!serial && serial.startsWith('ios:')
}

function devicePlatform(serial: string | null | undefined): 'ios' | 'android' {
  const row = devices.value.find((d: any) => d.serial === serial)
  const platform = String(row?.platform || row?.device_platform || '').toLowerCase()
  if (platform === 'ios' || platform === 'android') return platform
  return isIosSerial(serial) ? 'ios' : 'android'
}

function isIosDevice(serial: string | null | undefined): boolean {
  return devicePlatform(serial) === 'ios'
}

function mjpegStreamUrl(serial: string): string {
  const modeParam = isIosDevice(serial) ? '&mode=wda-mjpeg' : ''
  return `/api/phone/stream?device=${encodeURIComponent(serial)}&fps=5${modeParam}`
}

function effectiveStreamMode(serial: string, mode: StreamMode): StreamMode {
  if (mode === 'h264') return mode
  return isIosDevice(serial) ? 'mjpeg' : mode
}

function streamModeText(serial: string, mode: StreamMode): string {
  if (mode === 'h264') return 'H.264'
  if (mode === 'rtc') return 'WebRTC'
  return isIosDevice(serial) ? 'WDA MJPEG' : 'MJPEG'
}

function streamModeTitle(serial: string, mode: StreamMode): string {
  if (mode === 'h264') return 'GhostAgent H.264 stream'
  if (isIosDevice(serial)) return 'iOS streams through WebDriverAgent MJPEG'
  return mode === 'rtc' ? 'Android Portal WebRTC stream' : 'Android MJPEG fallback stream'
}

function multiStreamLabel(serial: string): string {
  const mode = multiStreamMode.value[serial] || 'mjpeg'
  if (mode === 'rtc') return rtcStatus.value[serial] || 'RTC'
  return streamModeText(serial, mode)
}

function streamFallbackUrl(serial: string, fallback?: any): string {
  const url = String(fallback?.url || '').trim()
  return url || mjpegStreamUrl(serial)
}

const streamInfo = ref<Record<string, StreamInfo>>({})
const streamInfoStatus = ref<Record<string, string>>({})

function streamInfoModeParam(serial: string, mode: StreamMode): string {
  if (isIosDevice(serial)) return 'mjpeg'
  return mode === 'rtc' ? 'portal' : 'screencap'
}

function streamInfoTitle(serial: string): string {
  const info = streamInfo.value[serial]
  if (!info) return streamModeTitle(serial, multiStreamMode.value[serial] || singleStreamMode.value)
  const parts = [
    info.effective_mode ? `mode ${info.effective_mode}` : '',
    info.fallback_mode ? `fallback ${info.fallback_mode}` : '',
    info.unsupported_actions?.length ? `unsupported ${info.unsupported_actions.join(', ')}` : '',
  ].filter(Boolean)
  return parts.join(' | ') || streamModeTitle(serial, multiStreamMode.value[serial] || singleStreamMode.value)
}

async function resolveMjpegStreamUrl(serial: string, mode: StreamMode): Promise<string> {
  const fallback = mjpegStreamUrl(serial)
  try {
    const info = await api<StreamInfo>(
      `/api/phone/stream-info?device=${encodeURIComponent(serial)}&fps=5&mode=${encodeURIComponent(streamInfoModeParam(serial, mode))}`
    )
    streamInfo.value[serial] = info
    streamInfoStatus.value[serial] = ''
    return String(info.stream_url || fallback)
  } catch (error) {
    streamInfoStatus.value[serial] = error instanceof Error ? error.message.replace(/^API \d+:\s*/, '') : 'Stream metadata unavailable'
    return fallback
  }
}

function applyIosStreamFallback(serial: string, fallback?: any) {
  rtcStatus.value[serial] = 'WDA MJPEG'
  if (serial === selectedDevice.value) {
    singleStreamMode.value = 'mjpeg'
    singleMjpegUrl.value = streamFallbackUrl(serial, fallback)
  }
  if (multiStreaming.value[serial]) {
    multiStreamMode.value[serial] = 'mjpeg'
    mjpegUrls.value[serial] = streamFallbackUrl(serial, fallback)
  }
}

function blackWarningText(serial: string): string {
  return isIosDevice(serial) ? 'WDA stream stalled' : 'FLAG_SECURE - switch to MJPEG'
}

function streamPlaceholderText(serial: string): string {
  return isIosDevice(serial) ? 'Press play for WDA MJPEG' : 'Press WebRTC or MJPEG'
}

function uuid(): string {
  return ([1e7] as any + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c: any) =>
    (c ^ ((crypto.getRandomValues(new Uint8Array(1))[0] ?? 0) & 15) >> c / 4).toString(16))
}

async function rtcFixPortal(serial: string) {
  rtcStatus.value[serial] = 'Fixing Portal...'
  try {
    const r = await api(`/api/phone/portal-fix/${serial}`, { method: 'POST' })
    rtcStatus.value[serial] = r.ok ? 'Portal fixed Ã¢â‚¬â€ retry stream' : ('Fix failed: ' + (r.error || ''))
  } catch { rtcStatus.value[serial] = 'Fix failed' }
}

async function rtcStart(serial: string, _reconnectAttempt = 0) {
  console.log(`[RTC ${serial}] rtcStart called (attempt=${_reconnectAttempt})`)
  if (isIosDevice(serial)) {
    applyIosStreamFallback(serial)
    return
  }
  if (rtcSessions.value[serial]) rtcStop(serial)
  const sessionId = uuid()
  const t0 = performance.now()
  rtcStatus.value[serial] = 'Requesting...'

  const startRes = await api('/api/phone/webrtc-signal', {
    method: 'POST',
    body: JSON.stringify({ device: serial, method: 'stream/start', params: { sessionId, width: 720, height: 1280, fps: 30 } })
  })

  console.log(`[RTC ${serial}] stream/start response:`, JSON.stringify(startRes).substring(0, 100))
  if (!startRes.ok) {
    if (startRes.platform === 'ios' && startRes.stream_fallback) {
      applyIosStreamFallback(serial, startRes.stream_fallback)
      return
    }
    const err = startRes.error || 'unknown'
    if (err.includes('Accessibility') || err.includes('Portal not')) {
      rtcStatus.value[serial] = 'Portal down Ã¢â‚¬â€ fixing...'
      await rtcFixPortal(serial)
      const retry = await api('/api/phone/webrtc-signal', {
        method: 'POST',
        body: JSON.stringify({ device: serial, method: 'stream/start', params: { sessionId, width: 720, height: 1280, fps: 30 } })
      })
      if (!retry.ok) { rtcStatus.value[serial] = 'Portal fix failed: ' + (retry.error || err); return }
    } else { rtcStatus.value[serial] = 'Failed: ' + err; return }
  }

  const pc = new RTCPeerConnection({
    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    iceCandidatePoolSize: 1,  // Pre-allocate candidates for faster ICE
  })
  setupDataChannel(serial, pc)

  pc.ontrack = (evt) => {
    rtcStatus.value[serial] = 'Streaming'
    const videoEl = document.getElementById(`rtc-video-${serial}`) as HTMLVideoElement
    const stream = evt.streams[0]
    if (videoEl && stream) {
      videoEl.srcObject = stream
      videoEl.play().catch(() => {})
    }
    startBlackCheck(serial)
    console.log(`[RTC ${serial}] First frame in ${(performance.now() - t0).toFixed(0)}ms`)
  }

  pc.onicecandidate = (evt) => {
    if (evt.candidate) {
      api('/api/phone/webrtc-signal', {
        method: 'POST',
        body: JSON.stringify({ device: serial, method: 'webrtc/ice',
          params: { candidate: evt.candidate.candidate, sdpMid: evt.candidate.sdpMid,
            sdpMLineIndex: evt.candidate.sdpMLineIndex, sessionId } })
      })
    }
  }

  // Auto-reconnect on ICE failure (up to 3 attempts)
  pc.oniceconnectionstatechange = () => {
    const st = pc.iceConnectionState
    if (st === 'connected' || st === 'completed') {
      rtcStatus.value[serial] = 'Streaming'
      // Close SSE once ICE is stable Ã¢â‚¬â€ signals no longer needed
      const sess = rtcSessions.value[serial]
      if (sess?.sse) { sess.sse.close(); sess.sse = null }
    } else if (st === 'disconnected') {
      rtcStatus.value[serial] = 'Reconnecting...'
    } else if (st === 'failed') {
      rtcStatus.value[serial] = 'ICE failed'
      if (_reconnectAttempt < 3) {
        console.log(`[RTC ${serial}] Auto-reconnect attempt ${_reconnectAttempt + 1}/3`)
        rtcStatus.value[serial] = `Reconnecting (${_reconnectAttempt + 1}/3)...`
        setTimeout(() => rtcStart(serial, _reconnectAttempt + 1), 500)
      }
    } else if (st === 'checking') {
      rtcStatus.value[serial] = 'Connecting...'
    }
  }

  // Register session and start signal polling
  rtcStatus.value[serial] = 'Waiting for offer...'

  // Poll for signaling messages from phone
  let sse: EventSource | null = null
  console.log(`[RTC ${serial}] Starting poll timer (100ms interval)`)
  const pollTimer = window.setInterval(async () => {
    try {
      const r = await fetch(`/api/phone/webrtc-poll-signals/${serial}`)
      const d = await r.json()
      if (d.ok && d.messages?.length) {
        // Sort: process offers/answers BEFORE ICE candidates (they may arrive out of order)
        const msgs = d.messages.filter((m: any) => m.result !== 'prompting_user' && m.result !== 'reusing_capture')
        const parsed = msgs.map((data: any) => {
          const payload = data.payload ? (typeof data.payload === 'string' ? JSON.parse(data.payload) : data.payload) : data
          return { method: payload.method || data.method, params: payload.params || payload }
        })
        // Offers first, then answers, then ICE
        const ordered = [
          ...parsed.filter((m: any) => m.method === 'webrtc/offer'),
          ...parsed.filter((m: any) => m.method === 'webrtc/answer'),
          ...parsed.filter((m: any) => m.method === 'webrtc/ice'),
        ]
        for (const { method: m, params: p } of ordered) {
          if (m === 'webrtc/offer' && p.sdp) {
            rtcStatus.value[serial] = 'Got offer...'
            await pc.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: p.sdp }))
            const answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await api('/api/phone/webrtc-signal', {
              method: 'POST',
              body: JSON.stringify({ device: serial, method: 'webrtc/answer',
                params: { sdp: pc.localDescription!.sdp, sessionId: p.sessionId || sessionId } })
            })
            rtcStatus.value[serial] = 'Connecting...'
          } else if (m === 'webrtc/answer' && p.sdp) {
            await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: p.sdp }))
          } else if (m === 'webrtc/ice' && p.candidate && pc.remoteDescription) {
            await pc.addIceCandidate(new RTCIceCandidate({ candidate: p.candidate, sdpMid: p.sdpãN·ÚÚ$z{-®éÜj×&v–âÖ&÷GFöÓ¢‡ƒ°Ğ¢FW‡B×G&ç6f÷&Ó¢WW&66S°Ğ§ĞĞ Ğ¢ò¢FWf–6R6VÆV7F÷"¢ğĞ¢æFWf–6R×&÷r°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢gƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ§ĞĞ Ğ¢æFWf–6R×6VÆV7B°Ğ¢fÆWƒ¢°Ğ¢FF–æs¢g‚ƒ°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢föçB×6—¦S¢'ƒ°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ“°Ğ§ĞĞ Ğ¢ææ–6¶æÖR×&÷r°Ğ¢Ö&v–â×F÷¢gƒ°Ğ§ĞĞ Ğ¢ææ–6¶æÖRÖVF—B°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢Gƒ°Ğ§ĞĞ Ğ¢ææ–6¶æÖRÖ–çWB°Ğ¢fÆWƒ¢°Ğ¢FF–æs¢G‚‡ƒ°Ğ¢&÷&FW"×&F—W3¢Wƒ°Ğ¢föçB×6—¦S¢'ƒ°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ“°Ğ§ĞĞ Ğ¢ò¢6öçG&öÂ'WGFöç2¢ğĞ¢æ7G&ÂÖ'Fâ°Ğ¢FF–æs¢W‚ƒ°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢c°Ğ¢7W'6÷#¢ö–çFW#°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖ6&B“°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ¢G&ç6—F–öã¢ÆÂã'3°Ğ¢v†—FR×76S¢æ÷w&°Ğ§ĞĞ¢æ7G&ÂÖ'Fã¦†÷fW"²&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ66VçB“²6öÆ÷#¢f"‚Ò×FW‡BÓ“²ĞĞ¢æ7G&ÂÖ'Fã¦F—6&ÆVB°Ğ¢7W'6÷#¢æ÷BÖÆÆ÷vVC°Ğ¢÷6—G“¢ãSS°Ğ§ĞĞ Ğ¢æ7G&ÂÖ'FâÒ×vV''F2²&6¶w&÷VæC¢3VVS“²6öÆ÷#¢6ffc²&÷&FW"Ö6öÆ÷#¢3VVS“²ĞĞ¢æ7G&ÂÖ'FâÒ×vV''F3¦†÷fW"²&6¶w&÷VæC¢3#ƒF3s²&÷&FW"Ö6öÆ÷#¢3#ƒF3s²ĞĞ¢æ7G&ÂÖ'FâÒÖÖ§Vr²&6¶w&÷VæC¢f"‚ÒÖ66VçB“²6öÆ÷#¢6ffc²&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ66VçB“²ĞĞ¢æ7G&ÂÖ'FâÒÖÖ§Vs¦†÷fW"²&6¶w&÷VæC¢3FcCfSS²&÷&FW"Ö6öÆ÷#¢3FcCfSS²ĞĞ¢æ7G&ÂÖ'FâÒ×7F÷²&÷&FW"Ö6öÆ÷#¢3CsSSc“²6öÆ÷#¢f"‚Ò×FW‡BÓ2“²ĞĞ¢æ7G&ÂÖ'FâÒÖ6öæf—&Ò²6öÆ÷#¢33FC3““²&÷&FW"Ö6öÆ÷#¢33FC3““²ĞĞ¢æ7G&ÂÖ'FâÒÖf—‚²&6¶w&÷VæC¢6cS–S#²6öÆ÷#¢3²&÷&FW#¢æöæS²föçB×6—¦S¢—ƒ²FF–æs¢'‚gƒ²ĞĞ¢æ7G&ÂÖ'FâÒÖf—ƒ¦F—6&ÆVBÀĞ¢æ‡rÖ¶W’Ö'Fã¦F—6&ÆVB°Ğ¢7W'6÷#¢v—C°Ğ¢÷6—G“¢ãcS°Ğ§ĞĞ¢æ7G&ÂÖ'FâÒ×&V6÷&B°Ğ¢&÷&FW"Ö6öÆ÷#¢3vcCC°Ğ¢6öÆ÷#¢6f6VS°Ğ¢&6¶w&÷VæC¢3cƒ°Ğ§ĞĞ¢æ7G&ÂÖ'FâÒ×&V6÷&C¦†÷fW#¦æ÷Bƒ¦F—6&ÆVB’°Ğ¢&÷&FW"Ö6öÆ÷#¢6VcCCCC°Ğ¢6öÆ÷#¢6fV66°Ğ§ĞĞ¢æ7G&ÂÖ'FâÒ×&V6÷&BÖ7F—fR°Ğ¢&6¶w&÷VæC¢6VcCCCC33°Ğ¢&÷&FW"Ö6öÆ÷#¢6VcCCCCcc°Ğ¢6öÆ÷#¢6fV66°Ğ§ĞĞ¢æ7G&ÂÖ'FâÒ×&V6÷&BÖÆ–æ²°Ğ¢&÷&FW"Ö6öÆ÷#¢3cFSc3°Ğ¢6öÆ÷#¢3cvS†c“°Ğ¢&6¶w&÷VæC¢3ƒ&cC“°Ğ¢FW‡BÖFV6÷&F–öã¢æöæS°Ğ§ĞĞ Ğ¢æ7G&ÂÖ'FâÒ×F–ç’²föçB×6—¦S¢—ƒ²FF–æs¢'‚gƒ²ĞĞ Ğ¢ç&V6÷&F–ær×7FGW2ÖÆ–æRÀĞ¢æ×VÇF’×&V6÷&F–ær×7FGW2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢Wƒ°Ğ¢Ö–âÖ†V–v‡C¢‡ƒ°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ§ĞĞ Ğ¢ç&V6÷&F–ær×7FGW2ÖÆ–æR°Ğ¢FF–æs¢gƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ§ĞĞ Ğ¢æ×VÇF’×&V6÷&F–ær×7FGW2°Ğ¢FF–æs¢'‚g‚°Ğ¢föçB×6—¦S¢‡ƒ°Ğ§ĞĞ Ğ¢ç&V6÷&F–ærÖF÷B°Ğ¢v–GFƒ¢gƒ°Ğ¢†V–v‡C¢gƒ°Ğ¢&÷&FW"×&F—W3¢SS°Ğ¢&6¶w&÷VæC¢6VcCCCC°Ğ¢&÷‚×6†F÷s¢'‚3vcCCSS°Ğ¢fÆW‚×6‡&–æ³¢°Ğ§ĞĞ Ğ¢ææWw2×æVÂ°Ğ¢Ö&v–ã¢Gƒ°Ğ¢FF–æs¢‡ƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&÷&FW"×&F—W3¢‡ƒ°Ğ¢&6¶w&÷VæC¢3cc°Ğ¢fÆW‚×6‡&–æ³¢°Ğ¢Ö‚Ö†V–v‡C¢#cƒ°Ğ¢÷fW&fÆ÷r×“¢WFó°Ğ§ĞĞ Ğ¢ææWw2×æVÂÖ†VB°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢gƒ°Ğ¢Ö&v–âÖ&÷GFöÓ¢gƒ°Ğ§ĞĞ Ğ¢ææWw2×F—FÆR°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢s°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ§ĞĞ Ğ¢ææWw2×æVÂÖ†VBæ7G&ÂÖ'Fâ°Ğ¢Ö&v–âÖÆVgC¢WFó°Ğ§ĞĞ Ğ¢ææWw2Ö6öçG&öÇ2°Ğ¢F—7Æ“¢w&–C°Ğ¢w&–B×FV×ÆFRÖ6öÇVÖç3¢Ö–æÖ‚ƒÂã&g"’Ö–æÖ‚ƒÂg"’C'‚C'‚C‡ƒ°Ğ¢v¢Gƒ°Ğ§ĞĞ Ğ¢ææWw2Ö–çWBÀĞ¢ææWw2ÖçVÖ&W"°Ğ¢Ö–â×v–GFƒ¢°Ğ¢FF–æs¢G‚gƒ°Ğ¢&÷&FW"×&F—W3¢Wƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&6¶w&÷VæC¢3s#°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ¢föçB×6—¦S¢—ƒ°Ğ§ĞĞ Ğ¢ææWw2Ö–çWBÒÖ÷WB°Ğ¢w&–BÖ6öÇVÖã¢òÓ°Ğ§ĞĞ Ğ¢ææWw2×FövvÆR°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢§W7F–g’Ö6öçFVçC¢6VçFW#°Ğ¢v¢7ƒ°Ğ¢Ö–â×v–GFƒ¢°Ğ¢FF–æs¢G‚Wƒ°Ğ¢&÷&FW"×&F—W3¢Wƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&6¶w&÷VæC¢3s#°Ğ¢6öÆ÷#¢3“F6#ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢v†—FR×76S¢æ÷w&°Ğ§ĞĞ Ğ¢ææWw2×FövvÆR–çWB°Ğ¢v–GFƒ¢ƒ°Ğ¢†V–v‡C¢ƒ°Ğ¢66VçBÖ6öÆ÷#¢3c3cfc°Ğ§ĞĞ Ğ¢ææWw2×7FGW2°Ğ¢Ö&v–â×F÷¢gƒ°Ğ¢FF–æs¢G‚gƒ°Ğ¢&÷&FW"×&F—W3¢Wƒ°Ğ¢&6¶w&÷VæC¢3ƒ#s°Ğ¢6öÆ÷#¢3“F6#ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ§ĞĞ Ğ¢ææWw2×7FGW2ÒÖW'&÷"°Ğ¢&6¶w&÷VæC¢36cC#c°Ğ¢6öÆ÷#¢6f6VS°Ğ¢v†—FR×76S¢æ÷&ÖÃ°Ğ§ĞĞ Ğ¢ææWw2×&W7VÇB°Ğ¢Ö&v–â×F÷¢gƒ°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°Ğ¢v¢Wƒ°Ğ§ĞĞ Ğ¢ææWw2×7VÖÖ'’ÀĞ¢ææWw2ÖWf–FVæ6RÀĞ¢ææWw2Ö'F–f7G2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢gƒ°Ğ¢fÆW‚×w&¢w&°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢föçB×6—¦S¢—ƒ°Ğ§ĞĞ Ğ¢ææWw2×–ÆÂ°Ğ¢FF–æs¢‚Wƒ°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢föçB×6—¦S¢‡ƒ°Ğ¢föçB×vV–v‡C¢s°Ğ§ĞĞ Ğ¢ææWw2×–ÆÂÒÖö²°Ğ¢&6¶w&÷VæC¢3CS3&C°Ğ¢6öÆ÷#¢3ƒfVf3°Ğ§ĞĞ Ğ¢ææWw2×–ÆÂÒÖW'&÷"°Ğ¢&6¶w&÷VæC¢3vcCC°Ğ¢6öÆ÷#¢6fV66°Ğ§ĞĞ Ğ¢ææWw2ÖWf–FVæ6R7â°Ğ¢FF–æs¢'‚Wƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢&6¶w&÷VæC¢3s#°Ğ¢6öÆ÷#¢3cvS†c“°Ğ§ĞĞ Ğ¢ææWw2Ö'F–f7G27â°Ğ¢Ö‚×v–GFƒ¢S°Ğ¢FF–æs¢'‚Wƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢&6¶w&÷VæC¢3ƒ#s°Ğ¢6öÆ÷#¢6V#Ff3°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ§ĞĞ Ğ¢ææWw2ÖÆ—7BÀĞ¢ææWw2Ö'F–6ÆW2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°Ğ¢v¢Gƒ°Ğ§ĞĞ Ğ¢ææWw2Ö†VFÆ–æRÀĞ¢ææWw2Ö'F–6ÆR°Ğ¢FF–æs¢W‚gƒ°Ğ¢&÷&FW#¢‚6öÆ–B3S#“6#°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢&6¶w&÷VæC¢3s#°Ğ§ĞĞ Ğ¢ææWw2Ö†VFÆ–æRÀĞ¢ææWw2Ö'F–6ÆR×F—FÆR°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ¢föçB×6—¦S¢ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ã3S°Ğ§ĞĞ Ğ¢ææWw2Ö'F–6ÆRÖÖWF°Ğ¢Ö&v–â×F÷¢'ƒ°Ğ¢6öÆ÷#¢3cCsC†#°Ğ¢föçB×6—¦S¢‡ƒ°Ğ§ĞĞ Ğ¢ææWw2Ö'F–6ÆRÖ&öG’ÀĞ¢ææWw2Ö'F–6ÆRÖW'&÷"°Ğ¢Ö&v–â×F÷¢Gƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ãC°Ğ¢Ö‚Ö†V–v‡C¢S‡ƒ°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢v†—FR×76S¢&RÖÆ–æS°Ğ§ĞĞ Ğ¢ææWw2Ö'F–6ÆRÖW'&÷"°Ğ¢6öÆ÷#¢6f6VS°Ğ§ĞĞ Ğ¢æ'FâÖw&–B°Ğ¢F—7Æ“¢w&–C°Ğ¢w&–B×FV×ÆFRÖ6öÇVÖç3¢g"g#°Ğ¢v¢gƒ°Ğ§ĞĞ Ğ¢ç7G&VÒ×7FGW2ÖÆ–æR°Ğ¢Ö&v–â×F÷¢gƒ°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢gƒ°Ğ§ĞĞ Ğ¢ç7G&VÒ×7FGW2×FW‡B°Ğ¢föçB×6—¦S¢ƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ§ĞĞ Ğ¢ò¢†&Gv&R¶W—2w&–B¢ğĞ¢æ‡rÖ¶W—2Öw&–B°Ğ¢F—7Æ“¢w&–C°Ğ¢w&–B×FV×ÆFRÖ6öÇVÖç3¢g"g"g"g#°Ğ¢v¢7ƒ°Ğ§ĞĞ¢æ‡rÖ¶W—2Öw&–Bæ7G&ÂÖ'Fâ°Ğ¢FF–æs¢G‚'ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ§ĞĞ Ğ¢ò¢Æörf–ÇFW"&÷r¢ğĞ¢æÆörÖf–ÇFW"×&÷r°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢7ƒ°Ğ¢Ö&v–âÖ&÷GFöÓ¢gƒ°Ğ¢fÆW‚×w&¢w&°Ğ§ĞĞ Ğ¢æÆörÖf–ÇFW"Ö'Fâ°Ğ¢FF–æs¢'‚‡ƒ°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢S°Ğ¢7W'6÷#¢ö–çFW#°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢G&ç6—F–öã¢ÆÂã'3°Ğ§ĞĞ¢æÆörÖf–ÇFW"Ö'Fâæ7F—fR°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ66VçB“°Ğ¢6öÆ÷#¢6ffc°Ğ¢&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ66VçB“°Ğ¢föçB×vV–v‡C¢s°Ğ§ĞĞ Ğ¢æÆör×67&öÆÂ°Ğ¢fÆWƒ¢°Ğ¢Ö–âÖ†V–v‡C¢cƒ°Ğ¢Ö‚Ö†V–v‡C¢ƒƒ°Ğ¢÷fW&fÆ÷r×“¢WFó°Ğ¢FF–æs¢g‚‡ƒ°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢föçBÖfÖ–Ç“¢t6÷W&–W"æWrrÂÖöæ÷76S°Ğ¢föçB×6—¦S¢ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ãc°Ğ§ĞĞ¢æÆör×67&öÆÂÒÖ&÷B²6öÆ÷#¢3#“ƒ²ĞĞ Ğ¢æÆörÖÆ–æR°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ¢v÷&BÖ'&V³¢'&V²ÖÆÃ°Ğ§ĞĞ Ğ¢æÆörÖV×G’°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ¢föçB×7G–ÆS¢—FÆ–3°Ğ§ĞĞ Ğ¢ò¢&÷BÆör6VÆV7B¢ğĞ¢æ&÷BÖÆör×6VÆV7B°Ğ¢v–GFƒ¢S°Ğ¢föçB×6—¦S¢ƒ°Ğ¢FF–æs¢G‚‡ƒ°Ğ¢Ö&v–âÖ&÷GFöÓ¢gƒ°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢&÷&FW"×&F—W3¢Wƒ°Ğ§ĞĞ Ğ¢ò¢&Æ6²67&VVâv&æ–ær¢ğĞ¢æ&Æ6²×v&æ–ær°Ğ¢÷6—F–öã¢'6öÇWFS°Ğ¢F÷¢‡ƒ°Ğ¢ÆVgC¢SS°Ğ¢G&ç6f÷&Ó¢G&ç6ÆFU‚‚ÓSR“°Ğ¢&6¶w&÷VæC¢6cS–S&VS°Ğ¢6öÆ÷#¢3°Ğ¢FF–æs¢g‚Gƒ°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢c°Ğ¢¢Ö–æFWƒ¢°Ğ¢ö–çFW"ÖWfVçG3¢WFó°Ğ¢v†—FR×76S¢æ÷w&°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢‡ƒ°Ğ¢æ–ÖF–öã¢fFT–ä÷WBg2V6RÖ–âÖ÷WBf÷'v&G3°Ğ§ĞĞ¢æ&Æ6²×v&æ–ærÒÖ6ö×7B°Ğ¢FF–æs¢G‚ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢v¢gƒ°Ğ§ĞĞ Ğ¢æ&Æ6²×v&æ–ærÖ'Fâ°Ğ¢&6¶w&÷VæC¢3°Ğ¢6öÆ÷#¢6cS–S#°Ğ¢&÷&FW#¢æöæS°Ğ¢FF–æs¢'‚‡ƒ°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢s°Ğ¢7W'6÷#¢ö–çFW#°Ğ§ĞĞ Ğ¢ò¢:.(	Ş(*Ì:.(	Ş(*Âg&÷¦Vâ7G&VÒ÷fW&Æ’:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Â¢ğĞ¢æg&÷¦VâÖ÷fW&Æ’°Ğ¢÷6—F–öã¢'6öÇWFS²–ç6WC¢°Ğ¢F—7Æ“¢fÆWƒ²fÆW‚ÖF—&V7F–öã¢6öÇVÖã²Æ–vâÖ—FV×3¢6VçFW#²§W7F–g’Ö6öçFVçC¢6VçFW#°Ğ¢&6¶w&÷VæC¢&v&ƒÂRÂ"ÂãƒR“°Ğ¢&6¶G&÷Öf–ÇFW#¢&ÇW"ƒG‚“°Ğ¢7W'6÷#¢ö–çFW#²¢Ö–æFWƒ¢°Ğ¢&÷&FW"×&F—W3¢–æ†W&—C°Ğ§ĞĞ¢æg&÷¦VâÖv†÷7B²föçB×6—¦S¢C‡ƒ²Ö&v–âÖ&÷GFöÓ¢‡ƒ²÷6—G“¢ã“²ĞĞ¢æg&÷¦Vâ×FW‡B²föçB×6—¦S¢Gƒ²föçB×vV–v‡C¢s²6öÆ÷#¢6cS–S#²ÆWGFW"×76–æs¢ãWƒ²ĞĞ¢æg&÷¦VâÖ†–çB²föçB×6—¦S¢ƒ²6öÆ÷#¢3†–†C²Ö&v–â×F÷¢Gƒ²ĞĞ Ğ¢ò¢:.(	Ş(*Ì:.(	Ş(*Â×VÇF’FWf–6RÆ–÷WB:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Ì:.(	Ş(*Â¢ğĞ¢æ×VÇF’Ö†VFW"°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢‡ƒ°Ğ¢Ö&v–âÖ&÷GFöÓ¢'ƒ°Ğ¢fÆW‚×w&¢w&°Ğ§ĞĞ Ğ¢æFWf–6RÖ6÷VçB°Ğ¢Ö&v–âÖÆVgC¢WFó°Ğ¢föçB×6—¦S¢ƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ§ĞĞ Ğ¢æ×VÇF’Öw&–B°Ğ¢F—7Æ“¢w&–C°Ğ¢v¢‡ƒ°Ğ¢†V–v‡C¢6Æ2ƒf‚Òƒ‚“°Ğ§ĞĞ Ğ¢æ×VÇF’Ö6&B°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖ6&B“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢&÷&FW"×&F—W3¢‡ƒ°Ğ¢Ö–âÖ†V–v‡C¢°Ğ§ĞĞ Ğ¢æ×VÇF’Ö6&BÖ†VFW"°Ğ¢FF–æs¢g‚ƒ°Ğ¢&÷&FW"Ö&÷GFöÓ¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢gƒ°Ğ¢fÆW‚×6‡&–æ³¢°Ğ¢fÆW‚×w&¢w&°Ğ§ĞĞ Ğ¢æ×VÇF’ÖFWf–6RÖæÖR°Ğ¢föçB×6—¦S¢ƒ°Ğ¢föçB×vV–v‡C¢s°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ§ĞĞ Ğ¢æ†VÇF‚ÖF÷G2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢7ƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢Ö&v–âÖÆVgC¢Gƒ°Ğ§ĞĞ¢æ†VÇF‚ÖF÷B°Ğ¢v–GFƒ¢gƒ°Ğ¢†V–v‡C¢gƒ°Ğ¢&÷&FW"×&F—W3¢SS°Ğ¢F—7Æ“¢–æÆ–æRÖ&Æö6³°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×æVÂ°Ğ¢Ö&v–ã¢G‚Gƒ°Ğ¢FF–æs¢‡‚ƒ°Ğ¢&÷&FW#¢‚6öÆ–B6cS–S#CC°Ğ¢&6¶w&÷VæC¢3cs&°Ğ¢&÷&FW"×&F—W3¢gƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ"“°Ğ¢föçB×6—¦S¢ƒ°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö†VB°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢v¢gƒ°Ğ¢Ö&v–âÖ&÷GFöÓ¢Gƒ°Ğ¢Ö–â×v–GFƒ¢°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×7FFR°Ğ¢6öÆ÷#¢6f&&c#C°Ğ¢föçB×vV–v‡C¢s°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö6öFR°Ğ¢6öÆ÷#¢6fVCv°Ğ¢&÷&FW#¢‚6öÆ–B6cS–S#SS°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢FF–æs¢‚Wƒ°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’ÖÆ–æ²°Ğ¢Ö&v–âÖÆVgC¢WFó°Ğ¢6öÆ÷#¢3“63VfC°Ğ¢&6¶w&÷VæC¢G&ç7&VçC°Ğ¢&÷&FW#¢æöæS°Ğ¢7W'6÷#¢ö–çFW#°Ğ¢föçB×6—¦S¢ƒ°Ğ¢FF–æs¢°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×7VÖÖ'’°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢Æ–æRÖ†V–v‡C¢ã3S°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×7VÖÖ'’Ö–æÆ–æR°Ğ¢fÆWƒ¢°Ğ¢Ö–â×v–GFƒ¢°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢föçB×6—¦S¢ƒ°Ğ¢÷6—G“¢ãƒS°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’ÖÆ–æ²ÒÖf—‚°Ğ¢Ö&v–âÖÆVgC¢°Ğ¢6öÆ÷#¢3fVSv#s°Ğ¢föçB×vV–v‡C¢s°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’ÖFWF–Ç2°Ğ¢Ö&v–â×F÷¢gƒ°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×7FGW2°Ğ¢Ö&v–â×F÷¢Gƒ°Ğ¢6öÆ÷#¢3“63VfC°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ã3°Ğ§ĞĞ Ğ¢æ–÷2Ö†VÇF‚ÖFWF–Ç2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚×w&¢w&°Ğ¢v¢Gƒ°Ğ¢Ö&v–â×F÷¢gƒ°Ğ§ĞĞ Ğ¢æ–÷2Ö†VÇF‚Ö6†—°Ğ¢Ö‚×v–GFƒ¢S°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ¢FF–æs¢'‚Wƒ°Ğ¢&÷&FW#¢‚6öÆ–B333CSS°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢&6¶w&÷VæC¢3#cs°Ğ¢6öÆ÷#¢3“F6#ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ§ĞĞ Ğ¢æ–÷2Ö†VÇF‚Ö6†—ÒÖö²°Ğ¢&÷&FW"Ö6öÆ÷#¢3ccS3Ccc°Ğ¢6öÆ÷#¢3ƒfVf3°Ğ¢&6¶w&÷VæC¢3S&Sc##°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’×7FW2°Ğ¢Ö&v–ã¢W‚°Ğ¢FF–ærÖÆVgC¢gƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ¢Æ–æRÖ†V–v‡C¢ã3S°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö6öÖÖæG2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°Ğ¢v¢Gƒ°Ğ¢Ö&v–â×F÷¢gƒ°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö6öÖÖæB°Ğ¢F—7Æ“¢w&–C°Ğ¢w&–B×FV×ÆFRÖ6öÇVÖç3¢Ö–æÖ‚ƒÂg"’WFó°Ğ¢v¢gƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö6öÖÖæB6öFR°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢FW‡BÖ÷fW&fÆ÷s¢VÆÆ—6—3°Ğ¢v†—FR×76S¢æ÷w&°Ğ¢FF–æs¢G‚gƒ°Ğ¢&÷&FW#¢‚6öÆ–B333CSS°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢&6¶w&÷VæC¢3#cs°Ğ¢6öÆ÷#¢63F#VfC°Ğ¢föçB×6—¦S¢—ƒ°Ğ§ĞĞ Ğ¢æ–÷2Ö6÷’Ö'Fâ°Ğ¢FF–æs¢7‚gƒ°Ğ¢&÷&FW#¢‚6öÆ–B333CSS°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢&6¶w&÷VæC¢3ƒ#s°Ğ¢6öÆ÷#¢3“63VfC°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢7W'6÷#¢ö–çFW#°Ğ§ĞĞ Ğ¢æ–÷2Ö6÷’Ö'Fã¦†÷fW"°Ğ¢&÷&FW"Ö6öÆ÷#¢3cVf°Ğ¢6öÆ÷#¢6&fF&fS°Ğ§ĞĞ Ğ¢æ–÷2×&V6÷fW'’Ö6ö×7B°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢gƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢FF–æs¢7‚gƒ°Ğ¢&÷&FW"×F÷¢‚6öÆ–B6cS–S#33°Ğ¢&6¶w&÷VæC¢6cS–S##°Ğ¢6öÆ÷#¢6f&&c#C°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ã#°Ğ§ĞĞ Ğ¢æ×VÇF’Ö‡rÖ¶W—2°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢'ƒ°Ğ¢Ö&v–âÖÆVgC¢Gƒ°Ğ§ĞĞ Ğ¢æ‡rÖ¶W’Ö'Fâ°Ğ¢FF–æs¢'‚Wƒ°Ğ¢&6¶w&÷VæC¢f"‚ÒÖ&rÖFVW“°Ğ¢&÷&FW#¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢&÷&FW"×&F—W3¢Gƒ°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓ2“°Ğ¢föçB×6—¦S¢ƒ°Ğ¢7W'6÷#¢ö–çFW#°Ğ¢G&ç6—F–öã¢&÷&FW"Ö6öÆ÷"ã'3°Ğ§ĞĞ¢æ‡rÖ¶W’Ö'Fã¦†÷fW"²&÷&FW"Ö6öÆ÷#¢f"‚ÒÖ66VçB“²ĞĞ Ğ¢æ×VÇF’×7G&VÒÖ'Fç2°Ğ¢Ö&v–âÖÆVgC¢WFó°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢v¢7ƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ§ĞĞ Ğ¢æ×VÇF’ÖÖöFRÖ&FvR°Ğ¢föçB×6—¦S¢‡ƒ°Ğ¢FF–æs¢‚Wƒ°Ğ¢&÷&FW"×&F—W3¢7ƒ°Ğ§ĞĞ Ğ¢ò¢7G&VÒ&V¢ğĞ¢æ×VÇF’×7G&VÒÖ&V°Ğ¢÷6—F–öã¢&VÆF—fS°Ğ¢fÆWƒ¢C°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢§W7F–g’Ö6öçFVçC¢6VçFW#°Ğ¢&6¶w&÷VæC¢3s#°Ğ¢Ö–âÖ†V–v‡C¢°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ¢÷6—F–öã¢&VÆF—fS°Ğ§ĞĞ Ğ¢æ×VÇF’×7G&VÒÖÖVF–°Ğ¢Ö‚Ö†V–v‡C¢S°Ğ¢Ö‚×v–GFƒ¢S°Ğ¢ö&¦V7BÖf—C¢6öçF–ã°Ğ¢7W'6÷#¢7&÷76†—#°Ğ¢F÷V6‚Ö7F–öã¢æöæS°Ğ¢W6W"×6VÆV7C¢æöæS°Ğ§ĞĞ Ğ¢æ×VÇF’×7G&VÒ×Æ6V†öÆFW"°Ğ¢6öÆ÷#¢333CSS°Ğ¢föçB×6—¦S¢ƒ°Ğ§ĞĞ Ğ¢ò¢W"ÖFWf–6RÆöw2¢ğĞ¢æ×VÇF’ÖÆöw2Ö&V°Ğ¢fÆWƒ¢°Ğ¢&÷&FW"×F÷¢‚6öÆ–Bf"‚ÒÖ&÷&FW"“°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢fÆW‚ÖF—&V7F–öã¢6öÇVÖã°Ğ¢&6¶w&÷VæC¢3Sc°Ğ¢Ö–âÖ†V–v‡C¢°Ğ¢÷fW&fÆ÷s¢†–FFVã°Ğ§ĞĞ Ğ¢æ×VÇF’ÖÆöw2Ö†VFW"°Ğ¢FF–æs¢7‚‡ƒ°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢föçB×vV–v‡C¢c°Ğ¢6öÆ÷#¢3#&3SVS°Ğ¢&÷&FW"Ö&÷GFöÓ¢‚6öÆ–B3c#°Ğ¢fÆW‚×6‡&–æ³¢°Ğ¢&6¶w&÷VæC¢3s#“°Ğ§ĞĞ Ğ¢æ×VÇF’ÖÆöw2×67&öÆÂ°Ğ¢fÆWƒ¢°Ğ¢÷fW&fÆ÷r×“¢WFó°Ğ¢FF–æs¢G‚gƒ°Ğ¢föçBÖfÖ–Ç“¢t6÷W&–W"æWrrÂÖöæ÷76S°Ğ¢föçB×6—¦S¢—ƒ°Ğ¢Æ–æRÖ†V–v‡C¢ãS°Ğ§ĞĞ Ğ¢æ×VÇF’ÖÆörÖÆ–æR°Ğ¢FF–ærÖÆVgC¢gƒ°Ğ§ĞĞ Ğ¢æ×VÇF’ÖÆörÖV×G’°Ğ¢6öÆ÷#¢33#°Ğ¢föçB×7G–ÆS¢—FÆ–3°Ğ§ĞĞ Ğ¢æ×VÇF’ÖV×G’°Ğ¢F—7Æ“¢fÆWƒ°Ğ¢Æ–vâÖ—FV×3¢6VçFW#°Ğ¢§W7F–g’Ö6öçFVçC¢6VçFW#°Ğ¢6öÆ÷#¢f"‚Ò×FW‡BÓB“°Ğ¢föçB×6—¦S¢'ƒ°Ğ¢FF–æs¢C‚°Ğ§ĞĞ£Â÷7G–ÆSàĞ 