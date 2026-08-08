<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '@/composables/useApi'
import PhoneStreamWidget from '@/components/PhoneStreamWidget.vue'

interface SkillAction { name: string; description: string }
interface SkillWorkflow { name: string; description: string }
interface PopupDetector { detect: string; button: string; label: string; method?: string; notes?: string }
interface SkillInfo {
  dir: string; name: string; version: string; app_package: string | null
  android_package?: string | null; ios_bundle_id?: string | null
  platforms?: string[]; supports_android?: boolean; supports_ios?: boolean
  description: string; actions: string[] | SkillAction[]; workflows: string[] | SkillWorkflow[]
  elements_count: number; elements_ios_count?: number; popup_count?: number; popup_detectors?: PopupDetector[]
  metadata: any; default_params?: Record<string, Record<string, any>>
  kind?: 'hard' | 'soft'; has_guidance?: boolean
}
interface SkillDetail extends SkillInfo {
  elements: Record<string, any>[]
  guidance?: string
}

const skills = ref<SkillInfo[]>([])
const selected = ref<SkillDetail | null>(null)
const loading = ref(false)
const searchQuery = ref('')
const HIDDEN_SKILLS = new Set(['tiktok', 'tiktok_ios'])
const visibleSkills = computed(() => skills.value.filter(s => !HIDDEN_SKILLS.has((s.dir || s.name || '').toLowerCase())))
const filteredSkills = computed(() => {
  const q = searchQuery.value.toLowerCase()
  if (!q) return visibleSkills.value
  return visibleSkills.value.filter(s =>
    (s.name || s.dir || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.app_package || '').toLowerCase().includes(q) ||
    (s.android_package || '').toLowerCase().includes(q) ||
    (s.ios_bundle_id || '').toLowerCase().includes(q)
  )
})
const devices = ref<{serial: string; nickname?: string; platform?: string; status?: string; status_message?: string}[]>([])
const runModal = ref(false)
const runTarget = ref({ type: '', name: '' })
const runDevice = ref('')
const runParams = ref('{}')
const runResult = ref('')

const ICONS: Record<string, string> = {
  tiktok: 'Ã°Å¸Å½Âµ', instagram: 'Ã°Å¸â€œÂ¸', _base: 'Ã°Å¸Â§Â©', send_gmail_email: 'Ã°Å¸Â§Â©'
}

