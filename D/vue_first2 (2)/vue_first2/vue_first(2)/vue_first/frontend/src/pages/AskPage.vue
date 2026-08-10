<template>
  <div class="ask-workspace flex gap-4 h-[calc(100vh-220px)]">
    <!-- ====== 左侧：历史记录面板 ====== -->
    <div class="w-56 flex-shrink-0 border border-gray-200 rounded-lg overflow-hidden flex flex-col">
      <!-- 头部 -->
      <div class="bg-gray-50 px-3 py-2 border-b border-gray-200 flex items-center justify-between">
        <span class="text-xs font-medium text-gray-600">智能问数</span>
        <button
          @click="createNewChat"
          class="text-xs text-primary hover:text-primary-dark font-medium transition"
        >
          + 新建对话
        </button>
      </div>

      <!-- 搜索框 + 搜索按钮 -->
      <div class="px-2 py-1.5 border-b border-gray-100">
        <div class="flex gap-1">
          <input
            v-model="searchInput"
            type="text"
            placeholder="搜索历史记录..."
            class="flex-1 px-2 py-1 text-xs border border-gray-200 rounded outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            @keyup.enter="doSearch"
          />
          <button
            @click="doSearch"
            class="px-2 py-1 text-xs text-white bg-primary rounded hover:bg-primary/80 transition flex-shrink-0"
            title="搜索"
          >
            🔍
          </button>
          <button
            v-if="searchKeyword"
            @click="clearSearch"
            class="px-2 py-1 text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded transition flex-shrink-0"
            title="清空搜索"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- 历史列表 -->
      <div class="flex-1 overflow-y-auto py-1">
        <div v-if="filteredHistory.length === 0" class="px-3 py-4 text-center text-xs text-gray-400">
          {{ searchKeyword ? '未找到匹配记录' : '暂无历史对话' }}
        </div>
        <div
          v-for="item in filteredHistory"
          :key="item.id"
          @click="loadChat(item.id)"
          class="px-3 py-2 cursor-pointer transition hover:bg-gray-50 border-b border-gray-50"
          :class="currentChatId === item.id ? 'bg-primary/5 border-l-2 border-primary' : ''"
        >
          <div class="text-xs text-gray-700 truncate font-medium">{{ item.title || '新对话' }}</div>
          <div class="flex items-center justify-between mt-0.5">
            <span class="text-[10px] text-gray-400">{{ formatTime(item.createdAt) }}</span>
            <button
              @click.stop="deleteChat(item.id)"
              class="text-[10px] text-gray-300 hover:text-danger transition"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      <!-- 底部统计 -->
      <div class="border-t border-gray-100 px-3 py-1.5 text-[10px] text-gray-400">
        共 {{ history.length }} 条对话
        <span v-if="searchKeyword" class="ml-2">(筛选后 {{ filteredHistory.length }} 条)</span>
      </div>
    </div>

    <!-- ====== 右侧：聊天区域 ====== -->
    <div class="flex-1 min-w-0 border border-gray-200 rounded-lg overflow-hidden flex flex-col">
      <!-- 对话区域 -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4" ref="chatContainer">
        <div v-for="(msg, idx) in currentMessages" :key="idx"
             class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
          <div class="max-w-[85%]">
            <div class="text-xs text-gray-400 mb-1">{{ msg.role === 'user' ? '我' : 'AI 助手' }}</div>
            <div class="rounded-lg px-4 py-2.5 text-sm"
                 :class="msg.role === 'user' ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700'">
              {{ msg.content }}
            </div>
            <!-- 结果显示 -->
            <div v-if="msg.result" class="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="flex items-center gap-2 text-xs text-gray-400 mb-2">
                <span>📊 分析结果</span>
                <span class="text-success">● 已生成</span>
              </div>
              <div v-html="msg.result" class="text-sm text-gray-600"></div>
            </div>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="isLoading" class="flex justify-start">
          <div class="bg-gray-100 rounded-lg px-4 py-2.5 text-sm text-gray-500">
            <span class="inline-block animate-pulse">思考中...</span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="p-4 border-t border-gray-100 flex-shrink-0">
        <div class="flex gap-3">
          <input
            v-model="inputText"
            @keydown.enter="sendMessage"
            type="text"
            placeholder="请输入分析问题，如：分析各工序的良率"
            class="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50"
          />
          <button
            @click="sendMessage"
            :disabled="isLoading || !inputText.trim()"
            class="px-6 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            发送
          </button>
        </div>

        <!-- 快捷提问 -->
        <div class="flex gap-2 mt-3 flex-wrap">
          <button
            v-for="q in quickQuestions"
            :key="q"
            @click="inputText = q"
            class="text-xs px-3 py-1 bg-gray-100 text-gray-600 rounded-full hover:bg-gray-200 transition"
          >
            {{ q }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'

// ========== Props ==========
const props = defineProps<{
  initialQuestion?: string
}>()

const emit = defineEmits<{
  'question-consumed': []
}>()

// ========== 类型定义 ==========
interface Message {
  role: 'user' | 'assistant'
  content: string
  result?: string
}

interface ChatHistory {
  id: string
  title: string
  messages: Message[]
  createdAt: string
  updatedAt: string
}

// ========== 状态 ==========
const inputText = ref('')
const isLoading = ref(false)
const searchInput = ref('')      // 输入框的值
const searchKeyword = ref('')    // 实际搜索的关键词
const chatContainer = ref<HTMLElement | null>(null)

// 历史记录列表
const history = ref<ChatHistory[]>([])
const currentChatId = ref<string | null>(null)

// ========== 搜索方法 ==========
const doSearch = () => {
  searchKeyword.value = searchInput.value.trim()
}

const clearSearch = () => {
  searchInput.value = ''
  searchKeyword.value = ''
}

// ========== 计算属性 ==========

// 当前对话的消息
const currentMessages = computed(() => {
  if (!currentChatId.value) return []
  const chat = history.value.find(h => h.id === currentChatId.value)
  return chat?.messages || []
})

// 过滤后的历史记录
const filteredHistory = computed(() => {
  if (!searchKeyword.value) return history.value
  const keyword = searchKeyword.value.toLowerCase()
  return history.value.filter(item =>
    item.title?.toLowerCase().includes(keyword) ||
    item.messages.some(m => m.content.toLowerCase().includes(keyword))
  )
})

// ========== 快捷问题 ==========
const quickQuestions = [
  '分析各工序的良率',
  '最近一个月不良数量最高的产品',
  '分析设备停机时间和不良率是否相关',
  '统计每条产线最近7天的产量趋势'
]

// ========== 核心方法 ==========

// 生成唯一 ID
const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

// 格式化时间
const formatTime = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  if (diff < 604800000) return Math.floor(diff / 86400000) + '天前'

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 创建新对话
const createNewChat = () => {
  const newChat: ChatHistory = {
    id: generateId(),
    title: '新对话',
    messages: [
      { role: 'assistant', content: '你好！我是企业数据底座智能问析助手。请提出你想分析的问题，例如产量趋势、良率分析、设备停机等。' }
    ],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  }
  history.value.unshift(newChat)
  currentChatId.value = newChat.id
  saveToStorage()
}

// 加载对话
const loadChat = (id: string) => {
  currentChatId.value = id
  scrollToBottom()
}

// 删除对话
const deleteChat = (id: string) => {
  if (!confirm('确定要删除这条对话吗？')) return
  history.value = history.value.filter(h => h.id !== id)
  if (currentChatId.value === id) {
    currentChatId.value = history.value.length > 0 ? history.value[0].id : null
  }
  saveToStorage()
}

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

// ========== 渲染 Agent 结果 ==========

// HTML 转义，防止 XSS
const esc = (s: any): string => {
  if (s === null || s === undefined) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// 渲染数据表格
const renderTable = (columns: string[], rows: any[]): string => {
  if (!columns || !rows || rows.length === 0) return ''
  let html = '<div class="overflow-x-auto"><table class="min-w-full text-xs border-collapse">'
  html += '<thead><tr>'
  columns.forEach(c => { html += `<th class="border border-gray-300 bg-gray-100 px-2 py-1 text-left font-medium">${esc(c)}</th>` })
  html += '</tr></thead><tbody>'
  rows.slice(0, 20).forEach(r => {
    html += '<tr>'
    columns.forEach(c => { html += `<td class="border border-gray-200 px-2 py-1">${esc(r[c] ?? '')}</td>` })
    html += '</tr>'
  })
  if (rows.length > 20) {
    html += `<tr><td colspan="${columns.length}" class="border border-gray-200 px-2 py-1 text-center text-gray-400">... 共 ${rows.length} 行</td></tr>`
  }
  html += '</tbody></table></div>'
  return html
}

// 根据 agent 返回的 data 生成展示 HTML
const renderAgentResult = (data: any): string => {
  if (!data) return '<div class="text-sm text-gray-500">无返回结果</div>'
  const type = data.type || ''
  let html = ''

  // 闲聊 / 数据库分析：纯文本
  if (type === 'general_chat' || type === 'analyze_db') {
    html += `<div style="white-space:pre-wrap;line-height:2;font-size:13px">${esc(data.answer || '')}</div>`
    return html
  }

  // 表结构查询
  if (type === 'table_lookup') {
    const mt = data.matched_table
    if (mt) {
      html += `<div class="text-sm font-medium mb-1">${esc(mt.table_alias)}（${esc(mt.table_name)}）</div>`
      html += `<div class="text-xs text-gray-500 mb-2">${esc(mt.category)} · ${mt.row_count} 行 · ${mt.field_count} 字段</div>`
      if (data.detail && data.detail.fields) {
        html += renderTable(['字段', '类型', '键'], data.detail.fields.map((f: any) => ({ '字段': f.name, '类型': f.type, '键': f.key || '' })))
      }
    } else {
      html += '<div class="text-sm text-gray-500">未找到匹配的表</div>'
    }
    return html
  }

  // ML 建模结果
  if (type === 'ml_result' || type === 'ml_error') {
    if (data.ml_result && data.ml_result.success) {
      const mr = data.ml_result
      html += `<div class="text-sm mb-1"><b>${esc(mr.model?.label || mr.model?.name || '')}</b></div>`
      html += `<div class="text-xs text-gray-500 mb-2">样本 ${mr.samples} 条</div>`
      if (mr.metrics) {
        html += '<div class="text-xs mb-2">'
        Object.entries(mr.metrics).forEach(([k, v]) => { html += `<span class="mr-3">${esc(k)}: <b>${esc(v)}</b></span>` })
        html += '</div>'
      }
      if (mr.pred_samples && mr.pred_samples.length > 0) {
        html += '<div class="text-xs text-gray-400 mb-1">预测样本</div>'
        html += renderTable(Object.keys(mr.pred_samples[0]), mr.pred_samples.slice(0, 10))
      }
    } else {
      html += `<div class="text-sm text-red-500">${esc(data.error || data.ml_result?.error || 'ML 执行失败')}</div>`
    }
    return html
  }

  // data_query：SQL + 表格 + 图表 + 分析 + 推荐
  if (type === 'data_query') {
    if (data.sql) {
      html += '<div class="text-xs text-gray-400 mb-2">📌 生成的 SQL</div>'
      html += `<pre class="text-xs bg-gray-100 rounded p-2 mb-3 overflow-x-auto">${esc(data.sql)}</pre>`
    }

    const result = data.result || {}
    if (result.rows && result.rows.length > 0) {
      html += '<div class="text-xs text-gray-400 mb-1">📊 查询结果</div>'
      html += renderTable(result.columns || [], result.rows)
    }

    if (data.chart && data.chart.svg) {
      html += `<div class="mt-3">${data.chart.svg}</div>`
    }

    if (data.analysis) {
      html += `<div class="mt-3 text-sm text-gray-600" style="white-space:pre-wrap;line-height:1.8">${esc(data.analysis)}</div>`
    }

    if (data.recommended && data.recommended.length > 0) {
      html += '<div class="mt-3 text-xs text-gray-500">你可能还想问：</div>'
      html += '<div class="flex flex-wrap gap-2 mt-1">'
      data.recommended.forEach((q: string) => {
        const safeQ = esc(q).replace(/'/g, "\\'")
        html += `<span class="text-xs px-3 py-1 bg-blue-50 text-blue-600 rounded-full cursor-pointer hover:bg-blue-100 transition" onclick="window.__askSend('${safeQ}')">${esc(q)}</span>`
      })
      html += '</div>'
    }

    if (data.prediction && data.prediction.length > 0) {
      html += '<div class="mt-3 text-xs text-gray-400">📈 趋势预测</div>'
      html += renderTable(Object.keys(data.prediction[0]), data.prediction.slice(0, 10))
    }
    return html
  }

  // 兜底：尝试显示 answer 或原始 JSON
  if (data.answer) return `<div style="white-space:pre-wrap;line-height:2;font-size:13px">${esc(data.answer)}</div>`
  return `<pre class="text-xs overflow-x-auto">${esc(JSON.stringify(data, null, 2))}</pre>`
}

// 暴露给推荐问题点击的回调（用于快捷填充输入框）
declare global {
  interface Window {
    __askSend?: (q: string) => void
  }
}

// ========== 发送消息 ==========
const sendMessage = async () => {
  if (!inputText.value.trim() || isLoading.value) return
  const text = inputText.value.trim()

  // 如果没有当前对话，创建新对话
  if (!currentChatId.value) {
    createNewChat()
  }

  // 添加用户消息
  const chat = history.value.find(h => h.id === currentChatId.value)
  if (!chat) return

  chat.messages.push({ role: 'user', content: text })

  // 更新标题（取第一条用户消息作为标题）
  if (chat.title === '新对话') {
    chat.title = text.length > 20 ? text.slice(0, 20) + '...' : text
  }

  chat.updatedAt = new Date().toISOString()
  inputText.value = ''
  saveToStorage()
  await scrollToBottom()

  // 调用真实 Agent 接口
  isLoading.value = true
  try {
    // 组装对话历史（最近 6 条）
    const historyPayload = chat.messages
      .filter(m => m.content)
      .slice(-6)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

    const resp = await fetch('/api/agent/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: text, history: historyPayload })
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      throw new Error(err?.detail || `请求失败(${resp.status})`)
    }
    const data = await resp.json()

    const finalData = data.data || {}
    chat.messages.push({
      role: 'assistant',
      content: finalData.answer || (finalData.type === 'data_query' ? `已查询到 ${(finalData.result?.rows || []).length} 条数据` : '已收到您的请求'),
      result: renderAgentResult(finalData)
    })
    chat.updatedAt = new Date().toISOString()
    saveToStorage()
    await scrollToBottom()
  } catch (e: any) {
    chat.messages.push({
      role: 'assistant',
      content: '请求失败',
      result: `<div class="text-sm text-red-500">${esc(e.message || '未知错误')}</div>`
    })
    chat.updatedAt = new Date().toISOString()
    saveToStorage()
    await scrollToBottom()
  } finally {
    isLoading.value = false
  }
}

// 供推荐问题快捷填充
window.__askSend = (q: string) => {
  inputText.value = q
}

// ========== 存储 ==========
const STORAGE_KEY = 'ask_chat_history'

const saveToStorage = () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value))
  } catch (e) {
    console.warn('保存历史记录失败:', e)
  }
}

const loadFromStorage = () => {
  try {
    const data = localStorage.getItem(STORAGE_KEY)
    if (data) {
      const parsed = JSON.parse(data)
      if (Array.isArray(parsed) && parsed.length > 0) {
        history.value = parsed
        currentChatId.value = parsed[0].id
        return true
      }
    }
  } catch (e) {
    console.warn('加载历史记录失败:', e)
  }
  return false
}

// ========== 初始化 ==========
onMounted(() => {
  // 尝试从 localStorage 加载
  const hasHistory = loadFromStorage()

  // 如果没有历史记录，创建默认对话
  if (!hasHistory) {
    createNewChat()
  }

  scrollToBottom()
})

// 监听消息变化，滚动到底部
watch(currentMessages, () => {
  scrollToBottom()
}, { deep: true })

// 监听外部传入的初始问题（来自分析模板）
watch(() => props.initialQuestion, (question) => {
  if (question && question.trim()) {
    createNewChat()
    nextTick(() => {
      inputText.value = question
      emit('question-consumed')
    })
  }
})
</script>
