<template>
  <main class="landing-page" :class="{ 'is-intro': !introComplete }">
    <AuroraField />
    <button v-if="!introComplete && !reduced" class="skip-intro" @click="skipIntro">跳过动画</button>
    <div class="landing-content">
      <header class="landing-nav reveal-item">
        <div class="brand-mark"><span>O</span><div><strong>ORIPIO</strong><small>INTELLIGENCE OS</small></div></div>
        <div class="landing-nav-meta"><span class="status-dot"></span> 数据智能工作台 <button class="ghost-light" @click="enter('overview')">进入工作台 ↗</button></div>
      </header>
      <section class="landing-hero">
        <div class="hero-kicker reveal-item"><span></span> DATA · CONTEXT · ACTION</div>
        <h1 aria-label="让复杂数据开始流动。">
          <span class="hero-title-line"><TextReveal :fragments="['让复杂数据']" :delay="introDelay + 80" :simple="reduced" /></span>
          <span class="hero-title-line hero-title-line--signal"><TextReveal :fragments="['开始流动。']" :delay="introDelay + 330" :simple="reduced" /></span>
        </h1>
        <p class="reveal-item">Oripio 将数据库、业务知识与智能分析汇聚到一个可探索的空间。<br />从自然语言提问，到看见数据背后的关系与信号。</p>
        <div class="hero-actions reveal-item"><button ref="primaryButton" class="primary-light" @pointermove="magnetize" @pointerleave="resetMagnet" @click="enter('overview')">探索数据空间 <span>↗</span></button><button class="text-light" @click="enter('ask')">直接问一个问题 <span>→</span></button></div>
      </section>
      <section class="landing-bottom reveal-item">
        <div v-for="feature in features" :key="feature.number" class="landing-feature"><span class="feature-number">{{ feature.number }}</span><div><strong>{{ feature.title }}</strong><p>{{ feature.description }}</p></div></div>
      </section>
    </div>
    <div class="landing-footer reveal-item"><span>ORIPIO / 2026</span><span>ANALYTICS, REFRAMED</span></div>
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AuroraField from '../components/AuroraField.vue'
import TextReveal from '../components/TextReveal.vue'