/* Ã¢â€â‚¬Ã¢â€â‚¬ compat tracking Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
interface CompatEntry {
  device_serial: string; skill_name: string; target_type: string; target_name: string
  app_version: string | null; status: string; last_run_at: string | null; last_error: string | null
  run_count: number; ok_count: number; fail_count: number; kind?: string
}
const compat = ref<CompatEntry[]>([])
const verifying = ref(false)
const verifyLog = ref('')

function compatFor(skill: string, device?: string): CompatEntry[] {
  return compat.value.filter(c => c.skill_name === skill && (!device || c.device_serial === device))
}
function compatStatus(skill: string, device: string): string {
  const entries = compatFor(skill, device)
  if (!entries.length) return 'untested'
  if (entries.every(c => c.status === 'ok')) return 'ok'
  if (entries.some(c => c.status === 'ok')) return 'partial'
  return 'fail'
}
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  ok: { bg: '#22c55e22', text: '#4ade80' },
  fail: { bg: '#ef444422', text: '#f87171' },
  partial: { bg: '#f59e0b22', text: '#fbbf24' },
  untested: { bg: '#64748b22', text: '#94a3b8' },
  unsupported: { bg: '#33415544', text: '#64748b' },
}

function devicePlatform(device: string | { serial: string; platform?: string } | undefined): 'android' | 'ios' {
  const serial = typeof device === 'string' ? device : (device?.serial || '')
  const platform = typeof device === 'string' ? '' : (device?.platform || '')
  return platform === 'ios' || serial.startsWith('ios:') ? 'ios' : 'android'
}

function skillSupportsDevice(skill: SkillInfo | null | undefined, device: string | { serial: string; platform?: string } | undefined): boolean {
  if (!skill || !device) return true
  const platforms = skill.platforms || []
  if (!platforms.length) return true
  return platforms.includes(devicePlatform(device))
}

function skillTargetLabel(skill: SkillInfo | null | undefined): string {
  if (!skill) return 'universal'
  if (skill.supports_ios && !skill.supports_android) return skill.ios_bundle_id || 'iOS app'
  if (skill.supports_android && !skill.supports_ios) return skill.android_package || skill.app_package || 'Android app'
  if (skill.supports_android && skill.supports_ios) return 'Android + iOS'
  return skill.app_package || skill.ios_bundle_id || 'universal'
}

function platformLabel(skill: SkillInfo | null | undefined): string {
  const platforms = skill?.platforms || []
  return platforms.length ? platforms.map(p => p.toUpperCase()).join(' / ') : 'ANDROID'
}

function skillDeviceStatus(skill: SkillInfo, device: string): string {
  if (!skillSupportsDevice(skill, device)) return 'unsupported'
  return compatStatus(skill.dir, device)
}

async function verifySkill(skillName: string, device: string) {
  if (!device) return
  if (!skillSupportsDevice(selected.value, device)) return
  verifying.value = true
  verifyLog.value = ''
  runDevice.value = device
  // Auto-start stream so user can watch the verification
  if (phoneWidget.value && !phoneWidget.value.streaming) phoneWidget.value.startStream()
  const sk = selected.value
  const wfNames = (sk?.workflows || []).map(w => typeof w === 'string' ? w : w.name)
  // Soft skills have no workflows Ã¢â‚¬â€ run a single smoke verify (backend ignores the
  // workflow arg for soft skills and treats verify as a smoke check).
  const toTest = wfNames.length ? wfNames : ['recorded']
  for (const wName of toTest) {
    verifyLog.value += `Testing ${wName}...\n`
    try {
      const res = await api(`/api/skills/${skillName}/verify`, {
        method: 'POST', body: JSON.stringify({ workflow: wName, device, params: {} })
      })
      verifyLog.value += res.ok ? `  Ã¢Å“â€¦ ${wName} passed\n` : `  Ã¢ÂÅ’ ${wName} failed: ${res.output?.slice(0, 200)}\n`
    } catch (e: any) {
      verifyLog.value += `  Ã¢ÂÅ’ ${wName} error: ${e.message}\n`
    }
  }
  verifying.value = false
  await loadCompat()
}

async function resetCompat(skill: string, device: string) {
  await api(`/api/skills/compat/${device}/${skill}`, { method: 'DELETE' })
  await loadCompat()
}

async function loadCompat() {
  try { compat.value = await api('/api/skills/compat') } catch { compat.value = [] }
}

/* Ã¢â€â‚¬Ã¢â€â‚¬ Checkpoint / awaiting-human gates Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
interface CheckpointInfo {
  reason: 'captcha' | 'sms' | 'email' | 'login' | 'generic'
  prompt: string
  success?: Record<string, any>
  timeout_s?: number
}
interface SkillRun {
  id: number
  device_serial: string
  skill_name: string
  status: string
  kind?: string
  checkpoint?: CheckpointInfo | null
}
const awaitingRuns = ref<SkillRun[]>([])
let awaitingTimer: ReturnType<typeof setInterval> | null = null

const REASON_LABELS: Record<string, string> = {
  captcha: 'CAPTCHA', sms: 'SMS CODE', email: 'EMAIL CODE', login: 'LOGIN / 2FA', generic: 'ACTION NEEDED'
}
function reasonLabel(cp?: CheckpointInfo | null): string {
  return REASON_LABELS[cp?.reason || 'generic'] || 'ACTION NEEDED'
}

async function loadAwaitingRuns() {
  try {
    const runs = await api<SkillRun[]>('/api/skills/runs?limit=50')
    awaitingRuns.value = (runs || []).filter(r => r.status === 'awaiting_human')
  } catch { /* transient poll failure Ã¢â‚¬â€ keep last known list */ }
}

async function resolveCheckpoint(run: SkillRun, action: 'resume' | 'abort') {
  // Optimistically remove so the banner disappears immediately.
  awaitingRuns.value = awaitingRuns.value.filter(r => r.id !== run.id)
  try {
    await api(`/api/skills/runs/${run.id}/resume`, {
      method: 'POST', body: JSON.stringify({ action })
    })
  } catch {
    // 409 = run already moved on, or transient error Ã¢â‚¬â€ just re-sync from server.
  }
  await loadAwaitingRuns()
}

async function load() {
  loading.value = true
  try {
    skills.value = await api('/api/skills')
    const devResp = await api('/api/phone/devices')
    devices.value = devResp.devices || devResp || []
    await loadCompat()
  } finally { loading.value = false }
}

const phoneWidget = ref<InstanceType<typeof PhoneStreamWidget> | null>(null)

async function showDetail(name: string) {
  const detail = await api<SkillDetail>(`/api/skills/${name}`)
  selected.value = detail
  // Push browser history so Back button works
  history.pushState({ skill: name }, '', `#skill/${name}`)
}

function back() {
  selected.value = null
  history.pushState(null, '', location.pathname)
}

