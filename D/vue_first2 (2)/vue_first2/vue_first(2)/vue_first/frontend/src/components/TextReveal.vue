<template>
  <span class="text-reveal" :class="{ 'is-ready': ready, 'is-simple': simple }" :style="{ '--reveal-delay': `${delay}ms` }">
    <span
      v-for="(character, index) in characters"
      :key="`${character}-${index}`"
      class="text-reveal__glyph"
      :class="{ 'is-space': character === ' ' }"
      :data-char="character"
      :style="{ '--character-delay': `${index * 64}ms`, '--glitch-index': index }"
    >{{ character === ' ' ? '\u00a0' : character }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
const props = withDefaults(defineProps<{ fragments: string[]; delay?: number; simple?: boolean }>(), { delay: 0, simple: false })
const characters = computed(() => props.fragments.join('').split(''))
const ready = ref(false)
onMounted(() => requestAnimationFrame(() => { ready.value = true }))
</script>

<style scoped>
.text-reveal { display: inline-flex; flex-wrap: nowrap; overflow: visible; white-space: nowrap; transform: scaleX(1.1); transform-origin: center; }
.text-reveal__glyph { position: relative; display: inline-block; opacity: 0; color: inherit; transform: translate3d(0, .72em, 0) skewX(-10deg); filter: blur(6px); clip-path: inset(0 0 100% 0); }
.text-reveal__glyph::before,.text-reveal__glyph::after { position: absolute; inset: 0; overflow: hidden; opacity: 0; content: attr(data-char); pointer-events: none; }
.text-reveal__glyph::before { color: #ff2b27; transform: translateX(-.055em); clip-path: inset(9% 0 58% 0); }
.text-reveal__glyph::after { color: #fcee0a; transform: translateX(.055em); clip-path: inset(58% 0 10% 0); }
.text-reveal.is-ready .text-reveal__glyph { animation: glyph-boot .56s steps(2,end) calc(var(--reveal-delay) + var(--character-delay)) forwards, glyph-twitch 6.4s steps(1,end) calc(var(--reveal-delay) + var(--character-delay) + 1.1s) infinite; }
.text-reveal.is-ready .text-reveal__glyph::before { animation: glyph-red .48s steps(2,end) calc(var(--reveal-delay) + var(--character-delay)) both, slice-red 6.4s steps(1,end) calc(var(--reveal-delay) + var(--character-delay) + 1.1s) infinite; }
.text-reveal.is-ready .text-reveal__glyph::after { animation: glyph-yellow .52s steps(2,end) calc(var(--reveal-delay) + var(--character-delay) + 36ms) both, slice-yellow 6.4s steps(1,end) calc(var(--reveal-delay) + var(--character-delay) + 1.1s) infinite; }
.text-reveal.is-simple .text-reveal__glyph { opacity: 1; transform: none; filter: none; clip-path: none; animation: none; }
.text-reveal.is-simple .text-reveal__glyph::before,.text-reveal.is-simple .text-reveal__glyph::after { display: none; }
@keyframes glyph-boot { 0%{opacity:0;transform:translate3d(-.24em,.7em,0) scaleX(1.65) skewX(-18deg);filter:blur(8px);clip-path:inset(0 0 100% 0)} 25%{opacity:1;transform:translate3d(.13em,-.04em,0) scaleX(.74) skewX(10deg);filter:blur(0);clip-path:inset(58% 0 3% 0)} 47%{transform:translate3d(-.08em,.02em,0) scaleX(1.34);clip-path:polygon(0 4%,100% 4%,100% 31%,8% 31%,8% 56%,100% 56%,100% 92%,0 92%)} 68%{transform:translate3d(.035em,0,0) scaleX(.92);clip-path:inset(9% 0 43% 0)} 100%{opacity:1;transform:none;filter:none;clip-path:inset(0)} }
@keyframes glyph-red { 0%,100%{opacity:0} 18%,42%{opacity:.9;transform:translateX(-.1em)} 58%{opacity:.45;transform:translateX(.04em)} }
@keyframes glyph-yellow { 0%,100%{opacity:0} 20%,48%{opacity:.95;transform:translateX(.12em)} 66%{opacity:.35;transform:translateX(-.03em)} }
@keyframes glyph-twitch { 0%,91%,94%,100%{transform:none} 92%{transform:translateX(-.025em) skewX(-2deg)} 93%{transform:translateX(.025em)} }
@keyframes slice-red { 0%,90%,95%,100%{opacity:0;transform:translateX(-.04em) scaleX(1)} 91%{opacity:.9;transform:translateX(-.16em) scaleX(1.3);clip-path:inset(12% 0 57%)} 93%{opacity:.55;transform:translateX(.09em) scaleX(.82);clip-path:inset(61% 0 8%)} }
@keyframes slice-yellow { 0%,90%,95%,100%{opacity:0;transform:translateX(.04em) scaleX(1)} 92%{opacity:.85;transform:translateX(.14em) scaleX(1.26);clip-path:inset(48% 0 17%)} 94%{opacity:.4;transform:translateX(-.06em) scaleX(.9);clip-path:inset(17% 0 60%)} }
@media (max-width:680px) { .text-reveal{transform:scaleX(1.04)} }
@media (prefers-reduced-motion:reduce) { .text-reveal__glyph { opacity:1;transform:none;filter:none;clip-path:none;animation:none!important; }.text-reveal__glyph::before,.text-reveal__glyph::after{display:none} }
</style>
