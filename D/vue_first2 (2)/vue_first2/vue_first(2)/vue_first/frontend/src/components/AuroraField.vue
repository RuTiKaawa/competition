<template>
  <div ref="field" class="data-field" aria-hidden="true" @pointermove="handlePointer" @pointerleave="resetPointer">
    <canvas ref="canvas"></canvas>
    <div class="data-field__glow data-field__glow--cyan" :style="parallaxOne"></div>
    <div class="data-field__glow data-field__glow--violet" :style="parallaxTwo"></div>
    <div class="data-field__grid"></div>
    <div class="data-field__beam"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type Particle = { x: number; y: number; vx: number; vy: number; radius: number; alpha: number }
const field = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const pointer = ref({ x: 0, y: 0 })
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const parallaxOne = computed(() => ({ transform: `translate3d(${pointer.value.x * 18}px, ${pointer.value.y * 12}px, 0)` }))
const parallaxTwo = computed(() => ({ transform: `translate3d(${pointer.value.x * -14}px, ${pointer.value.y * -18}px, 0)` }))
let particles: Particle[] = []
let frame = 0
let observer: ResizeObserver | null = null

function setup() {
  if (!field.value || !canvas.value) return
  cancelAnimationFrame(frame)
  const rect = field.value.getBoundingClientRect()
  const ratio = Math.min(window.devicePixelRatio || 1, 1.5)
  canvas.value.width = Math.max(1, Math.floor(rect.width * ratio))
  canvas.value.height = Math.max(1, Math.floor(rect.height * ratio))
  canvas.value.style.width = `${rect.width}px`; canvas.value.style.height = `${rect.height}px`
  const count = Math.max(24, Math.min(72, Math.floor(rect.width / 20)))
  particles = Array.from({ length: count }, (_, index) => ({ x: (index * 83) % rect.width, y: (index * 47) % rect.height, vx: .05 + (index % 5) * .018, vy: -.04 + (index % 4) * .016, radius: index % 7 === 0 ? 1.8 : .8, alpha: .2 + (index % 6) * .08 }))
  draw()
}
function draw() {
  if (!canvas.value || !field.value) return
  const ctx = canvas.value.getContext('2d'); if (!ctx) return
  const ratio = Math.min(window.devicePixelRatio || 1, 1.5); const width = canvas.value.width / ratio; const height = canvas.value.height / ratio
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height)
  for (const particle of particles) {
    if (!reduced) { particle.x = (particle.x + particle.vx + width) % width; particle.y = (particle.y + particle.vy + height) % height }
    ctx.beginPath(); ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2); ctx.fillStyle = `rgba(252,238,10,${particle.alpha})`; ctx.fill()
  }
  for (let i = 0; i < particles.length; i += 1) for (let j = i + 1; j < particles.length; j += 1) {
    const dx = particles[i].x - particles[j].x; const dy = particles[i].y - particles[j].y; const distance = Math.hypot(dx, dy)
    if (distance < 130) { ctx.beginPath(); ctx.moveTo(particles[i].x, particles[i].y); ctx.lineTo(particles[j].x, particles[j].y); ctx.strokeStyle = `rgba(255,53,48,${(1 - distance / 130) * .13})`; ctx.lineWidth = .6; ctx.stroke() }
  }
  if (!reduced) frame = requestAnimationFrame(draw)
}
function handlePointer(event: PointerEvent) { if (reduced || !field.value) return; const rect = field.value.getBoundingClientRect(); pointer.value = { x: (event.clientX - rect.left) / rect.width - .5, y: (event.clientY - rect.top) / rect.height - .5 } }
function resetPointer() { pointer.value = { x: 0, y: 0 } }
onMounted(() => { setup(); observer = new ResizeObserver(setup); if (field.value) observer.observe(field.value) })
onBeforeUnmount(() => { cancelAnimationFrame(frame); observer?.disconnect() })
</script>

<style scoped>
.data-field { position: absolute; inset: 0; overflow: hidden; pointer-events: auto; background: radial-gradient(circle at 35% 32%, #21100d 0, #0b0805 46%, #030302 100%); }
.data-field canvas { position: absolute; inset: 0; opacity: .85; }
.data-field__glow { position: absolute; width: 60vw; height: 60vw; border-radius: 50%; filter: blur(90px); opacity: .32; transition: transform 1.2s cubic-bezier(.2,.8,.2,1); }
.data-field__glow--cyan { left: -18%; top: -45%; background: radial-gradient(circle, rgba(255,43,39,.58), transparent 68%); }
.data-field__glow--violet { right: -20%; bottom: -50%; background: radial-gradient(circle, rgba(252,238,10,.32), transparent 68%); }
.data-field__grid { position: absolute; inset: 35% -15% -42%; opacity: .2; background-image: linear-gradient(rgba(252,238,10,.19) 1px, transparent 1px), linear-gradient(90deg, rgba(252,238,10,.19) 1px, transparent 1px); background-size: 68px 68px; mask-image: linear-gradient(to bottom, transparent, black 25%, transparent 88%); transform: perspective(600px) rotateX(64deg) scale(1.45); transform-origin: center top; }
.data-field__beam { position: absolute; left: 14%; right: 14%; top: 50%; height: 1px; background: linear-gradient(90deg, transparent, rgba(255,43,39,.86), transparent); box-shadow: 0 0 22px rgba(255,43,39,.55); animation: beam 8s ease-in-out infinite; }
@keyframes beam { 0%,100% { opacity: .15; transform: translateY(-16vh) scaleX(.65); } 50% { opacity: .6; transform: translateY(20vh) scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .data-field__beam { animation: none; opacity: .2; } }
</style>