function onPopState() {
  // Browser back button pressed
  if (selected.value) {
    selected.value = null
  }
}

function actionCount(s: SkillInfo) {
  return Array.isArray(s.actions) ? s.actions.length : 0
}
function workflowCount(s: SkillInfo) {
  return Array.isArray(s.workflows) ? s.workflows.length : 0
}

function openRun(type: 'workflow' | 'action', name: string) {
  runTarget.value = { type, name }
  const compatible = devices.value.find(d => skillSupportsDevice(selected.value, d))
  runDevice.value = compatible?.serial || devices.value[0]?.serial || ''
  runResult.value = ''
  // Pre-fill default params from skill metadata
  const dp = (selected.value as any)?.default_params as Record<string, any> | undefined
  const typeKey = type === 'workflow' ? 'workflows' : 'actions'
  const defaults = dp?.[typeKey]?.[name]
  runParams.value = defaults ? JSON.stringify(defaults, null, 2) : '{}'
  runModal.value = true
}

async function executeRun() {
  const skill = selected.value?.dir || selected.value?.name
  if (!skillSupportsDevice(selected.value, runDevice.value)) {
    runResult.value = `Unsupported: ${selected.value?.name || skill} does not support ${devicePlatform(runDevice.value)}`
    return
  }
  const endpoint = runTarget.value.type === 'workflow'
    ? `/api/skills/${skill}/run`
    : `/api/skills/${skill}/run-action`
  const body: any = { device: runDevice.value }
  body[runTarget.value.type] = runTarget.value.name
  try { body.params = JSON.parse(runParams.value) } catch { body.params = {} }
  // Auto-start stream on the selected device
  if (phoneWidget.value && !phoneWidget.value.streaming) phoneWidget.value.startStream()
  try {
    const res = await api(endpoint, { method: 'POST', body: JSON.stringify(body) })
    runResult.value = `Ã¢Å“â€¦ Enqueued Ã¢â‚¬â€ job_id: ${res.job_id || res.ok || JSON.stringify(res)}`
  } catch (e: any) {
    runResult.value = `Ã¢ÂÅ’ ${e.message}`
  }
}

async function deleteSkill(name: string) {
  if (!confirm(`Delete skill "${name}"? This cannot be undone.`)) return
  try {
    await api(`/api/skills/${name}`, { method: 'DELETE' })
    selected.value = null
    await load()
  } catch (e: any) {
    alert('Failed to delete: ' + e.message)
  }
}

function exportSkill(name: string) {
  window.open(`/api/skills/export/${name}`, '_blank')
}

