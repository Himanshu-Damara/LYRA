<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const configured = ref(false)
const connected = ref(false)
const email = ref('')
const to = ref('')
const subject = ref('')
const body = ref('')
const assistantPrompt = ref('')
const assistantReply = ref('')
const busy = ref(false)
const assistantBusy = ref(false)
const message = ref('')
const error = ref('')
let pollTimer: number | null = null

async function loadStatus() {
  const response = await fetch('/api/gmail/status')
  if (!response.ok) return
  const data = await response.json()
  configured.value = data.configured; connected.value = data.connected; email.value = data.email || ''
}

async function connect() {
  error.value = ''; message.value = ''
  const response = await fetch('/api/gmail/oauth/start')
  const data = await response.json()
  if (!response.ok) { error.value = data.detail || 'Gmail OAuth is not configured'; return }
  window.open(data.authorization_url, 'lyra-gmail-oauth', 'width=520,height=700')
  pollTimer = window.setInterval(async () => { await loadStatus(); if (connected.value && pollTimer) { clearInterval(pollTimer); pollTimer = null; message.value = 'Gmail connected.' } }, 2000)
}

async function disconnect() {
  await fetch('/api/gmail/connection', { method: 'DELETE' })
  connected.value = false; email.value = ''; message.value = 'Gmail disconnected.'
}

async function askAssistant() {
  if (!assistantPrompt.value.trim() || assistantBusy.value) return
  assistantBusy.value = true; error.value = ''; assistantReply.value = ''
  try {
    const response = await fetch('/api/gmail/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: assistantPrompt.value }) })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Gmail assistant failed')
    assistantReply.value = data.reply || 'Done.'
    if (data.draft) { to.value = data.draft.to; subject.value = data.draft.subject; body.value = data.draft.body; message.value = 'Draft prepared. Review it before sending.' }
  } catch (err) { error.value = err instanceof Error ? err.message : 'Gmail assistant failed' }
  finally { assistantBusy.value = false }
}

async function send() {
  if (!to.value || !subject.value || !body.value || busy.value) return
  if (!window.confirm(`Send this email to ${to.value}?`)) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const response = await fetch('/api/gmail/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to: to.value, subject: subject.value, body: body.value }) })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Gmail rejected the message')
    message.value = `Email sent to ${data.to}.`; to.value = ''; subject.value = ''; body.value = ''
  } catch (err) { error.value = err instanceof Error ? err.message : 'Could not send email' }
  finally { busy.value = false }
}

onMounted(() => { void loadStatus() })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div class="gmail-page">
    <div class="gmail-header"><div><div class="eyebrow">GOOGLE WORKSPACE INTEGRATION</div><h2>Gmail</h2><p>Use Grok with Gmail after Google OAuth authorization.</p></div><div v-if="connected" class="connected-pill">â— {{ email }}</div></div>
    <div v-if="error" class="alert error">{{ error }}</div><div v-if="message" class="alert success">{{ message }}</div>
    <section class="card auth-card"><div><strong>{{ connected ? 'Gmail connected' : 'Connect Gmail' }}</strong><p v-if="connected">Grok can search/read mail and prepare drafts. It cannot delete or send automatically.</p><p v-else-if="!configured">Add Google OAuth credentials to the server .env file first.</p><p v-else>Google will request Gmail read and send permissions.</p></div><div class="auth-actions"><button class="primary" :disabled="!configured" @click="connect">{{ connected ? 'Reconnect with Google' : 'Connect with Google' }}</button><button v-if="connected" class="secondary" @click="disconnect">Disconnect</button></div></section>
    <section v-if="connected" class="card assistant-card"><div class="section-title"><div><strong>Ask Gmail AI</strong><span>Search/read relevant mail and prepare a draft; sending always requires your confirmation.</span></div></div><textarea v-model="assistantPrompt" rows="3" placeholder="Example: Find the latest mail from Alex and draft a polite replyâ€¦"></textarea><button class="primary" :disabled="assistantBusy || !assistantPrompt.trim()" @click="askAssistant">{{ assistantBusy ? 'Thinkingâ€¦' : 'Ask AI' }}</button><p v-if="assistantReply" class="assistant-reply">{{ assistantReply }}</p></section>
    <section v-if="connected" class="card compose-card"><div class="section-title"><div><strong>Compose email</strong><span>Direct Gmail API send Â· Android UI is not used</span></div></div><label>To<input v-model="to" type="email" placeholder="recipient@example.com" /></label><label>Subject<input v-model="subject" placeholder="Subject" /></label><label>Message<textarea v-model="body" rows="9" placeholder="Write your messageâ€¦"></textarea></label><button class="primary send" :disabled="busy || !to || !subject || !body" @click="send">{{ busy ? 'Sendingâ€¦' : 'Send email' }}</button></section>
  </div>
</template>

<style scoped>
.gmail-page{max-width:1000px;margin:0 auto;color:var(--text-1)}.gmail-header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:18px}.eyebrow{color:#34d399;font:700 10px ui-monospace,Consolas,monospace;letter-spacing:.12em}.gmail-header h2{margin:6px 0 4px;font-size:25px}.gmail-header p,.card p{color:var(--text-3);font-size:12px;margin:0;line-height:1.5}.connected-pill{padding:7px 10px;border:1px solid #2b654f;border-radius:999px;color:#6ee7b7;font-size:11px}.card{background:var(--bg-card,#111a15);border:1px solid var(--border,#26372c);border-radius:10px;padding:18px;margin-bottom:14px}.auth-card,.section-title{display:flex;justify-content:space-between;align-items:center;gap:20px}.auth-card strong,.section-title strong{font-size:14px}.auth-actions{white-space:nowrap}.primary,.secondary{border:1px solid #2b654f;border-radius:7px;padding:9px 13px;background:#123126;color:#8ff0c2;font-size:11px;font-weight:700;cursor:pointer}.primary:disabled{opacity:.4;cursor:not-allowed}.secondary{background:transparent;color:var(--text-2);border-color:var(--border)}.compose-card,.assistant-card{max-width:720px}.section-title{margin-bottom:14px}.section-title span{display:block;color:var(--text-4);font-size:10px;margin-top:4px}.compose-card label{display:block;color:var(--text-3);font-size:11px;margin:12px 0}.compose-card input,.compose-card textarea,.assistant-card textarea{display:block;width:100%;box-sizing:border-box;margin-top:5px;padding:9px;border:1px solid var(--border);border-radius:6px;background:#08100b;color:var(--text-1);font:12px/1.5 inherit}.assistant-reply{margin-top:12px;padding:10px;border:1px solid var(--border);border-radius:6px;white-space:pre-wrap}.send{margin-top:4px}.alert{padding:10px;border-radius:7px;margin-bottom:12px;font-size:11px}.alert.error{background:#451a0b;color:#fbbf24;border:1px solid #92400e}.alert.success{background:#064e3b;color:#6ee7b7;border:1px solid #047857}@media(max-width:700px){.gmail-header,.auth-card{align-items:flex-start;flex-direction:column}}
</style>
