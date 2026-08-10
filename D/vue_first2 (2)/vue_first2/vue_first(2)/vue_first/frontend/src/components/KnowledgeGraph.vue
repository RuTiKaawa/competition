<template>
  <div ref="containerRef" class="w-full" style="height: 560px;"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'

const props = defineProps<{
  nodes?: Array<{
    id: string
    name: string
    label: string
    columns: number
    connected: boolean
    nodeType?: string        // 业务对象 / 业务指标 / 业务规则 / 分析主题
    subFields?: Array<{ name: string; type: string; ktype: string }>  // 子字段
    rowCount?: number
    icon?: string
  }>
  relationships: Array<{
    source_table: string
    source_column: string
    target_table: string
    target_column: string
    type: string
    description?: string
  }>
}>()

const containerRef = ref<HTMLElement | null>(null)
let network: any = null

async function renderGraph() {
  if (!containerRef.value || !(props.nodes?.length || props.relationships.length)) return

  // 动态导入 vis-network 和 vis-data
  const { Network } = await import('vis-network')
  const { DataSet } = await import('vis-data')

  // 收集所有节点
  const nodeSet = new Set<string>()
  props.relationships.forEach((r) => {
    nodeSet.add(r.source_table)
    nodeSet.add(r.target_table)
  })

  const nodeDetails = new Map((props.nodes || []).map((node) => [node.id, node]))
  if (props.nodes?.length) {
    props.nodes.forEach((node) => nodeSet.add(node.id))
  }

  const nodes = new DataSet(
    Array.from(nodeSet).map((name) => {
      const detail = nodeDetails.get(name)
      const kt = detail?.nodeType || '业务对象'
      const isTable = !!detail && (kt === '业务对象' || !kt)
      const subInfo = detail?.subFields
        ? detail.subFields.slice(0, 6).map((f: any) => `${f.name}(${f.ktype})`).join(', ')
        : ''

      return {
        id: name,
        label: `${getNodeIcon(name, kt)} ${detail?.label || name}${detail?.connected ? '' : ''}`,
        title: [
          `📋 ${name}`,
          `知识类型：${kt}`,
          `字段数：${detail?.columns || 0}`,
          detail?.rowCount ? `数据行数：${detail.rowCount.toLocaleString()}` : '',
          detail?.connected ? '🔗 存在表间关系' : '⚪ 暂无外键关系',
          subInfo ? `📌 关键字段：${subInfo}` : '',
        ].filter(Boolean).join('\n'),
        shape: isTable ? 'box' : 'ellipse',
        color: getNodeColorByType(name, kt),
        borderWidth: isTable ? 3 : 2,
        borderRadius: isTable ? 12 : 24,
        font: { color: getNodeFontColor(kt), size: isTable ? 14 : 12, face: 'ZCOOL QingKe HuangYou', bold: { color: getNodeFontColor(kt) } },
        margin: { top: isTable ? 16 : 10, bottom: isTable ? 16 : 10, left: isTable ? 20 : 14, right: isTable ? 20 : 14 },
        widthConstraint: { minimum: isTable ? 180 : 100, maximum: isTable ? 300 : 200 },
        heightConstraint: { minimum: isTable ? 56 : 36 },
        value: detail?.connected ? 30 : (isTable ? 20 : 12),
      }
    })
  )

  const edges = new DataSet(
    props.relationships.map((r, idx) => ({
      id: idx,
      from: r.source_table,
      to: r.target_table,
      label: r.source_column && r.target_column ? `${r.source_column} → ${r.target_column}` : '关联',
      title: `${r.description || `${r.source_table}.${r.source_column} → ${r.target_table}.${r.target_column}`}\n关系类型：${r.type || 'unknown'}`,
      arrows: { to: { enabled: true, type: 'arrow' } },
      color: { color: getEdgeColor(r.type), highlight: '#fcee0a' },
      font: { size: 11, color: '#b7ad8e', strokeWidth: 3, strokeColor: '#080604' },
      width: r.type === 'foreign_key' ? 3 : 2,
      smooth: { type: 'curvedCW', roundness: 0.35 },
    }))
  )

  const data = { nodes, edges }
  const options = {
    layout: {
      improvedLayout: true,
      hierarchical: false,
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      zoomView: true,
      dragView: true,
      dragNodes: true,
      multiselect: true,
      navigationButtons: true,
    },
    edges: {
      smooth: { enabled: true, type: 'dynamic' },
      color: { color: '#786f50', highlight: '#fcee0a' },
    },
    nodes: {
      shapeProperties: { borderRadius: 12 },
      scaling: { min: 18, max: 36 },
      shadow: { enabled: true, color: 'rgba(0,0,0,0.42)', size: 16, x: 0, y: 6 },
    },
    physics: {
      enabled: true,
      stabilization: { enabled: true, iterations: 200, updateInterval: 25 },
      barnesHut: { gravitationalConstant: -2000, centralGravity: 0.1, springLength: 200, springConstant: 0.08, damping: 0.4 },
    },
  }

  network = new Network(containerRef.value, data as any, options as any)
}

