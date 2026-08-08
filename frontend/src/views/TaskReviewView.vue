<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type SectionStatus = 'complete' | 'review' | 'missing'
type TaskStatus = 'Draft' | 'In review' | 'Ready'

interface ReviewSection {
  id: string
  name: string
  required: boolean
  source: string
  status: SectionStatus
  generated_content: string
  notes: string
}

interface AgentTask {
  id: string
  title: string
  summary: string
  owner: string
  agent: string
  status: TaskStatus
  notes: string
  validation_warnings: string[]
  updated_at: string
  sections: ReviewSection[]
  completion: { complete: number; total: number; percent: number }
  missing_required: string[]
  ready: boolean
}

const tasks = ref<AgentTask[]>([])
const selectedTask = ref<AgentTask | null>(null)
const selectedSectionId = ref('')
const query = ref('')
const sectionFilter = ref('')
const statusFilter = ref('')
const ownerFilter = ref('')
const agentFilter = ref('')
const missingFilter = ref('')
const loading = ref(false)
const error = ref('')
const savedAt = ref('')

const filters = ref<{ sections: string[]; statuses: string[]; owners: string[]; agents: string[] }>({ sections: [], statuses: [], owners: [], agents: [] })
const selectedSection = computed(() => selectedTask.value?.sections.find(s => s.id === selectedSectionId.value) || null)
const selectedTaskIndex = computed(() => tasks.value.findIndex(t => t.id === selectedTask.value?.id))

async function fetchTasks(selectId = '') {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (query.value.trim()) params.set('search', query.value.trim())
    if (sectionFilter.value) params.set('section', sectionFilter.value)
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (ownerFilter.value) params.set('owner', ownerFilter.value)
    if (agentFilter.value) params.set('agent', agentFilter.value)
    if (missingFilter.value) params.set('missing_data', missingFilter.value === 'missing' ? 'true' : 'false')
    const response = await fetch(`/api/task-review/tasks?${params}`)
    if (!response.ok) throw new Error('Could not load task records')
    const data = await response.json()
    tasks.value = data.data || []
    filters.value = data.filters || filters.value
    const nextId = selectId || selectedTask.value?.id || tasks.value[0]?.id || ''
    if (nextId && tasks.value.some(t => t.id === nextId)) await selectTask(nextId)
    else selectedTask.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load task records'
  } finally { loading.value = false }
}

async function selectTask(id: string) {
  try {
    const response = await fetch(`/api/task-review/tasks/${encodeURIComponent(id)}`)
    if (!response.ok) throw new Error('Could not load selected task')
    selectedTask.value = await response.json()
    selectedSectionId.value = selectedTask.value?.sections[0]?.id || ''
  } catch (err) { error.value = err instanceof Error ? err.message : 'Could not load selected task' }
}

function resetFilters() {
  query.value = ''; sectionFilter.value = ''; statusFilter.value = ''; ownerFilter.value = ''; agentFilter.value = ''; missingFilter.value = ''
}

async function saveSection() {
  if (!selectedTask.value || !selectedSection.value) return
  const section = selectedSection.value
  const response = await fetch(`/api/task-review/tasks/${selectedTask.value.id}/sections/${section.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: section.status, source: section.source, generated_content: section.generated_content, notes: section.notes }),
  })
  if (!response.ok) { error.value = 'Could not save checklist item'; return }
  const updated = await response.json() as AgentTask
  selectedTask.value = updated; savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  await fetchTasks(updated.id)
}

async function saveTask() {
  if (!selectedTask.value) return
  const response = await fetch(`/api/task-review/tasks/${selectedTask.value.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes: selectedTask.value.notes }),
  })
  if (!response.ok) { error.value = 'Could not save reviewer note'; return }
  const updated = await response.json() as AgentTask
  selectedTask.value = updated; savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  await fetchTasks(updated.id)
}

async function downloadPacket() {
  if (!selectedTask.value) return
  const response = await fetch(`/api/task-review/tasks/${selectedTask.value.id}/packet`)
  if (!response.ok) { error.value = 'Could not generate review packet'; return }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = `review-packet-${selectedTask.value.id}.md`; link.click(); URL.revokeObjectURL(url)
}

