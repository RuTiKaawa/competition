<script setup lang="ts">
import type { PropType } from 'vue'

export interface StatItem {
  label: string
  value: number
  change: number
  icon: string
}

const props = defineProps({
  stat: {
    type: Object as PropType<StatItem>,
    required: true,
  },
})

const isPositive = props.stat.change >= 0
</script>

<template>
  <div class="bg-white rounded-xl shadow-sm p-5 border border-gray-100/50 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-xs text-gray-400 font-medium uppercase tracking-wider">{{ stat.label }}</p>
        <p class="text-2xl font-bold text-gray-800 mt-1">
          {{ stat.value.toLocaleString() }}
        </p>
      </div>
      <span class="text-2xl">{{ stat.icon }}</span>
    </div>
    <div class="flex items-center gap-1.5 mt-3">
      <span class="text-xs font-semibold" :class="isPositive ? 'text-success' : 'text-danger'">
        {{ isPositive ? '↑' : '↓' }} {{ Math.abs(stat.change).toFixed(2) }}%
      </span>
      <span class="text-xs text-gray-400">较上期</span>
    </div>
  </div>
</template>