function getNodeColorByType(name: string, kt: string) {
  const map: Record<string, { background: string; border: string; highlight: { background: string; border: string } }> = {
    '业务对象': { background: '#19130c', border: '#fcee0a', highlight: { background: '#30270d', border: '#fff36a' } },
    '业务指标': { background: '#22100d', border: '#ff3b36', highlight: { background: '#421714', border: '#ff716c' } },
    '业务规则': { background: '#2b230c', border: '#d8c900', highlight: { background: '#43370d', border: '#fcee0a' } },
    '分析主题': { background: '#27100d', border: '#ff2b27', highlight: { background: '#461714', border: '#fcee0a' } },
  }
  if (map[kt]) return map[kt]

  // fallback by table prefix
  const bgMap: Record<string, string> = { dim_: '#19130c', mes_: '#21170b', qms_: '#26100d', eqp_: '#2a210b', inv_: '#17110b' }
  const borderMap: Record<string, string> = { dim_: '#fcee0a', mes_: '#d6c900', qms_: '#ff3d38', eqp_: '#e5d700', inv_: '#ff5a55' }
  for (const [prefix, bg] of Object.entries(bgMap)) {
    if (name.startsWith(prefix)) return { background: bg, border: borderMap[prefix] || '#fcee0a', highlight: { background: '#3a2e0c', border: '#fcee0a' } }
  }
  return { background: '#17110b', border: '#8f835b', highlight: { background: '#35280d', border: '#fcee0a' } }
}

function getNodeFontColor(kt: string): string {
  const map: Record<string, string> = {
    '业务对象': '#fcee0a',
    '业务指标': '#ff7772',
    '业务规则': '#f2e7b9',
    '分析主题': '#ff4d48',
  }
  return map[kt] || '#d8cfb2'
}

function getNodeIcon(name: string, kt?: string): string {
  const iconMap: Record<string, string> = {
    '业务对象': '📦',
    '业务指标': '📊',
    '业务规则': '📏',
    '分析主题': '🎯',
  }
  if (kt && iconMap[kt]) return iconMap[kt]
  if (name.startsWith('dim_')) return '📘'
  if (name.startsWith('mes_')) return '🏭'
  if (name.startsWith('qms_')) return '✅'
  if (name.startsWith('eqp_')) return '⚙️'
  if (name.startsWith('inv_')) return '📦'
  return '📄'
}

function getEdgeColor(relType: string): string {
  const map: Record<string, string> = {
    'foreign_key': '#fcee0a',
    'belongs_to': '#ff3d38',
    'has_many': '#d4c700',
    'reference': '#8f8566',
  }
  return map[relType] || '#9b916f'
}

onMounted(async () => {
  await nextTick()
  renderGraph()
})

watch(() => [props.nodes, props.relationships], async () => {
  if (network) {
    network.destroy()
    network = null
  }
  await nextTick()
  renderGraph()
})
</script>