watch([query, sectionFilter, statusFilter, ownerFilter, agentFilter, missingFilter], () => { void fetchTasks() })
onMounted(() => { void fetchTasks() })
</script>

<template>
  <div class="task-review">
    <div class="review-header">
      <div><div class="eyebrow">QUALITY GATE Â· GENERATED CONTENT</div><h2>Agent Task Review</h2><p>Complete sources, review generated sections, and export a persistent review packet.</p></div>
      <div class="header-actions"><span v-if="savedAt" class="saved-state">âœ“ Saved {{ savedAt }}</span><button class="primary-btn" :disabled="!selectedTask" @click="downloadPacket">â†“ Download review packet</button></div>
    </div>
    <div v-if="error" class="error-box">{{ error }}</div>
    <div class="filter-bar">
      <label class="search-field">âŒ• <input v-model="query" placeholder="Search task, section, source, or generated contentâ€¦" /></label>
      <select v-model="sectionFilter"><option value="">All sections</option><option v-for="value in filters.sections" :key="value" :value="value">{{ value }}</option></select>
      <select v-model="statusFilter"><option value="">All statuses</option><option v-for="value in filters.statuses" :key="value" :value="value">{{ value }}</option></select>
      <select v-model="ownerFilter"><option value="">All owners</option><option v-for="value in filters.owners" :key="value" :value="value">{{ value }}</option></select>
      <select v-model="agentFilter"><option value="">All agents</option><option v-for="value in filters.agents" :key="value" :value="value">{{ value }}</option></select>
      <select v-model="missingFilter"><option value="">All data states</option><option value="missing">Has missing data</option><option value="complete">No missing data</option></select>
      <button class="reset-btn" @click="resetFilters">Reset</button>
    </div>
    <div class="review-stats"><div><span>{{ tasks.length }}</span><small>Matching tasks</small></div><div><span>{{ tasks.filter(t => t.ready).length }}</span><small>Ready</small></div><div><span>{{ tasks.filter(t => !t.ready).length }}</span><small>Missing data</small></div><div><span>{{ loading ? 'â€¦' : (selectedTaskIndex >= 0 ? selectedTaskIndex + 1 : 0) }}</span><small>Selected</small></div></div>

    <div class="review-layout">
      <aside class="task-list card"><div class="list-heading"><strong>Task records</strong><span>{{ tasks.length }} results</span></div><div v-if="loading" class="empty-state">Loading task recordsâ€¦</div><template v-else><button v-for="task in tasks" :key="task.id" class="task-row" :class="{ selected: task.id === selectedTask?.id }" @click="selectTask(task.id)"><div class="task-row-top"><strong>{{ task.title }}</strong><span class="status-pill" :class="task.status.toLowerCase().replace(' ', '-')">{{ task.status }}</span></div><p>{{ task.summary }}</p><div class="task-meta"><span>{{ task.owner }} Â· {{ task.agent }}</span><span>{{ task.completion.complete }}/{{ task.completion.total }}</span></div><div class="progress"><i :style="{ width: `${task.completion.percent}%` }"></i></div><span v-if="!task.ready" class="missing-label">! Missing required data</span></button><div v-if="!tasks.length" class="empty-state">No agent tasks match the current filters.<br /><button class="reset-btn" @click="resetFilters">Reset filters</button></div></template></aside>

      <section v-if="selectedTask" class="task-detail">
        <div class="detail-card card"><div class="detail-title"><div><div class="eyebrow">{{ selectedTask.id }}</div><h3>{{ selectedTask.title }}</h3><p>{{ selectedTask.summary }}</p></div><span class="status-pill" :class="selectedTask.status.toLowerCase().replace(' ', '-')">{{ selectedTask.status }}</span></div><div class="detail-meta"><span>Owner <b>{{ selectedTask.owner }}</b></span><span>Agent <b>{{ selectedTask.agent }}</b></span><span>Checklist <b>{{ selectedTask.completion.complete }}/{{ selectedTask.completion.total }}</b></span><span :class="selectedTask.ready ? 'ready-text' : 'warning-text'">{{ selectedTask.ready ? 'READY' : 'MISSING REQUIRED INPUTS' }}</span></div></div>
        <div class="detail-grid">
          <div class="card checklist-card"><div class="card-heading"><div><strong>Source checklist</strong><span>Persisted required inputs and evidence</span></div><span class="completion-ring">{{ selectedTask.completion.percent }}%</span></div><button v-for="section in selectedTask.sections" :key="section.id" class="checklist-row" :class="{ active: section.id === selectedSectionId }" @click="selectedSectionId = section.id"><span class="check-icon" :class="section.status">{{ section.status === 'complete' && section.source ? 'âœ“' : section.status === 'review' ? 'â€¢' : '!' }}</span><span class="check-copy"><b>{{ section.name }}</b><small>{{ section.source || 'Source missing' }} Â· {{ section.required ? 'Required' : 'Optional' }}</small></span><span class="row-status">{{ section.status }}</span></button><div v-if="selectedTask.missing_required.length" class="warning-box">Missing required inputs: {{ selectedTask.missing_required.join(', ') }}</div></div>
          <div v-if="selectedSection" class="card section-editor"><div class="card-heading"><div><strong>{{ selectedSection.name }}</strong><span>Saved checklist and generated content</span></div><select v-model="selectedSection.status" @change="saveSection"><option value="complete">Complete</option><option value="review">Needs review</option><option value="missing">Missing data</option></select></div><label>Source / input <input v-model="selectedSection.source" placeholder="Who or what supports this section?" @change="saveSection" /></label><label>Generated content <textarea v-model="selectedSection.generated_content" rows="6" placeholder="Generated section contentâ€¦" @change="saveSection"></textarea></label><label>Section notes <textarea v-model="selectedSection.notes" rows="3" placeholder="Review notes or missing-data guidanceâ€¦" @change="saveSection"></textarea></label></div>
        </div>
        <div class="card notes-card"><div class="card-heading"><div><strong>User notes</strong><span>Saved with the selected agent task and included in exports</span></div><button class="secondary-btn" @click="saveTask">Save note</button></div><textarea v-model="selectedTask.notes" rows="3" placeholder="Add a reviewer note before exportingâ€¦" @change="saveTask"></textarea></div>
        <div class="card packet-preview"><div class="card-heading"><div><strong>Review packet</strong><span>Generated by the backend from this selected task</span></div><button class="secondary-btn" @click="downloadPacket">Export .md</button></div><div class="preview-grid"><div><small>Warnings</small><b>{{ selectedTask.validation_warnings.length || 'None' }}</b></div><div><small>Generated sections</small><b>{{ selectedTask.sections.filter(s => s.generated_content).length }}/{{ selectedTask.sections.length }}</b></div><div><small>Missing fields</small><b>{{ selectedTask.missing_required.length || 'None' }}</b></div></div></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.task-review{color:var(--text-1);max-width:1500px;margin:0 auto}.review-header{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:18px}.eyebrow{color:#34d399;font:700 10px/1.4 ui-monospace,Consolas,monospace;letter-spacing:.12em;text-transform:uppercase}h2{margin:5px 0 4px;font-size:25px}h3{margin:4px 0;font-size:18px}p{color:var(--text-3);font-size:12px;margin:0;line-height:1.5}.header-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}.saved-state,.ready-text{color:#34d399;font-size:11px}.warning-text{color:#fbbf24;font-size:11px}.error-box,.warning-box{padding:10px;border:1px solid #92400e;border-radius:7px;background:#451a0b55;color:#fbbf24;font-size:11px;margin-bottom:12px}.primary-btn,.secondary-btn,.reset-btn{border:1px solid #2b654f;border-radius:7px;padding:8px 12px;background:#123126;color:#8ff0c2;font-size:11px;font-weight:700;cursor:pointer}.primary-btn:disabled{opacity:.4;cursor:not-allowed}.secondary-btn,.reset-btn{background:transparent;border-color:var(--border);color:var(--text-2)}.filter-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.filter-bar select,.section-editor select{background:var(--bg-card,#111a15);border:1px solid var(--border);color:var(--text-2);border-radius:6px;padding:8px 9px;font-size:11px}.search-field{flex:1 1 270px;display:flex;gap:8px;align-items:center;background:var(--bg-card,#111a15);border:1px solid var(--border);border-radius:6px;padding:0 10px;color:#34d399;font-size:17px}.search-field input{width:100%;padding:9px 0;border:0;outline:0;background:transparent;color:var(--text-1);font-size:11px}.review-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.review-stats>div,.card{background:var(--bg-card,#111a15);border:1px solid var(--border,#26372c);border-radius:10px}.review-stats>div{padding:12px 14px}.review-stats span{display:block;font-size:20px;font-weight:750}.review-stats small,.card-heading span{color:var(--text-4);font-size:10px}.review-layout{display:grid;grid-template-columns:330px minmax(0,1fr);gap:14px;align-items:start}.task-list{padding:10px}.list-heading,.card-heading,.detail-title,.detail-meta,.task-row-top,.task-meta{display:flex;justify-content:space-between;align-items:center;gap:10px}.list-heading{padding:6px 6px 10px}.list-heading span,.detail-meta{color:var(--text-4);font-size:10px}.task-row{width:100%;text-align:left;padding:12px 10px;margin-bottom:6px;border:1px solid transparent;border-radius:8px;background:transparent;color:inherit;cursor:pointer}.task-row:hover,.task-row.selected{background:#14241b;border-color:#2b654f}.task-row strong{font-size:12px}.task-row p{margin:6px 0 8px;font-size:11px}.task-meta{font-size:10px;color:var(--text-4)}.progress{height:4px;background:#223329;border-radius:3px;overflow:hidden;margin-top:8px}.progress i{display:block;height:100%;background:#34d399;border-radius:3px}.missing-label{display:block;color:#fbbf24;font-size:10px;margin-top:7px}.status-pill{padding:3px 7px;border-radius:999px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;background:#33415566;color:var(--text-3)}.status-pill.ready{background:#064e3b66;color:#6ee7b7}.status-pill.in-review{background:#78350f66;color:#fbbf24}.status-pill.draft{background:#33415566;color:#94a3b8}.task-detail{display:flex;flex-direction:column;gap:14px;min-width:0}.detail-card,.checklist-card,.section-editor,.packet-preview,.notes-card{padding:16px}.detail-title{align-items:flex-start}.detail-meta{justify-content:flex-start;gap:24px;margin-top:15px}.detail-meta b{color:var(--text-2);margin-left:4px}.detail-grid{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(320px,1.2fr);gap:14px}.card-heading{margin-bottom:13px}.completion-ring{color:#34d399;font-weight:700}.checklist-row{width:100%;display:flex;align-items:center;gap:9px;padding:10px 8px;border:1px solid transparent;border-radius:7px;background:transparent;color:inherit;text-align:left;cursor:pointer}.checklist-row:hover,.checklist-row.active{background:#14241b;border-color:#2b654f}.check-icon{width:20px;height:20px;display:grid;place-items:center;border-radius:50%;font-weight:700;font-size:11px;background:#334155;color:#cbd5e1}.check-icon.complete{background:#065f46;color:#6ee7b7}.check-icon.review{background:#78350f;color:#fbbf24}.check-icon.missing{background:#7f1d1d;color:#fca5a5}.check-copy{display:flex;flex:1;flex-direction:column;gap:3px}.check-copy b{font-size:11px}.check-copy small{color:var(--text-4);font-size:10px}.row-status{color:var(--text-4);font-size:9px}.section-editor label,.notes-card label{display:block;color:var(--text-3);font-size:10px;margin:11px 0}.section-editor input,.section-editor textarea,.notes-card textarea{width:100%;box-sizing:border-box;background:#08100b;border:1px solid var(--border);border-radius:6px;color:var(--text-1);padding:8px;margin-top:5px;font:11px/1.5 inherit}.notes-card textarea{margin-top:0}.preview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.preview-grid div{padding:10px;background:#0b140e;border-radius:6px}.preview-grid small,.preview-grid b{display:block}.preview-grid small{color:var(--text-4);font-size:10px}.preview-grid b{margin-top:4px;font-size:14px}.empty-state{text-align:center;color:var(--text-3);font-size:11px;padding:28px 10px;line-height:1.8}@media(max-width:900px){.review-header{align-items:flex-start;flex-direction:column}.review-layout,.detail-grid{grid-template-columns:1fr}.review-stats{grid-template-columns:repeat(2,1fr)}.detail-meta{flex-wrap:wrap}}
</style>