const emit = defineEmits<{ (event: 'enter', page: string): void }>()
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const introDelay = reduced ? 0 : 140
const introComplete = ref(reduced)
const primaryButton = ref<HTMLButtonElement | null>(null)
let timer = 0
const features = [
  { number: '01', title: '语义检索', description: '以向量空间理解表结构和业务语义' },
  { number: '02', title: '智能问析', description: '用自然语言连接数据与决策' },
  { number: '03', title: '关系洞察', description: '把字段、指标与业务对象放在一起看' },
]
function finishIntro() { introComplete.value = true }
function skipIntro() { window.clearTimeout(timer); finishIntro() }
function enter(page: string) { finishIntro(); emit('enter', page) }
function magnetize(event: PointerEvent) { if (reduced || !primaryButton.value) return; const rect = primaryButton.value.getBoundingClientRect(); primaryButton.value.style.transform = `translate(${(event.clientX - rect.left - rect.width / 2) * .09}px, ${(event.clientY - rect.top - rect.height / 2) * .12}px)` }
function resetMagnet() { if (primaryButton.value) primaryButton.value.style.transform = '' }
onMounted(() => { if (!introComplete.value) timer = window.setTimeout(finishIntro, 1320) })
onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<style scoped>
.landing-page{position:relative;min-height:100svh;overflow:hidden;color:#efe8cf;background:#070604}.landing-page::before{position:absolute;inset:0;z-index:1;background:linear-gradient(90deg,rgba(252,238,10,.08) 1px,transparent 1px),linear-gradient(rgba(255,43,39,.055) 1px,transparent 1px);background-size:72px 72px;mask-image:linear-gradient(90deg,#000,transparent 76%);content:'';pointer-events:none}.landing-page::after{position:absolute;inset:12px;z-index:1;border:1px solid rgba(252,238,10,.28);clip-path:polygon(0 0,34% 0,35% 7px,76% 7px,77% 0,100% 0,100% 66%,calc(100% - 8px) 68%,calc(100% - 8px) 100%,0 100%);content:'';pointer-events:none}.landing-content{position:relative;z-index:2;display:flex;min-height:100svh;flex-direction:column;padding:28px 5vw;pointer-events:none}.landing-content button{pointer-events:auto}.reveal-item{opacity:1;transform:none;transition:opacity .3s steps(3,end),transform .38s steps(3,end)}.is-intro .reveal-item{opacity:0;transform:translateX(-9px)}.landing-nav{display:flex;align-items:center;justify-content:space-between}.brand-mark{display:flex;align-items:center;gap:11px}.brand-mark>span{display:grid;width:38px;height:38px;place-items:center;color:#080704;background:#fcee0a;font-family:Rajdhani,sans-serif;font-size:26px;font-weight:800;clip-path:polygon(0 0,78% 0,100% 22%,100% 100%,18% 100%,0 82%);box-shadow:8px 0 0 #ff2b27}.brand-mark strong{display:block;color:#fcee0a;font-family:Rajdhani,sans-serif;font-size:15px;font-weight:700;letter-spacing:.22em}.brand-mark small{display:block;margin-top:2px;color:#a69d7c;font-family:Rajdhani,sans-serif;font-size:8px;letter-spacing:.25em}.landing-nav-meta{display:flex;align-items:center;gap:9px;color:#b1a98e;font-size:12px}.status-dot{width:7px;height:7px;background:#ff2b27;box-shadow:0 0 13px #ff2b27;animation:status-twitch 2.4s steps(1,end) infinite}.ghost-light{margin-left:17px;padding:9px 15px;border:1px solid rgba(252,238,10,.65);border-radius:0;color:#fcee0a;background:rgba(252,238,10,.04);font-size:12px;clip-path:polygon(0 0,92% 0,100% 28%,100% 100%,8% 100%,0 72%);cursor:pointer;transition:.16s}.ghost-light:hover{color:#080704;background:#fcee0a;box-shadow:5px 5px 0 #ff2b27}.landing-hero{width:min(920px,88vw);margin:auto 0;padding:5.5vh 0 6vh}.hero-kicker{display:flex;align-items:center;gap:9px;color:#ff514d;font-family:Rajdhani,sans-serif;font-size:12px;font-weight:700;letter-spacing:.3em}.hero-kicker>span{width:38px;height:3px;background:#ff2b27;box-shadow:12px 0 0 #fcee0a}.landing-hero h1{margin:22px 0 0;color:#efe8cf;font-family:'ZCOOL QingKe HuangYou',sans-serif;font-size:clamp(58px,8.3vw,126px);font-weight:400;letter-spacing:-.035em;line-height:1}.hero-title-line{display:block;width:max-content;max-width:100%;min-height:1em;white-space:nowrap}.hero-title-line--signal{color:#fcee0a;text-shadow:7px 5px 0 rgba(255,43,39,.72)}.landing-hero p{max-width:650px;margin-top:27px;padding-left:13px;border-left:3px solid #ff2b27;color:#b7ad8f;font-size:14px;line-height:1.8}.hero-actions{display:flex;align-items:center;gap:24px;margin-top:31px}.primary-light{padding:14px 18px;border:0;border-radius:0;color:#090804;background:#fcee0a;font-size:13px;font-weight:800;clip-path:polygon(0 0,91% 0,100% 28%,100% 100%,9% 100%,0 72%);box-shadow:8px 8px 0 rgba(255,43,39,.8);cursor:pointer;transition:background .15s,transform .15s}.primary-light span{margin-left:25px;font-size:17px}.primary-light:hover{background:#fff36a}.text-light{padding:9px 0;border:0;border-bottom:1px solid #ff2b27;color:#d3c9a8;background:transparent;font-size:12px;cursor:pointer}.text-light span{margin-left:7px;color:#ff3d38}.landing-bottom{display:grid;grid-template-columns:repeat(3,1fr);max-width:900px;border-top:2px solid rgba(252,238,10,.38)}.landing-feature{display:flex;gap:18px;padding:20px 24px 0 0}.landing-feature+.landing-feature{padding-left:24px;border-left:1px solid rgba(252,238,10,.24)}.feature-number{color:#ff3d38;font-family:Rajdhani,monospace;font-size:12px;font-weight:700}.landing-feature strong{display:block;color:#eee4c4;font-size:13px}.landing-feature p{margin-top:7px;color:#756d58;font-size:10px;line-height:1.6}.landing-footer{position:absolute;right:5vw;bottom:28px;left:5vw;z-index:3;display:flex;justify-content:space-between;color:#71694f;font-family:Rajdhani,monospace;font-size:10px;letter-spacing:.15em;pointer-events:none}.skip-intro{position:fixed;right:24px;bottom:24px;z-index:8;padding:8px 12px;border:1px solid #fcee0a;border-radius:0;color:#fcee0a;background:#0c0a07;font-size:10px;cursor:pointer}@keyframes status-twitch{0%,89%,94%,100%{transform:none}90%{transform:translateX(3px)}92%{transform:translateX(-2px)}}
@media(max-width:680px){.landing-page::after{inset:7px}.landing-content{padding:20px}.landing-nav-meta{display:none}.landing-hero{width:100%;padding:8vh 0 7vh}.landing-hero h1{font-size:clamp(48px,16.5vw,72px);line-height:1.06;letter-spacing:-.045em}.hero-title-line--signal{text-shadow:4px 3px 0 rgba(255,43,39,.7)}.landing-hero p{margin-top:24px;font-size:12px}.landing-hero p br{display:none}.hero-actions{align-items:flex-start;gap:18px;flex-direction:column}.landing-bottom{grid-template-columns:1fr}.landing-feature,.landing-feature+.landing-feature{padding:9px 0;border-left:0;border-bottom:1px solid rgba(252,238,10,.15)}.landing-footer{right:20px;bottom:14px;left:20px}.landing-footer span:last-child{display:none}}
@media(prefers-reduced-motion:reduce){.reveal-item{transition-duration:.18s}.status-dot{animation:none}.primary-light{transition-duration:.18s}}
</style>
<style scoped>
.landing-hero{width:min(980px,88vw);margin:auto;text-align:center}.hero-kicker{justify-content:center}.landing-hero h1{letter-spacing:.025em}.hero-title-line{margin-right:auto;margin-left:auto}.landing-hero p{margin-right:auto;margin-left:auto;padding-top:13px;padding-left:0;border-top:2px solid rgba(255,43,39,.75);border-left:0}.hero-actions{justify-content:center}.landing-bottom{width:min(900px,100%);margin-right:auto;margin-left:auto}.landing-feature{text-align:left}.brand-mark strong,.landing-nav-meta,.hero-kicker,.landing-feature strong{animation:landing-micro-rip 7.6s steps(1,end) infinite;transform-origin:center}.landing-feature:nth-child(2) strong{animation-delay:-2.5s}.landing-feature:nth-child(3) strong{animation-delay:-4.8s}@keyframes landing-micro-rip{0%,91%,95%,100%{text-shadow:none;transform:none}92%{color:#fcee0a;text-shadow:-2px 0 #ff2b27,2px 0 rgba(252,238,10,.7);transform:translateX(-1px) scaleX(1.12);clip-path:inset(0 0 52%)}93%{text-shadow:2px 0 #ff2b27;transform:translateX(1px) scaleX(.92);clip-path:inset(48% 0 0)}94%{transform:scaleX(1.05);clip-path:none}}
@media(max-width:680px){.landing-hero{width:100%;margin:auto;text-align:center}.hero-actions{align-items:center}.landing-hero p{padding-top:12px}.landing-bottom{margin-top:12px}.landing-feature{text-align:left}}
@media(prefers-reduced-motion:reduce){.brand-mark strong,.landing-nav-meta,.hero-kicker,.landing-feature strong{animation:none}}
</style>
