<template>

  <div class="knowledge-studio space-y-6">

    <!-- ====== 顶部说明 ====== -->

    <div class="bg-gradient-to-r from-blue-50/80 to-purple-50/80 rounded-xl p-5 border border-blue-100">

      <div class="flex items-start gap-3">

        <span class="text-2xl mt-0.5">🧠</span>

        <div>

          <div class="font-semibold text-gray-700 text-sm">业务知识库</div>

          <div class="text-xs text-gray-500 mt-0.5 leading-relaxed">

            业务知识是连接 <span class="text-blue-600 font-medium">自然语言问题</span> 与 <span class="text-blue-600 font-medium">数据底座</span> 的桥梁。

            系统围绕制造业典型场景，梳理了业务对象、业务指标、业务规则和分析主题，

            帮助大模型准确理解用户意图，生成正确的 SQL 和分析结果。

          </div>

        </div>

      </div>

    </div>



    <!-- ====== 视图切换 Tab ====== -->

    <div class="flex items-center gap-2 border-b border-gray-200">

      <button

        v-for="view in viewTabs"

        :key="view.key"

        @click="activeView = view.key"

        class="px-4 py-2 text-sm font-medium transition-all border-b-2"

        :class="activeView === view.key ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-400 hover:text-gray-600'"

      >

        {{ view.icon }} {{ view.name }}

      </button>

      <span class="ml-auto text-xs text-gray-400">📊 共 {{ tableCount }} 张表 · {{ totalRows }} 行数据</span>

    </div>

    <!-- ====== 加载 / 错误 状态 ====== -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-center">
        <div class="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3"></div>
        <span class="text-sm text-gray-500">正在从数据库加载业务知识…</span>
      </div>
    </div>
    <div v-else-if="errorMsg" class="bg-red-50 rounded-xl p-6 border border-red-200 text-center">
      <span class="text-red-500 text-sm">⚠️ 加载失败：{{ errorMsg }}</span>
      <div class="mt-2 text-xs text-gray-400">请确保后端服务已启动（python main.py）</div>
    </div>

    <!-- ====== 视图1：场景导航视图 ====== -->
    <template v-else-if="activeView === 'scene'">
      <div class="grid gap-3" :style="`grid-template-columns: repeat(${Math.min(scenes.length, 4)}, minmax(0, 1fr))`">
        <div
          v-for="scene in scenes"
          :key="scene.key"
          @click="activeScene = scene.key"
          class="rounded-xl p-4 cursor-pointer transition-all border-2"
          :class="activeScene === scene.key ? 'border-blue-500 bg-blue-50/50 shadow-sm' : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'"
        >
          <div class="flex items-center gap-2">
            <span class="text-xl">{{ scene.icon }}</span>
            <span class="font-semibold text-sm text-gray-700">{{ scene.name }}</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">{{ scene.desc }}</div>
          <div class="text-[10px] text-blue-500 mt-1.5" v-if="activeScene === scene.key">● 当前查看</div>
          <div class="text-[10px] text-gray-400 mt-1">{{ scenesMap[scene.key]?.objects?.length || 0 }} 张数据表</div>
        </div>
      </div>

      <div class="grid grid-cols-5 gap-4 mt-3">
        <div class="col-span-3 space-y-3">
          <div class="bg-white rounded-xl p-4 border border-gray-200">
            <div class="flex items-center gap-2 mb-3">
              <span class="text-lg">📦</span>
              <span class="font-semibold text-sm text-gray-700">{{ scenesMap[activeScene]?.name || '当前场景' }} — 数据表</span>
              <span class="text-[10px] text-gray-400 ml-auto">{{ currentSceneData.objects?.length || 0 }} 张表</span>
            </div>
            <div class="space-y-2 max-h-[600px] overflow-y-auto">
              <div v-if="!currentSceneData.objects?.length" class="text-center py-8 text-gray-400 text-sm">该场景下暂无数据表</div>
              <div v-for="obj in currentSceneData.objects" :key="obj.table" class="flex items-start gap-2 p-3 rounded-lg hover:bg-gray-50 transition cursor-pointer border border-transparent hover:border-gray-100" @click="openObjectDetail(obj)">
                <span class="text-sm mt-0.5">{{ obj.icon || '📋' }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-mono font-medium text-sm text-blue-600">{{ obj.table }}</span>
                    <span v-if="obj.is_core" class="text-[10px] text-orange-500 bg-orange-50 px-1.5 py-0.5 rounded">核心</span>
                    <span v-if="obj.row_count !== undefined" class="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">{{ obj.row_count.toLocaleString() }} 行</span>
                  </div>
                  <div class="text-xs text-gray-400 mt-0.5">{{ obj.desc }}</div>
                  <div class="flex flex-wrap gap-1 mt-1">
                    <span v-for="field in (obj.fields || [])" :key="field" class="text-[10px] text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded font-mono">{{ field }}</span>
                    <span v-if="(obj.fields || []).length > 8" class="text-[10px] text-gray-300">+{{ (obj.fields || []).length - 8 }} 更多</span>
                  </div>
                </div>
                <span class="text-xs text-gray-300 mt-1 flex-shrink-0">→</span>
              </div>
            </div>
          </div>
        </div>

        <div class="col-span-2 space-y-3">
          <div class="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
            <div class="text-sm font-semibold text-gray-700 mb-2">💡 数据来源</div>
            <div class="text-xs text-gray-500 leading-relaxed">以上数据表均从 <span class="font-mono text-blue-600">PostgreSQL</span> 数据库中实时获取。表名和字段名与实际数据库结构完全一致，点击任意表可查看完整的字段列表及类型信息。</div>
          </div>
          <div class="bg-white rounded-xl p-4 border border-gray-200">
            <div class="text-sm font-semibold text-gray-700 mb-3">📊 当前场景概览</div>
            <div class="space-y-2 text-xs">
              <div class="flex justify-between"><span class="text-gray-400">数据表数量</span><span class="font-medium text-gray-700">{{ currentSceneData.objects?.length || 0 }}</span></div>
              <div class="flex justify-between"><span class="text-gray-400">核心表</span><span class="font-medium text-orange-500">{{ (currentSceneData.objects || []).filter((o: any) => o.is_core).length }}</span></div>
              <div class="flex justify-between"><span class="text-gray-400">总字段数</span><span class="font-medium text-gray-700">{{ (currentSceneData.objects || []).reduce((sum: number, o: any) => sum + (o.columns?.length || 0), 0) }}</span></div>
              <div class="flex justify-between"><span class="text-gray-400">总数据行数</span><span class="font-medium text-gray-700">{{ (currentSceneData.objects || []).reduce((sum: number, o: any) => sum + (o.row_count || 0), 0).toLocaleString() }}</span></div>
            </div>
          </div>
          <div class="bg-white rounded-xl p-4 border border-gray-200">
            <div class="text-sm font-semibold text-gray-700 mb-2">🔗 表关联关系</div>
            <div class="text-xs text-gray-500 leading-relaxed">通过字段名中的 <span class="font-mono text-blue-600">_id</span> 后缀可识别外键关系。例如 <span class="font-mono">product_id</span> → <span class="font-mono">dim_product</span>。</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ====== 视图2：知识图谱视图 ====== -->
    <template v-else-if="activeView === 'graph'">
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="flex items-center justify-between p-3 border-b border-gray-100 bg-gray-50/50">
          <div class="flex items-center gap-3">
            <span class="text-sm font-medium text-gray-700">🔗 业务知识图谱</span>
            <span class="text-[10px] text-gray-400">拖拽查看</span>
          </div>
          <div class="flex items-center gap-2">
            <button v-for="filter in graphFilters" :key="filter.key" @click="toggleGraphFilter(filter.key)" class="px-2 py-1 text-[10px] rounded transition" :class="activeGraphFilters.includes(filter.key) ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'">{{ filter.label }}</button>
            <button @click="resetGraphZoom" class="text-xs text-gray-400 hover:text-gray-600 px-2">⟲ 重置</button>
          </div>
        </div>
        <div class="p-4 min-h-[680px] bg-slate-50 rounded-b-2xl">
          <!-- 图例 -->
          <div class="flex flex-wrap gap-3 mb-3 text-[10px]">
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-indigo-200 border border-indigo-400"></span> 业务对象</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-emerald-200 border border-emerald-400"></span> 业务指标</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-amber-200 border border-amber-400"></span> 业务规则</span>
            <span class="text-gray-400 ml-2">■ 方形=表级节点 · ● 圆形=字段级节点</span>
          </div>
          <KnowledgeGraph :nodes="graphComponentNodes" :relationships="graphComponentRels" />
        </div>
      </div>

      <div v-if="selectedGraphNode" class="bg-white rounded-xl border border-gray-200 p-4 mt-3">
        <div class="flex items-center justify-between mb-2">
          <span class="font-semibold text-sm text-gray-700">📌 {{ selectedGraphNode.table || selectedGraphNode.label }} 详情</span>
          <button @click="selectedGraphNode = null" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="grid grid-cols-3 gap-4 text-xs">
          <div><span class="text-gray-400">数据表</span><div class="font-medium text-gray-700 font-mono">{{ selectedGraphNode.table }}</div></div>
          <div><span class="text-gray-400">字段数</span><div class="font-medium text-gray-700">{{ selectedGraphNode.fields?.length || 0 }}</div></div>
          <div><span class="text-gray-400">数据行数</span><div class="font-medium text-gray-700">{{ selectedGraphNode.row_count?.toLocaleString() || '-' }}</div></div>
        </div>
        <div class="mt-2 text-xs text-gray-500">{{ selectedGraphNode.desc }}</div>
        <div v-if="selectedGraphNode.columns?.length" class="mt-2 flex flex-wrap gap-1">
          <span v-for="(col, ci) in selectedGraphNode.columns.slice(0, 10)" :key="ci" class="text-[10px] text-blue-600 bg-blue-50 px-2 py-0.5 rounded font-mono" :title="col.type + (col.comment ? ' — ' + col.comment : '')">{{ col.name }}</span>
          <span v-if="selectedGraphNode.columns.length > 10" class="text-[10px] text-gray-400">+{{ selectedGraphNode.columns.length - 10 }} 更多</span>
        </div>
      </div>
    </template>

    <!-- ====== 视图3：术语词典视图 ====== -->
    <template v-else-if="activeView === 'terms'">
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="p-4 border-b border-gray-100">
          <div class="flex flex-wrap items-center gap-3">
            <span class="text-lg">📖</span>
            <span class="font-semibold text-sm text-gray-700">业务术语词典</span>
            <span class="text-[10px] text-gray-400 ml-auto">共 {{ termDictionary.length }} 个术语</span>
          </div>
          <div class="mt-3 grid gap-2 md:grid-cols-[1fr_auto_auto]">
            <input v-model="termSearch" type="text" placeholder="搜索术语、英文名、定义、分类..." class="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20" />
            <select v-model="termCategoryFilter" class="w-full md:w-36 px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20">
              <option value="">全部分类</option>
              <option v-for="category in termCategories" :key="category" :value="category">{{ category }}</option>
            </select>
            <select v-model="termTypeFilter" class="w-full md:w-36 px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20">
              <option value="">全部类型</option>
              <option v-for="kt in knowledgeTypes" :key="kt" :value="kt">{{ kt }}</option>
            </select>
          </div>
        </div>

        <!-- 按知识类型分组展示 -->
        <div class="max-h-[520px] overflow-y-auto">
          <div v-if="!filteredTerms.length" class="p-6 text-center text-sm text-gray-500">未找到匹配术语，请尝试更换关键词或清空筛选。</div>

          <div v-for="group in groupedTerms" :key="group.type" class="border-b border-gray-100 last:border-b-0">
            <!-- 分组标题 -->
            <div class="flex items-center gap-2 px-4 py-2.5 bg-gray-50/80 sticky top-0 z-10">
              <span class="text-sm">{{ typeIcons[group.type] || '📋' }}</span>
              <span class="font-medium text-xs text-gray-700">{{ group.type }}</span>
              <span class="text-[10px] text-gray-400">（{{ group.items.length }} 个术语）</span>
            </div>
            <!-- 分组项 -->
            <div v-for="term in group.items" :key="term.term" class="px-4 py-3 hover:bg-blue-50/40 transition cursor-pointer group" @click="openTermDetail(term)">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-sm text-slate-900 group-hover:text-blue-600 transition">{{ term.term }}</span>
                    <span class="text-[10px] text-white px-2 py-0.5 rounded-full" :class="typeBadgeClass(term.knowledge_type)">{{ term.knowledge_type }}</span>
                    <span class="text-[10px] text-white bg-sky-500 px-2 py-0.5 rounded-full">{{ term.category }}</span>
                  </div>
                  <div class="text-xs text-gray-500 mt-1 line-clamp-2">{{ term.definition }}</div>
                </div>
                <div class="text-right flex-shrink-0">
                  <div class="text-xs text-gray-600 font-mono bg-gray-100 group-hover:bg-blue-100 px-2 py-1 rounded transition">{{ term.en }}</div>
                  <div class="text-[10px] text-gray-400 mt-0.5">英文名</div>
                </div>
              </div>
              <div class="flex flex-wrap gap-2 mt-2 text-[10px]">
                <span class="text-slate-500 bg-slate-50 px-2 py-0.5 rounded font-mono">类型：{{ term.data_type || '-' }}</span>
                <span v-if="term.abbreviation" class="text-sky-700 bg-sky-50 px-2 py-0.5 rounded-full">简称：{{ term.abbreviation }}</span>
                <span v-if="term.mapped_table" class="text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">来源：{{ term.mapped_table }}{{ term.mapped_field ? '.' + term.mapped_field : '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ====== 视图4：分析模板 ====== -->
    <template v-else-if="activeView === 'templates'">
      <div class="flex flex-col gap-4">
        <div class="flex flex-wrap items-center gap-3 p-4 bg-white rounded-xl border border-gray-200">
          <div>
            <div class="text-lg">🧩</div>
            <div class="font-semibold text-sm text-gray-700">分析模板助手</div>
            <div class="text-[10px] text-gray-400">快速选用常见业务分析主题，生成标准问题和参考指标</div>
          </div>
          <input v-model="templateSearch" type="text" placeholder="搜索模板名称、场景、标签..." class="flex-1 min-w-[200px] px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20" />
          <select v-model="templateSceneFilter" class="w-full max-w-[220px] px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20">
            <option value="">全部场景</option>
            <option v-for="scene in templateScenes" :key="scene" :value="scene">{{ scene }}</option>
          </select>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-if="!filteredTemplates.length" class="bg-white rounded-xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-500">暂无符合条件的模板。请调整搜索词或清空筛选。</div>
          <div v-for="template in filteredTemplates" :key="template.id" class="group bg-white rounded-3xl border border-gray-200 p-5 transition hover:shadow-lg cursor-pointer" @click="applyTemplate(template)">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-2xl leading-none">{{ template.icon }}</div>
                <div class="font-semibold text-base text-slate-900 mt-2">{{ template.name }}</div>
              </div>
              <span class="text-[10px] uppercase tracking-[.2em] text-slate-500 bg-slate-100 px-3 py-1 rounded-full">{{ template.scene }}</span>
            </div>
            <div class="text-sm text-gray-600 mt-3">{{ template.desc }}</div>
            <div class="flex flex-wrap gap-2 mt-4">
              <span v-for="tag in template.tags" :key="tag" class="text-[10px] text-slate-600 bg-slate-50 px-2 py-1 rounded-full">{{ tag }}</span>
            </div>
            <div class="mt-4 grid gap-2 sm:grid-cols-2 text-[11px] text-gray-500">
              <div class="bg-blue-50 rounded-xl px-3 py-2">💡 示例问题：<span class="font-medium text-slate-700">{{ template.example_question }}</span></div>
              <div class="bg-slate-50 rounded-xl px-3 py-2">📊 指标：{{ template.metrics_count }} 张表：{{ template.tables_count }}</div>
            </div>
            <button type="button" class="mt-4 w-full rounded-full bg-blue-600 text-white text-sm py-2 transition group-hover:bg-blue-700">应用该模板</button>
          </div>
        </div>
      </div>
    </template>

    <!-- ====== 底部 ====== -->
    <div class="bg-gray-50/80 rounded-xl p-4 border border-gray-200 text-center">
      <span class="text-xs text-gray-400">💡 业务知识是智能问析的核心 —— 系统通过理解业务对象、指标、规则和主题，将您的自然语言问题转化为准确的数据分析任务</span>
    </div>

    <!-- ====== 详情弹窗 ====== -->
    <div v-if="detailModal" class="fixed inset-0 bg-black/30 flex items-center justify-center z-50" @click.self="closeModal">
      <div class="bg-white rounded-xl p-6 max-w-2xl w-full mx-4 shadow-xl max-h-[80vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
          <span class="font-semibold text-gray-700">{{ detailModal.title }}</span>
          <button @click="closeModal" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="space-y-3 text-sm"><div v-html="detailModal.content"></div></div>
        <div class="mt-4 flex justify-end"><button @click="closeModal" class="px-4 py-1.5 text-sm bg-gray-100 rounded-lg hover:bg-gray-200">关闭</button></div>
      </div>
    </div>

  </div>
</template>



<script setup lang="ts">

import { ref, computed, onMounted } from 'vue'
import KnowledgeGraph from '../components/KnowledgeGraph.vue'

const props = defineProps<{
  initialScene?: string
}>()

const emit = defineEmits<{
  'navigate-ask': [question: string]
}>()



// ========== API 基础地址 ==========

// 通过 Vite 代理访问后端（vite.config.ts 将 /api 转发到后端端口）
const API_BASE = '/api'

// ========== 加载状态 ==========

const loading = ref(true)

const errorMsg = ref('')



// ========== 视图切换 ==========

const viewTabs = [

  { key: 'scene', icon: '📂', name: '场景知识' },

  { key: 'graph', icon: '🔗', name: '知识图谱' },

  { key: 'terms', icon: '📖', name: '术语词典' },

  { key: 'templates', icon: '📝', name: '分析模板' },

]

const activeView = ref('scene')



// ========== 场景数据 ==========

const scenesMap = ref<Record<string, any>>({})

const activeScene = ref('production')



const scenes = computed(() => {

  const keys = Object.keys(scenesMap.value)

  if (keys.length === 0) return []

  return keys.map(k => ({

    key: scenesMap.value[k].key,

    icon: scenesMap.value[k].icon,

    name: scenesMap.value[k].name,

    desc: scenesMap.value[k].desc,

  }))

})



const currentSceneData = computed(() => {

  return scenesMap.value[activeScene.value] || { objects: [] }

})



const tableCount = computed(() => {

  let count = 0

  Object.values(scenesMap.value).forEach((s: any) => {

    count += (s.objects || []).length

  })

  return count

})



const totalRows = computed(() => {

  let total = 0

  Object.values(scenesMap.value).forEach((s: any) => {

    ;(s.objects || []).forEach((o: any) => {

      total += (o.row_count || 0)

    })

  })

  return total

})



// ========== 加载知识数据 ==========

const loadKnowledge = async () => {

  loading.value = true

  errorMsg.value = ''

  try {

    const [scenesRes, termsRes] = await Promise.all([

      fetch(`${API_BASE}/knowledge/scenes`),

      fetch(`${API_BASE}/knowledge/terms`),

    ])



    if (!scenesRes.ok) throw new Error(`场景接口返回 ${scenesRes.status}`)

    if (!termsRes.ok) throw new Error(`术语接口返回 ${termsRes.status}`)



    const scenesJson = await scenesRes.json()

    const termsJson = await termsRes.json()



    scenesMap.value = scenesJson.scenes || {}

    termDictionary.value = termsJson.terms || []



    // 确保有选中的场景

    const keys = Object.keys(scenesMap.value)

    if (keys.length > 0 && !scenesMap.value[activeScene.value]) {

      activeScene.value = keys[0]

    }

  } catch (e: any) {

    errorMsg.value = e.message || '加载失败'

    console.error('知识数据加载失败:', e)

  } finally {

    loading.value = false

  }

}



// ========== 详情弹窗 ==========

const detailModal = ref<any>(null)



const openObjectDetail = (obj: any) => {

  const fieldHtml = (obj.columns || []).map((c: any) => `

    <div class="flex items-center gap-2 text-xs py-0.5 border-b border-gray-50">

      <span class="font-mono text-blue-600 min-w-[120px]">${c.name}</span>

      <span class="text-gray-400 min-w-[80px]">${c.type}</span>

      ${c.primary_key ? '<span class="text-yellow-500">🔑</span>' : ''}

      ${!c.nullable ? '<span class="text-red-400 text-[10px]">NOT NULL</span>' : ''}

      <span class="text-gray-500 text-[10px]">${c.comment || ''}</span>

    </div>

  `).join('')



  detailModal.value = {

    title: `${obj.icon || '📦'} ${obj.table}`,

    content: `

      <div class="grid grid-cols-3 gap-4 mb-4">

        <div><strong>数据表：</strong><span class="font-mono text-blue-600">${obj.table}</span></div>

        <div><strong>字段数：</strong>${obj.columns?.length || 0}</div>

        <div><strong>数据行数：</strong>${(obj.row_count || 0).toLocaleString()}</div>

      </div>

      <div><strong>描述：</strong>${obj.desc || '暂无描述'}</div>

      ${obj.is_core ? '<div class="mt-2 text-xs text-orange-500">⭐ 核心业务对象</div>' : ''}

      <div class="mt-4"><strong>字段列表：</strong></div>

      <div class="mt-2 max-h-60 overflow-y-auto bg-gray-50 rounded-lg p-2">

        ${fieldHtml || '无字段信息'}

      </div>

    `

  }

}



const closeModal = () => {

  detailModal.value = null

}



// ========== 知识图谱 ==========

const graphFilters = [
  { key: '业务对象', label: '📦 对象' },
  { key: '业务指标', label: '📊 指标' },
  { key: '业务规则', label: '📏 规则' },
]
const activeGraphFilters = ref<string[]>(['业务对象', '业务指标', '业务规则'])

const selectedGraphNode = ref<any>(null)



const toggleGraphFilter = (key: string) => {

  const idx = activeGraphFilters.value.indexOf(key)

  if (idx > -1) activeGraphFilters.value.splice(idx, 1)

  else activeGraphFilters.value.push(key)

}



const resetGraphZoom = () => {

  selectedGraphNode.value = null

}



// ========== Graph component data准备（从 scenes + relations 生成） ==========
const graphComponentNodes = ref<any[]>([])
const graphComponentRels = ref<any[]>([])

// 前端知识类型分类（与后端 _classify_knowledge_type 保持一致）
function classifyFieldType(colName: string, colType: string): string {
  const name = colName.toLowerCase()
  const type = colType.toLowerCase()
  const metricKeys = ['rate', 'count', 'amount', 'qty', 'quantity', 'duration', 'price', 'cost', 'value', 'weight', 'percent', 'ratio', 'score', 'yield', 'output', 'total', 'sum', 'avg', 'max', 'min', 'temperature', 'speed', 'pressure', 'volume', 'length']
  const ruleKeys = ['status', 'type', 'level', 'flag', 'state', 'result', 'grade', 'category', 'class', 'stage', 'phase', 'mode', 'reason', 'check', 'pass', 'fail', 'qualified']
  const isNumeric = ['int', 'float', 'numeric', 'decimal', 'double', 'real'].some(t => type.includes(t))
  if (isNumeric && metricKeys.some(k => name.includes(k))) return '业务指标'
  if (ruleKeys.some(k => name.includes(k))) return '业务规则'
  if (name.endsWith('_id') || name.endsWith('_key')) return '业务对象'
  if (isNumeric) return '业务指标'
  return '业务对象'
}

function classifyTableType(tableName: string): string {
  // 根据表名前缀判断表的整体知识类型
  if (tableName.startsWith('dim_')) return '业务对象'
  if (['mes_work_order', 'mes_process_output'].some(p => tableName.startsWith(p))) return '业务指标'
  if (['qms_defect', 'qms_inspection'].some(p => tableName.startsWith(p))) return '业务规则'
  if (['eqp_downtime'].some(p => tableName.startsWith(p))) return '业务指标'
  if (['inv_inventory'].some(p => tableName.startsWith(p))) return '业务规则'
  return '业务对象'
}

const loadRelations = async () => {
  try {
    // 优先使用新图谱接口（含知识类型分类）
    const graphRes = await fetch(`${API_BASE}/knowledge/graph`)
    if (graphRes.ok) {
      const graphJson = await graphRes.json()
      graphComponentNodes.value = graphJson.nodes || []
      graphComponentRels.value = (graphJson.edges || []).map((e: any) => ({
        source_table: e.source,
        source_column: e.sourceColumn,
        target_table: e.target,
        target_column: e.targetColumn,
        type: e.type,
        description: e.description,
      }))
      return
    }

    // fallback: 使用旧 relations 接口
    const res = await fetch(`${API_BASE}/knowledge/relations`)
    if (!res.ok) throw new Error(`关系接口返回 ${res.status}`)
    const json = await res.json()
    const rels = json.relations || []

    const nodeMap = new Map<string, any>()
    Object.values(scenesMap.value).forEach((s: any) => {
      (s.objects || []).forEach((o: any) => {
        const subFields = (o.columns || []).map((c: any) => ({
          name: c.name,
          type: c.type,
          ktype: classifyFieldType(c.name, c.type),
        }))
        nodeMap.set(o.table, {
          id: o.table,
          name: o.table,
          label: o.label || o.table,
          columns: (o.columns || []).length,
          connected: false,
          nodeType: classifyTableType(o.table),
          subFields,
          rowCount: o.row_count,
          icon: o.icon,
        })
      })
    })

    rels.forEach((r: any) => {
      if (nodeMap.has(r.source_table)) nodeMap.get(r.source_table).connected = true
      if (nodeMap.has(r.target_table)) nodeMap.get(r.target_table).connected = true
      if (!nodeMap.has(r.source_table)) nodeMap.set(r.source_table, { id: r.source_table, name: r.source_table, label: r.source_table, columns: 0, connected: true, nodeType: classifyTableType(r.source_table), subFields: [], rowCount: 0 })
      if (!nodeMap.has(r.target_table)) nodeMap.set(r.target_table, { id: r.target_table, name: r.target_table, label: r.target_table, columns: 0, connected: true, nodeType: classifyTableType(r.target_table), subFields: [], rowCount: 0 })

      graphComponentRels.value.push({
        source_table: r.source_table,
        source_column: r.source_column,
        target_table: r.target_table,
        target_column: r.target_column,
        type: r.type,
        description: r.description,
      })
    })

    graphComponentNodes.value = Array.from(nodeMap.values())
  } catch (e: any) {
    console.error('加载图谱数据失败', e)
  }
}

// 监听 scenes 加载完毕后再加载 relations
onMounted(async () => {
  // scenes 在 loadKnowledge 中赋值，确保先加载过一次
  await loadKnowledge()
  await loadRelations()

  // 如果从总览页传入指定场景，自动切换
  if (props.initialScene && scenesMap.value[props.initialScene]) {
    activeView.value = 'scene'
    activeScene.value = props.initialScene
  }
})



// ========== 术语词典 ==========

const termSearch = ref('')

const termDictionary = ref<any[]>([])

const termCategoryFilter = ref('')
const termTypeFilter = ref('')

const knowledgeTypes = ['业务对象', '业务指标', '业务规则', '分析主题']

const typeIcons: Record<string, string> = {
  '业务对象': '📦',
  '业务指标': '📊',
  '业务规则': '📏',
  '分析主题': '🎯',
}

const typeBadgeClass = (kt: string) => {
  const map: Record<string, string> = {
    '业务对象': 'bg-indigo-500',
    '业务指标': 'bg-emerald-500',
    '业务规则': 'bg-amber-500',
    '分析主题': 'bg-rose-500',
  }
  return map[kt] || 'bg-gray-500'
}

const termCategories = computed(() => {
  const categories = new Set<string>()
  termDictionary.value.forEach((term: any) => {
    if (term.category) categories.add(term.category)
  })
  return Array.from(categories).sort()
})

// 中文关键词 → 对应英文词映射（双向搜索用）
const CN_EN_SEARCH_MAP: Record<string, string[]> = {
  '质量': ['quality', 'defect', 'inspection', 'yield', '合格', '不良', '检验'],
  '生产': ['production', 'process', 'output', 'manufacturing', 'work_order', 'mes'],
  '设备': ['equipment', 'machine', 'downtime', 'maintenance', 'uptime', 'eqp'],
  '库存': ['inventory', 'stock', 'warehouse', 'safety', 'material', 'inv'],
  '工序': ['process', 'step', 'stage'],
  '良率': ['yield', 'rate', 'qualified'],
  '缺陷': ['defect', 'fault', 'reject', 'bad'],
  '停机': ['downtime', 'stop', 'halt'],
  '安全': ['safety', 'secure'],
  '检验': ['inspection', 'check', 'test', 'qc'],
  '物料': ['material', 'item'],
  '工单': ['work_order', 'order'],
  '产品': ['product', 'item'],
  '数据': ['data', 'record'],
}

const filteredTerms = computed(() => {
  const q = termSearch.value.trim()
  let result = termDictionary.value

  if (q) {
    const qLower = q.toLowerCase()
    const expandWords = new Set<string>([qLower])
    for (const [cn, enList] of Object.entries(CN_EN_SEARCH_MAP)) {
      if (qLower.includes(cn) || cn.includes(qLower)) {
        enList.forEach(w => expandWords.add(w.toLowerCase()))
      }
    }
    result = result.filter((t: any) => {
      const haystack = [
        t.term || '', t.en || '', t.definition || '',
        t.category || '', t.abbreviation || '', t.knowledge_type || '',
      ].join(' ').toLowerCase()
      return Array.from(expandWords).some(w => haystack.includes(w))
    })
  }

  if (termCategoryFilter.value) {
    result = result.filter((t: any) => t.category === termCategoryFilter.value)
  }
  if (termTypeFilter.value) {
    result = result.filter((t: any) => t.knowledge_type === termTypeFilter.value)
  }

  return result
})

// 按知识类型分组
const groupedTerms = computed(() => {
  const order = ['业务对象', '业务指标', '业务规则', '分析主题']
  const groups: Record<string, any[]> = {}
  for (const kt of order) groups[kt] = []

  filteredTerms.value.forEach((term: any) => {
    const kt = term.knowledge_type || '业务对象'
    if (groups[kt]) groups[kt].push(term)
    else {
      if (!groups['其他']) groups['其他'] = []
      groups['其他'].push(term)
    }
  })

  return order
    .filter(kt => groups[kt].length > 0)
    .map(kt => ({ type: kt, items: groups[kt] }))
})

const openTermDetail = (term: any) => {
  const kt = term.knowledge_type || '业务对象'
  const icon = typeIcons[kt] || '📋'
  const explainMap: Record<string, string> = {
    '业务对象': '业务对象是数据建模中的核心实体，如产品、工序、设备等。它们通过外键相互关联，构成数据分析的基础维度。',
    '业务指标': '业务指标是可量化、可度量的数值，如良率、产量、停机时长等。它们是 KPI 看板和分析报表的核心数据。',
    '业务规则': '业务规则定义了判断逻辑和分类标准，如状态、等级、类型等。它们用于数据筛选、条件判断和异常识别。',
    '分析主题': '分析主题是面向具体业务问题的知识集合，围绕某一分析目标组织相关的对象、指标和规则。',
  }
  detailModal.value = {
    title: `${icon} ${term.term}`,
    content: `
      <div class="space-y-4 text-sm">
        <div class="grid grid-cols-3 gap-3">
          <div class="bg-indigo-50 rounded-xl p-3 text-center">
            <div class="text-xs text-indigo-500 mb-1">知识类型</div>
            <div class="font-semibold text-indigo-700">${kt}</div>
          </div>
          <div class="bg-blue-50 rounded-xl p-3 text-center">
            <div class="text-xs text-blue-500 mb-1">📝 英文名称</div>
            <div class="font-mono font-semibold text-blue-700">${term.en || '-'}</div>
          </div>
          <div class="bg-orange-50 rounded-xl p-3 text-center">
            <div class="text-xs text-orange-500 mb-1">🏷️ 简称</div>
            <div class="font-mono font-semibold text-orange-700">${term.abbreviation || '-'}</div>
          </div>
        </div>
        <div class="bg-amber-50 rounded-xl p-3 text-xs text-amber-700 leading-relaxed">
          💡 <strong>${kt}说明：</strong>${explainMap[kt] || ''}
        </div>
        <div class="bg-gray-50 rounded-xl p-4">
          <div class="text-xs text-gray-400 mb-1">📄 术语定义</div>
          <div class="text-gray-700 leading-relaxed">${term.definition || '暂无详细定义'}</div>
        </div>
        <div class="grid grid-cols-3 gap-3 text-xs">
          <div><span class="text-gray-400">业务分类：</span><span class="font-medium text-gray-700">${term.category || '-'}</span></div>
          <div><span class="text-gray-400">数据类型：</span><span class="font-mono text-blue-600">${term.data_type || '-'}</span></div>
          <div><span class="text-gray-400">来源表：</span><span class="font-mono text-blue-600">${term.mapped_table || '-'}</span></div>
        </div>
        ${term.mapped_field ? `<div class="text-xs"><span class="text-gray-400">映射字段：</span><span class="font-mono text-blue-600">${term.mapped_field}</span></div>` : ''}
        <div class="mt-2 text-xs text-gray-400">💡 在智能问析中使用以上术语可以更准确地生成 SQL 查询和数据分析结果</div>
      </div>
    `,
  }
}

// ========== 分析模板 ==========

const templateSearch = ref('')
const templateSceneFilter = ref('')

const templateScenes = computed(() => {
  const scenes = new Set<string>()
  knowledgeTemplates.forEach((tpl: any) => {
    if (tpl.scene) scenes.add(tpl.scene)
  })
  return Array.from(scenes).sort()
})

const filteredTemplates = computed(() => {
  const keyword = templateSearch.value.trim().toLowerCase()
  return knowledgeTemplates.filter((tpl: any) => {
    const matchesSearch = !keyword ||
      tpl.name.toLowerCase().includes(keyword) ||
      tpl.scene.toLowerCase().includes(keyword) ||
      tpl.desc.toLowerCase().includes(keyword) ||
      tpl.tags.some((tag: string) => tag.toLowerCase().includes(keyword))

    const matchesScene = !templateSceneFilter.value || tpl.scene === templateSceneFilter.value
    return matchesSearch && matchesScene
  })
})

const knowledgeTemplates = [
  {
    id: 'tpl_001',
    icon: '📊',
    name: '周质量分析报告',
    scene: '质量分析',
    desc: '自动生成本周质量概况，包括合格率趋势、不良TOP5、各工序质量表现',
    tags: ['质量', '周报', '自动报告'],
    example_question: '请生成一份本周质量分析报告',
    metrics_count: 5,
    tables_count: 3,
  },
  {
    id: 'tpl_002',
    icon: '⚙️',
    name: '设备停机分析',
    scene: '设备分析',
    desc: '分析非计划停机原因、设备运行率、停机时长排行，定位设备改进点',
    tags: ['设备', '停机', '效率'],
    example_question: '分析设备停机时间和不良率是否相关',
    metrics_count: 4,
    tables_count: 2,
  },
  {
    id: 'tpl_003',
    icon: '🏭',
    name: '工序良率监控',
    scene: '生产分析',
    desc: '追踪各工序良率趋势，自动预警良率下降的工序，并提供异常归因',
    tags: ['生产', '良率', '监控'],
    example_question: '请分析各工序的良率，找出良率下降的工序',
    metrics_count: 3,
    tables_count: 2,
  },
  {
    id: 'tpl_004',
    icon: '📦',
    name: '库存预警看板',
    scene: '库存分析',
    desc: '监控库存水位，自动预警低库存和高库存物料，生成补货建议',
    tags: ['库存', '预警', '补货'],
    example_question: '找出库存低于安全线的产品，生成补货清单',
    metrics_count: 3,
    tables_count: 2,
  },
]

const applyTemplate = (template: any) => {
  emit('navigate-ask', template.example_question)
}

</script>



<style scoped>

::-webkit-scrollbar { width: 4px; }

::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }

::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }

::-webkit-scrollbar-thumb:hover { background: #9ca3af; }

</style>
