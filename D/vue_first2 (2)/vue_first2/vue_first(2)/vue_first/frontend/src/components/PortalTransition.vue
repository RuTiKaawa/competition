<template>
  <div v-if="active" class="sql-transition" :class="{ 'is-reduced': reduced }" role="status" aria-live="polite" aria-label="正在进入数据控制台">
    <div class="sql-transition__noise" aria-hidden="true"></div>
    <div class="sql-transition__rail sql-transition__rail--left" aria-hidden="true"></div>
    <div class="sql-transition__rail sql-transition__rail--right" aria-hidden="true"></div>
    <header class="sql-transition__header">
      <span>ORIPIO // QUERY BOOTSTRAP</span>
      <strong>SYS.077</strong>
      <i>LIVE</i>
    </header>
    <div class="sql-transition__viewport">
      <div class="sql-transition__code">
        <div v-for="(line, index) in sqlLines" :key="line.code" class="sql-line" :style="{ '--line-index': index }">
          <span>{{ line.code }}</span>
          <code v-html="line.html"></code>
          <b>{{ line.value }}</b>
        </div>
      </div>
      <div class="number-rain" aria-hidden="true">
        <span v-for="(column, index) in numberColumns" :key="index" :style="{ '--column-index': index }">{{ column }}</span>
      </div>
      <div class="sql-transition__status">
        <span>EXECUTION STREAM</span>
        <div><i></i></div>
        <strong>{{ reduced ? 'READY' : 'PROCESSING' }}</strong>
      </div>
    </div>
    <div class="sql-transition__scan" aria-hidden="true"></div>
    <footer><span>SQL / ANALYTICS KERNEL</span><span>NO. 02-77-{{ targetLabel }}</span></footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{ phase: 'home' | 'stream' | 'workspace'; reduced?: boolean; target?: string }>()
const emit = defineEmits<{ (event: 'midpoint'): void; (event: 'complete'): void }>()
const active = computed(() => props.phase === 'stream')
const targetLabel = computed(() => (props.target || 'overview').toUpperCase())
const sqlLines = [
  { code: '001', html: '<em>SELECT</em> signal_id, metric_value, confidence', value: '077.31' },
  { code: '002', html: '<em>FROM</em> oripio.semantic_stream', value: '2048' },
  { code: '003', html: '<em>JOIN</em> knowledge_graph <mark>ON</mark> context_id', value: '91.8%' },
  { code: '004', html: '<em>WHERE</em> workspace_state = <q>\'ACTIVE\'</q>', value: 'TRUE' },
  { code: '005', html: '<em>ORDER BY</em> relevance_score <mark>DESC</mark>', value: '0.984' },
  { code: '006', html: '<em>LIMIT</em> 2077;', value: 'READY' },
]
const numberColumns = [
  '077 31 2048 984 17 02 77 910 443 008', '2077 03 91 77 004 82 19 607 22', '984 108 77 31 550 02 48 913 60',
  '004 72 19 2077 11 39 88 510 03', '77 91 600 18 02 984 39 41 07', '313 08 77 2048 55 19 90 02 71',
]
let timers: number[] = []
function clearTimers() { timers.forEach(timer => window.clearTimeout(timer)); timers = [] }
watch(active, enabled => {
  clearTimers()
  if (!enabled) return
  const midpoint = props.reduced ? 90 : 1250
  const complete = props.reduced ? 180 : 1800
  timers.push(window.setTimeout(() => emit('midpoint'), midpoint))
  timers.push(window.setTimeout(() => emit('complete'), complete))
}, { immediate: true })
onBeforeUnmount(clearTimers)
</script>