/* Ã¢â€â‚¬Ã¢â€â‚¬ Hub / Browse tab Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
const hubTab = ref<'installed' | 'browse'>('installed')
const registry = ref<any[]>([])
const installing = ref<Record<string, boolean>>({})
const hubSearch = ref('')

async function loadRegistry() {
  try { registry.value = await api('/api/skills/registry') } catch { registry.value = [] }
}

async function installFromHub(name: string) {
  installing.value[name] = true
  try {
    await api('/api/skills/install', { method: 'POST', body: JSON.stringify({ name }) })
    await load() // refresh installed skills
  } catch (e: any) {
    alert('Install failed: ' + e.message)
  } finally {
    installing.value[name] = false
  }
}

const installedNames = computed(() => new Set(skills.value.map(s => s.dir || s.name)))

const filteredRegistry = computed(() => {
  const q = hubSearch.value.toLowerCase()
  if (!q) return registry.value
  return registry.value.filter((s: any) =>
    (s.name || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.app_package || '').toLowerCase().includes(q) ||
    (s.android_package || '').toLowerCase().includes(q) ||
    (s.ios_bundle_id || '').toLowerCase().includes(q)
  )
})

function switchTab(tab: 'installed' | 'browse') {
  hubTab.value = tab
  if (tab === 'browse' && registry.value.length === 0) {
    loadRegistry()
  }
}

onMounted(() => {
  load()
  loadAwaitingRuns()
  awaitingTimer = setInterval(loadAwaitingRuns, 3000)
  window.addEventListener('popstate', onPopState)
})
onUnmounted(() => {
  if (awaitingTimer) { clearInterval(awaitingTimer); awaitingTimer = null }
  window.removeEventListener('popstate', onPopState)
})
</script>

<template>
  <div class="sh-root">

    <!-- ============================================================ -->
    <!-- CHECKPOINT / AWAITING-HUMAN BANNERS                          -->
    <!-- ============================================================ -->
    <div v-if="awaitingRuns.length" class="sh-checkpoint-stack">
      <div v-for="run in awaitingRuns" :key="run.id" class="sh-checkpoint-banner">
        <span class="sh-checkpoint-icon">&#9208;</span>
        <div class="sh-checkpoint-body">
          <div class="sh-checkpoint-head">
            <span class="sh-checkpoint-reason">{{ reasonLabel(run.checkpoint) }}</span>
            <span class="sh-checkpoint-skill">{{ run.skill_name }}</span>
            <span class="sh-checkpoint-device">{{ run.device_serial }}</span>
          </div>
          <div class="sh-checkpoint-prompt">{{ run.checkpoint?.prompt || 'Waiting for a human to clear this gate.' }}</div>
        </div>
        <div class="sh-c÷N}¶‰Ëkºwµçh€±¥¹”µ¡•¥¡Ğè€Ä¸Øì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°-¥¹‰…‘”€¡¡…É€¼Í½™Ğ¤ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ­¥¹µ‰…‘”ì4(€™½¹ĞµÍ¥é”è€åÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÉÁà€áÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€äääåÁàì4(€±•ÑÑ•ÈµÍÁ…¥¹œè€À¸ÀÑ•´ì4)ô4(¹Í µ­¥¹µ‰…‘”´µ¡…Éì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°€ŒØÌØÙ˜Ä€ÄØ”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4(€½±½Èè€„ÕˆÑ™Œì4)ô4(¹Í µ­¥¹µ‰…‘”´µÍ½™Ğì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°€˜Ôå”Áˆ€ÄØ”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4(€½±½Èè€™‰‰˜ÈĞì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°Õ¥‘…¹”‰±½¬€¡Í½™ĞÍ­¥±±Ì¤ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µÕ¥‘…¹”ì4(€µ…É¥¸è€Àì4(€Á…‘‘¥¹œè€ÄÉÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€±¥¹”µ¡•¥¡Ğè€Ä¸ÔÔì4(€™½¹Ğµ™…µ¥±äèµ½¹½ÍÁ…”ì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ‘••À¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´È¤ì4(€İ¡¥Ñ”µÍÁ…”èÁÉ”µİÉ…Àì4(€İ½Éµ‰É•…¬è‰É•…¬µİ½Éì4(€µ…àµ¡•¥¡Ğè€ĞàÁÁàì4(€½Ù•É™±½Üè…ÕÑ¼ì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°•Ñ…¥°Ù¥•Üƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ‘•Ñ…¥°µ¡•…‘•Èì4(€µ…É¥¸µ‰½ÑÑ½´è€ÈÑÁàì4)ô4(¹Í µ‰…¬µ‰Ñ¸ì4(€‘¥ÍÁ±…äè¥¹±¥¹”µ™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€ÑÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ÔÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ì¤ì4(€‰…­É½Õ¹è¹½¹”ì4(€‰½É‘•Èè¹½¹”ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€Á…‘‘¥¹œè€ÑÁà€Àì4(€µ…É¥¸µ‰½ÑÑ½´è€ÄÙÁàì4(€ÑÉ…¹Í¥Ñ¥½¸è½±½È€À¸ÄÕÌì4)ô4(¹Í µ‰…¬µ‰Ñ¸é¡½Ù•Èì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4)ô4(¹Í µ‰…¬µ…ÉÉ½Üì4(€™½¹ĞµÍ¥é”è€ÄÑÁàì4)ô4(¹Í µ‘•Ñ…¥°µÑ¥Ñ±”µÉ½Üì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€ÄÑÁàì4(€µ…É¥¸µ‰½ÑÑ½´è€áÁàì4)ô4(¹Í µ‘•Ñ…¥°µ¥½¸ì4(€™½¹ĞµÍ¥é”è€ÌÉÁàì4(€±¥¹”µ¡•¥¡Ğè€Äì4)ô4(¹Í µ‘•Ñ…¥°µÑ¥Ñ±”µ‰±½¬ì4(€‘¥ÍÁ±…äè™±•àì4(€™±•àµ‘¥É•Ñ¥½¸è½±Õµ¸ì4(€…Àè€ÉÁàì4)ô4(¹Í µ‘•Ñ…¥°µ¹…µ”ì4(€™½¹ĞµÍ¥é”è€ÈÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4(€µ…É¥¸è€Àì4)ô4(¹Í µ‘•Ñ…¥°µµ•Ñ„ì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€áÁàì4)ô4(¹Í µÁ­œì4(€™½¹ĞµÍ¥é”è€ÄÅÁàì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ğ¤ì4(€™½¹Ğµ™…µ¥±äèµ½¹½ÍÁ…”ì4)ô4(¹Í µ‘•Ñ…¥°µ‘•ÍŒì4(€™½¹ĞµÍ¥é”è€ÄÍÁàì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´È¤ì4(€µ…É¥¸µÑ½Àè€áÁàì4(€±¥¹”µ¡•¥¡Ğè€Ä¸Ôì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°Qİ¼µ½±Õµ¸±…å½ÕĞƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ‘•Ñ…¥°µ½±Õµ¹Ìì4(€‘¥ÍÁ±…äèÉ¥ì4(€É¥µÑ•µÁ±…Ñ”µ½±Õµ¹Ìè€Í™È€É™Èì4(€…Àè€ÈÁÁàì4(€…±¥¸µ¥Ñ•µÌèÍÑ…ÉĞì4)ô4)µ•‘¥„€¡µ…àµİ¥‘Ñ è€àÀÁÁà¤ì4(€€¹Í µ‘•Ñ…¥°µ½±Õµ¹Ìì4(€€€É¥µÑ•µÁ±…Ñ”µ½±Õµ¹Ìè€Å™Èì4(€ô4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°M•Ñ¥½¹Ìƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µÍ•Ñ¥½¸ì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ…É¤ì4(€‰½É‘•Èè€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÄÁÁàì4(€Á…‘‘¥¹œè€ÄÙÁàì4(€µ…É¥¸µ‰½ÑÑ½´è€ÄÙÁàì4)ô4(¹Í µÍ•Ñ¥½¸´µ…Ñ¥½¹Ìì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€áÁàì4(€™±•àµİÉ…ÀèİÉ…Àì4)ô4(¹Í µÍ•Ñ¥½¸µÑ¥Ñ±”ì4(€™½¹ĞµÍ¥é”è€ÄÍÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4(€µ…É¥¸è€À€À€ÄÉÁàì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€áÁàì4)ô4(¹Í µ½Õ¹Ğµ‰…‘”ì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÅÁà€İÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€äääåÁàì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°Ù…È ´µ}…•¹Ğ¤€ÄØ”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4(€½±½ÈèÙ…È ´µ}…•¹Ğ¤ì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°1¥ÍĞÉ½İÌ€¡…Ñ¥½¹Ì€¼İ½É­™±½İÌ¤ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ±¥ÍĞì4(€‘¥ÍÁ±…äè™±•àì4(€™±•àµ‘¥É•Ñ¥½¸è½±Õµ¸ì4)ô4(¹Í µ±¥ÍĞµÉ½Üì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€©ÕÍÑ¥™äµ½¹Ñ•¹ĞèÍÁ…”µ‰•Ñİ••¸ì4(€…Àè€ÄÉÁàì4(€Á…‘‘¥¹œè€ÄÁÁà€ÄÉÁàì4(€‰½É‘•Èµ‰½ÑÑ½´è€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€ÑÉ…¹Í¥Ñ¥½¸è‰…­É½Õ¹€À¸ÄÉÌì4)ô4(¹Í µ±¥ÍĞµÉ½Üé±…ÍĞµ¡¥±ì4(€‰½É‘•Èµ‰½ÑÑ½´è¹½¹”ì4)ô4(¹Í µ±¥ÍĞµÉ½Üé¡½Ù•Èì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°Ù…È ´µ}…•¹Ğ¤€Ô”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4)ô4(¹Í µ±¥ÍĞµÉ½Ü´µ½µÁ…Ğì4(€Á…‘‘¥¹œè€áÁà€ÄÉÁàì4)ô4(¹Í µ±¥ÍĞµÉ½Ü´µİ½É­™±½Üì4(€Á…‘‘¥¹œè€ÄÉÁà€ÄÉÁàì4)ô4(¹Í µ±¥ÍĞµÉ½ÜµÑ•áĞì4(€‘¥ÍÁ±…äè™±•àì4(€™±•àµ‘¥É•Ñ¥½¸è½±Õµ¸ì4(€…Àè€ÉÁàì4(€µ¥¸µİ¥‘Ñ è€Àì4)ô4(¹Í µ±¥ÍĞµÉ½Üµ¹…µ”ì4(€™½¹ĞµÍ¥é”è€ÄÍÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4)ô4(¹Í µ±¥ÍĞµÉ½Üµ‘•ÍŒì4(€™½¹ĞµÍ¥é”è€ÄÅÁàì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ğ¤ì4(€½Ù•É™±½Üè¡¥‘‘•¸ì4(€Ñ•áĞµ½Ù•É™±½Üè•±±¥ÁÍ¥Ìì4(€İ¡¥Ñ”µÍÁ…”è¹½İÉ…Àì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°IÕ¸‰ÕÑÑ½¹Ìƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µÉÕ¸µ‰Ñ¸ì4(€™±•àµÍ¡É¥¹¬è€Àì4(€Á…‘‘¥¹œè€ÕÁà€ÄÉÁàì4(€™½¹ĞµÍ¥é”è€ÄÅÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€‰½É‘•Èè¹½¹”ì4(€‰…­É½Õ¹èÙ…È ´µ}…•¹Ğ¤ì4(€½±½Èè€™™˜ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è½Á…¥Ñä€À¸ÄÕÌì4)ô4(¹Í µÉÕ¸µ‰Ñ¸é¡½Ù•Èì4(€½Á…¥Ñäè€À¸àÔì4)ô4(¹Í µÉÕ¸µ‰Ñ¸´µÍµ…±°ì4(€Á…‘‘¥¹œè€ÑÁà€ÄÁÁàì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°½µÁ…ĞÍ•Ñ¥½¸ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ½µÁ…Ğµ±¥ÍĞì4(€‘¥ÍÁ±…äè™±•àì4(€™±•àµ‘¥É•Ñ¥½¸è½±Õµ¸ì4(€…Àè€áÁàì4)ô4(¹Í µ½µÁ…ĞµÉ½Üì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ‘••À¤ì4(€‰½É‘•Èè€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€áÁàì4(€Á…‘‘¥¹œè€ÄÁÁà€ÄÉÁàì4)ô4(¹Í µ½µÁ…ĞµÉ½ÜµÑ½Àì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€áÁàì4(€™±•àµİÉ…ÀèİÉ…Àì4)ô4(¹Í µ½µÁ…Ğµ‘•Ù¥”ì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´È¤ì4(€µ¥¸µİ¥‘Ñ è€àÁÁàì4)ô4(¹Í µ½µÁ…ĞµÍÑ…ÑÕÌì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÉÁà€áÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÑÁàì4)ô4(¹Í µ½µÁ…Ğµ…Ñ¥½¹Ìì4(€µ…É¥¸µ±•™Ğè…ÕÑ¼ì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€ÑÁàì4)ô4(¹Í µÙ•É¥™äµ‰Ñ¸ì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€Á…‘‘¥¹œè€ÍÁà€ÄÁÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÕÁàì4(€‰½É‘•Èè¹½¹”ì4(€‰…­É½Õ¹èÙ…È ´µ}…•¹Ğ¤ì4(€½±½Èè€™™˜ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è½Á…¥Ñä€À¸ÄÕÌì4)ô4(¹Í µÙ•É¥™äµ‰Ñ¸é¡½Ù•Èé¹½Ğ é‘¥Í…‰±•¤ì4(€½Á…¥Ñäè€À¸àÔì4)ô4(¹Í µÙ•É¥™äµ‰Ñ¸é‘¥Í…‰±•ì4(€½Á…¥Ñäè€À¸Ôì4(€ÕÉÍ½Èè¹½Ğµ…±±½İ•ì4)ô4(¹Í µÉ•Í•Ğµ‰Ñ¸ì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€Á…‘‘¥¹œè€ÉÁà€áÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÕÁàì4(€‰½É‘•Èè€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ…É¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ì¤ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è‰…­É½Õ¹€À¸ÄÕÌì4)ô4(¹Í µÉ•Í•Ğµ‰Ñ¸é¡½Ù•Èì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ‘••À¤ì4)ô4(¹Í µ½µÁ…ĞµÑ…É•ÑÌì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€ÑÁàì4(€™±•àµİÉ…ÀèİÉ…Àì4(€µ…É¥¸µÑ½Àè€ÙÁàì4)ô4(¹Í µ½µÁ…ĞµÑ…É•Ğµ‰…‘”ì4(€™½¹ĞµÍ¥é”è€åÁàì4(€Á…‘‘¥¹œè€ÉÁà€ÙÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÑÁàì4)ô4(¹Í µÙ•É¥™äµ±½œì4(€µ…É¥¸µÑ½Àè€ÄÉÁàì4(€Á…‘‘¥¹œè€ÄÁÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµ™…µ¥±äèµ½¹½ÍÁ…”ì4(€‰…­É½Õ¹è€ŒÁ„Á”ÄĞì4(€½±½Èè€ŒäÑ„Íˆàì4(€µ…àµ¡•¥¡Ğè€ÈÀÁÁàì4(€½Ù•É™±½Üè…ÕÑ¼ì4(€İ¡¥Ñ”µÍÁ…”èÁÉ”µİÉ…Àì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°±•µ•¹ÑÌ¹½Ñ”ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ•±•µ•¹ÑÌµ¹½Ñ”ì4(€™½¹ĞµÍ¥é”è€ÄÅÁàì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ğ¤ì4(€µ…É¥¸è€Àì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°A½ÁÕÀ‘•Ñ•Ñ½ÉÌƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µÁ½ÁÕÀµ±¥ÍĞì4(€‘¥ÍÁ±…äè™±•àì4(€™±•àµ‘¥É•Ñ¥½¸è½±Õµ¸ì4)ô4(¹Í µÁ½ÁÕÀµÉ½Üì4(€Á…‘‘¥¹œè€áÁà€ÄÁÁàì4(€‰½É‘•Èµ‰½ÑÑ½´è€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4)ô4(¹Í µÁ½ÁÕÀµÉ½Üé±…ÍĞµ¡¥±ì4(€‰½É‘•Èµ‰½ÑÑ½´è¹½¹”ì4)ô4(¹Í µÁ½ÁÕÀµ±…‰•°ì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4(€µ…É¥¸µ‰½ÑÑ½´è€ÉÁàì4)ô4(¹Í µÁ½ÁÕÀµµ•Ñ„ì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€ÄÉÁàì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµ™…µ¥±äèµ½¹½ÍÁ…”ì4)ô4(¹Í µÁ½ÁÕÀµ‘•Ñ•Ğì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ğ¤ì4)ô4(¹Í µÁ½ÁÕÀµ…Ñ¥½¸ì4(€½±½Èè€˜Ôå”Áˆì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°áÁ½ÉĞ€¼•±•Ñ”‰ÕÑÑ½¹Ìƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ•áÁ½ÉĞµ‰Ñ¸ì4(€™±•àè€Äì4(€Á…‘‘¥¹œè€áÁà€ÄÑÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€‰½É‘•Èè€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ‘••À¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´È¤ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è‰…­É½Õ¹€À¸ÄÕÌ°½±½È€À¸ÄÕÌì4)ô4(¹Í µ•áÁ½ÉĞµ‰Ñ¸é¡½Ù•Èì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ…É¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4)ô4(¹Í µ‘•±•Ñ”µ‰Ñ¸ì4(€™±•àè€Äì4(€Á…‘‘¥¹œè€áÁà€ÄÑÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€‰½É‘•Èè€ÅÁàÍ½±¥€•˜ĞĞĞĞĞĞì4(€‰…­É½Õ¹è€•˜ĞĞĞĞÄØì4(€½±½Èè€˜àÜÄÜÄì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è‰…­É½Õ¹€À¸ÄÕÌì4)ô4(¹Í µ‘•±•Ñ”µ‰Ñ¸é¡½Ù•Èì4(€‰…­É½Õ¹è€•˜ĞĞĞĞÌÌì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°Q…ˆ‰…Èƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µÑ…ˆµ‰…Èì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€ÑÁàì4(€µ…É¥¸µ‰½ÑÑ½´è€ÄÙÁàì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ‘••À¤ì4(€‰½É‘•Èè€ÅÁàÍ½±¥Ù…È ´µ}‰½É‘•È¤ì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÄÁÁàì4(€Á…‘‘¥¹œè€ÑÁàì4(€İ¥‘Ñ è™¥Ğµ½¹Ñ•¹Ğì4)ô4(¹Í µÑ…ˆµ‰Ñ¸ì4(€‘¥ÍÁ±…äè™±•àì4(€…±¥¸µ¥Ñ•µÌè•¹Ñ•Èì4(€…Àè€ÙÁàì4(€Á…‘‘¥¹œè€áÁà€ÄáÁàì4(€™½¹ĞµÍ¥é”è€ÄÍÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€áÁàì4(€‰½É‘•Èè¹½¹”ì4(€‰…­É½Õ¹èÑÉ…¹ÍÁ…É•¹Ğì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ì¤ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è…±°€À¸ÄÕÌì4)ô4(¹Í µÑ…ˆµ‰Ñ¸é¡½Ù•Èé¹½Ğ ¹Í µÑ…ˆµ‰Ñ¸´µ…Ñ¥Ù”¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´È¤ì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°Ù…È ´µ}Ñ•áĞ´Ğ¤€à”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4)ô4(¹Í µÑ…ˆµ‰Ñ¸´µ…Ñ¥Ù”ì4(€‰…­É½Õ¹èÙ…È ´µ}‰œµ…É¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ä¤ì4(€‰½àµÍ¡…‘½Üè€À€ÅÁà€ÍÁàÉ‰„ À°€À°€À°€À¸È¤ì4)ô4(¹Í µÑ…ˆµ½Õ¹Ğì4(€™½¹ĞµÍ¥é”è€ÄÁÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÅÁà€İÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€äääåÁàì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°Ù…È ´µ}Ñ•áĞ´Ğ¤€Äà”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4(€½±½ÈèÙ…È ´µ}Ñ•áĞ´Ì¤ì4(€±¥¹”µ¡•¥¡Ğè€Ä¸Øì4)ô4(¹Í µÑ…ˆµ‰Ñ¸´µ…Ñ¥Ù”€¹Í µÑ…ˆµ½Õ¹Ğì4(€‰…­É½Õ¹è½±½Èµµ¥à¡¥¸ÍÉˆ°Ù…È ´µ}…•¹Ğ¤€ÄØ”°ÑÉ…¹ÍÁ…É•¹Ğ¤ì4(€½±½ÈèÙ…È ´µ}…•¹Ğ¤ì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°!Õˆ…ÉÑİ•…­Ìƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ…É´µ¡Õˆì4(€ÕÉÍ½Èè‘•™…Õ±Ğì4)ô4(¹Í µ…É´µ¡Õˆé¡½Ù•Èì4(€ÑÉ…¹Í™½É´è¹½¹”ì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°=™™¥¥…°€¼½µµÕ¹¥Ñä‰…‘•Ìƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ½™™¥¥…°µ‰…‘”ì4(€™½¹ĞµÍ¥é”è€åÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÉÁà€áÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€äääåÁàì4(€‰…­É½Õ¹è€ŒÈÉŒÔÕ”Äàì4(€½±½Èè€ŒÑ…‘”àÀì4(€±•ÑÑ•ÈµÍÁ…¥¹œè€À¸ÀÉ•´ì4)ô4(¹Í µ½µµÕ¹¥Ñäµ‰…‘”ì4(€™½¹ĞµÍ¥é”è€åÁàì4(€™½¹Ğµİ•¥¡Ğè€ÜÀÀì4(€Á…‘‘¥¹œè€ÉÁà€áÁàì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€äääåÁàì4(€‰…­É½Õ¹è€ŒÍˆàÉ˜ØÄàì4(€½±½Èè€ŒØÁ„Õ™„ì4(€±•ÑÑ•ÈµÍÁ…¥¹œè€À¸ÀÉ•´ì4)ô4(4(¼¨ƒ‹ŠwŠ
³‹ŠwŠ
°%¹ÍÑ…±°‰ÕÑÑ½¸É½Üƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°€¨¼4(¹Í µ…Éµ¥¹ÍÑ…±°µÉ½Üì4(€µ…É¥¸µÑ½Àè€ÄÉÁàì4(€‘¥ÍÁ±…äè™±•àì4(€…Àè€áÁàì4)ô4(¹Í µ¥¹ÍÑ…±°µ‰Ñ¸ì4(€Á…‘‘¥¹œè€ÙÁà€ÄÙÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€‰½É‘•Èè¹½¹”ì4(€‰…­É½Õ¹èÙ…È ´µ}…•¹Ğ¤ì4(€½±½Èè€™™˜ì4(€ÕÉÍ½ÈèÁ½¥¹Ñ•Èì4(€ÑÉ…¹Í¥Ñ¥½¸è½Á…¥Ñä€À¸ÄÕÌì4)ô4(¹Í µ¥¹ÍÑ…±°µ‰Ñ¸é¡½Ù•Èé¹½Ğ é‘¥Í…‰±•¤ì4(€½Á…¥Ñäè€À¸àÔì4)ô4(¹Í µ¥¹ÍÑ…±°µ‰Ñ¸é‘¥Í…‰±•ì4(€½Á…¥Ñäè€À¸Ôì4(€ÕÉÍ½Èè¹½Ğµ…±±½İ•ì4)ô4(¹Í µ¥¹ÍÑ…±±•µ‰…‘”µ‰Ñ¸ì4(€Á…‘‘¥¹œè€ÙÁà€ÄÙÁàì4(€™½¹ĞµÍ¥é”è€ÄÉÁàì4(€™½¹Ğµİ•¥¡Ğè€ØÀÀì4(€‰½É‘•ÈµÉ…‘¥ÕÌè€ÙÁàì4(€‰½É‘•Èè€ÅÁàÍ½±¥€ŒÈÉŒÔÕ”ĞĞì4(€‰…­É½Õ¹è€ŒÈÉŒÔÕ”ÄÈì4(€½±½Èè€ŒÑ…‘”àÀì4(€ÕÉÍ½Èè‘•™…Õ±Ğì4)ô4(ğ½ÍÑå±”ø4(