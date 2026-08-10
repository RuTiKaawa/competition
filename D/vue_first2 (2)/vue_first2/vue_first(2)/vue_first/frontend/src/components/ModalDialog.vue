<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="visible" class="modal-layer" role="dialog" aria-modal="true" :aria-label="title" @click.self="close">
        <div class="modal-backdrop" @click="close"></div>
        <div class="modal-panel" :style="{ width, maxHeight }">
          <header><div><small>ORIPIO / DETAIL</small><h3>{{ title }}</h3></div><button aria-label="关闭弹窗" @click="close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-width="1.7" d="M6 6l12 12M18 6 6 18"/></svg></button></header>
          <div class="modal-body"><slot /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ visible: boolean; title: string; width?: string; maxHeight?: string }>(), { width: '720px', maxHeight: '82vh' })
const emit = defineEmits<{ (event: 'close'): void }>()
const close = () => emit('close')
</script>

<style scoped>
.modal-layer { position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;padding:20px;color:#cad8e2; }.modal-backdrop { position:absolute;inset:0;background:rgba(1,5,11,.78);backdrop-filter:blur(9px); }.modal-panel { position:relative;display:flex;max-width:calc(100vw - 28px);flex-direction:column;overflow:hidden;border:1px solid rgba(136,189,211,.18);border-radius:22px;background:linear-gradient(145deg,rgba(15,24,38,.97),rgba(8,13,23,.98));box-shadow:0 28px 90px rgba(0,0,0,.58),inset 0 1px rgba(255,255,255,.04); }.modal-panel header { display:flex;align-items:center;justify-content:space-between;padding:19px 22px;border-bottom:1px solid rgba(146,185,207,.1); }.modal-panel header small { color:#52cdbb;font-size:8px;letter-spacing:.18em; }.modal-panel h3 { margin-top:4px;color:#eef6fa;font-size:17px;font-weight:580; }.modal-panel header button { display:grid;width:32px;height:32px;place-items:center;border:1px solid rgba(145,181,204,.12);border-radius:9px;color:#768a99;background:rgba(255,255,255,.03);cursor:pointer; }.modal-panel svg { width:17px;height:17px; }.modal-body { flex:1;overflow-y:auto;padding:20px 22px; }.modal-fade-enter-active,.modal-fade-leave-active { transition:opacity .2s; }.modal-fade-enter-active .modal-panel,.modal-fade-leave-active .modal-panel { transition:transform .24s,opacity .2s; }.modal-fade-enter-from,.modal-fade-leave-to { opacity:0; }.modal-fade-enter-from .modal-panel,.modal-fade-leave-to .modal-panel { opacity:0;transform:translateY(8px) scale(.985); }
</style>