<style scoped>
.sql-transition{position:fixed;inset:0;z-index:100;overflow:hidden;color:#e9dfbc;background:#050403;font-family:Rajdhani,monospace;pointer-events:all}.sql-transition::before{position:absolute;inset:0;background:radial-gradient(circle at 82% 24%,rgba(255,43,39,.16),transparent 31%),linear-gradient(90deg,rgba(252,238,10,.045) 1px,transparent 1px),linear-gradient(rgba(252,238,10,.035) 1px,transparent 1px);background-size:auto,64px 64px,64px 64px;content:''}.sql-transition__noise{position:absolute;inset:0;z-index:8;opacity:.1;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(255,255,255,.16) 3px 4px);mix-blend-mode:overlay;pointer-events:none}.sql-transition__header,footer{position:absolute;right:4vw;left:4vw;z-index:6;display:flex;align-items:center;border-bottom:2px solid #fcee0a;color:#fcee0a;font-size:clamp(10px,1vw,14px);font-weight:700;letter-spacing:.18em}.sql-transition__header{top:4vh;height:46px}.sql-transition__header strong{margin-left:auto;color:#ff3732}.sql-transition__header i{margin-left:18px;padding:4px 9px;color:#070604;background:#fcee0a;font-style:normal}footer{bottom:3vh;justify-content:space-between;height:35px;border-top:1px solid rgba(255,43,39,.6);border-bottom:0;color:#8f8567;font-size:10px}.sql-transition__viewport{position:absolute;inset:14vh 4vw 11vh;overflow:hidden;border-right:1px solid rgba(255,43,39,.45);border-left:1px solid rgba(252,238,10,.48);background:linear-gradient(100deg,rgba(252,238,10,.035),transparent 40%,rgba(255,43,39,.045))}.sql-transition__code{position:absolute;right:12%;left:7%;top:5%;z-index:3}.sql-line{display:grid;grid-template-columns:48px minmax(0,1fr) 90px;align-items:center;gap:14px;min-height:54px;border-bottom:1px solid rgba(252,238,10,.14);opacity:0;transform:translateY(-38px);animation:sql-drop .38s steps(4,end) calc(var(--line-index) * 125ms + 90ms) forwards}.sql-line>span{color:#665f4b;font-size:11px}.sql-line code{overflow:hidden;color:#d8cfb2;font-family:Rajdhani,monospace;font-size:clamp(14px,1.7vw,23px);font-weight:500;letter-spacing:.04em;white-space:nowrap}.sql-line code :deep(em){color:#fcee0a;font-style:normal;font-weight:700}.sql-line code :deep(mark){color:#ff4a45;background:transparent}.sql-line code :deep(q){color:#ff746f}.sql-line b{color:#ff3732;font-size:13px;text-align:right}.number-rain{position:absolute;inset:-90% 0 0;display:grid;grid-template-columns:repeat(6,1fr);opacity:.2;pointer-events:none}.number-rain span{display:block;max-width:52px;color:#fcee0a;font-size:13px;line-height:2.5;overflow-wrap:anywhere;transform:translateY(-30%);animation:number-fall 1.15s linear calc(var(--column-index) * -120ms) infinite}.number-rain span:nth-child(even){color:#ff2b27;animation-duration:.9s}.sql-transition__status{position:absolute;right:6%;bottom:6%;left:7%;z-index:5;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px;color:#8c8368;font-size:11px;letter-spacing:.18em}.sql-transition__status>div{height:4px;background:#261d12}.sql-transition__status i{display:block;width:100%;height:100%;background:linear-gradient(90deg,#fcee0a 0 76%,#ff2b27 76%);transform-origin:left;animation:progress 1.65s steps(12,end) both}.sql-transition__status strong{color:#fcee0a}.sql-transition__scan{position:absolute;inset:-15% 0 auto;z-index:7;height:16%;background:linear-gradient(transparent,rgba(252,238,10,.16),rgba(255,43,39,.34),transparent);filter:blur(2px);animation:scan-down 1.45s cubic-bezier(.2,.7,.2,1) .12s both;pointer-events:none}.sql-transition__rail{position:absolute;z-index:6;width:8px;height:30%;background:#fcee0a}.sql-transition__rail--left{left:2vw;top:16vh;box-shadow:0 33vh 0 #ff2b27}.sql-transition__rail--right{right:2vw;bottom:15vh;background:#ff2b27;box-shadow:0 -37vh 0 #fcee0a}@keyframes sql-drop{0%{opacity:0;transform:translateY(-38px);clip-path:inset(0 0 100%)}45%{opacity:1;transform:translate(7px,0);clip-path:inset(45% 0 8%)}70%{transform:translate(-3px,0);clip-path:inset(0)}100%{opacity:1;transform:none;clip-path:inset(0)}}@keyframes number-fall{to{transform:translateY(78%)}}@keyframes progress{from{transform:scaleX(0)}to{transform:scaleX(1)}}@keyframes scan-down{from{transform:translateY(0)}to{transform:translateY(720%)}}
.is-reduced .number-rain,.is-reduced .sql-transition__scan{display:none}.is-reduced .sql-line{opacity:1;transform:none;animation:none}.is-reduced .sql-transition__status i{animation:none}.is-reduced{animation:reduced-flash .18s ease both}@keyframes reduced-flash{0%,100%{opacity:0}45%{opacity:1}}
@media(max-width:680px){.sql-transition__header,footer{right:18px;left:18px}.sql-transition__viewport{inset:13vh 18px 10vh}.sql-transition__code{right:18px;left:18px}.sql-line{grid-template-columns:30px minmax(0,1fr);min-height:58px;gap:7px}.sql-line code{font-size:13px;text-overflow:ellipsis}.sql-line b{display:none}.number-rain{grid-template-columns:repeat(4,1fr)}.number-rain span:nth-child(n+5){display:none}.sql-transition__status{right:18px;left:18px;grid-template-columns:auto 1fr}.sql-transition__status strong{display:none}.sql-transition__rail{display:none}}
</style>
