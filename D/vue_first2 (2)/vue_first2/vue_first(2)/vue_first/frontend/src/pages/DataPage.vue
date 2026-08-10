<template>
  <div class="data-browser space-y-3">
    <!-- ====== 数据库切换器 ====== -->
    <div class="flex items-center justify-between border border-gray-200 rounded-lg px-3 py-2 bg-gray-50/70">
      <div class="flex items-center gap-2 text-sm text-gray-600">
        <span class="text-xs font-medium text-gray-500">当前数据库：</span>
        <select v-model="activeDatabase" @change="switchDatabase" class="px-2 py-1.5 border border-gray-300 rounded text-sm max-w-48">
          <option v-for="db in databases" :key="db" :value="db">{{ db }}</option>
        </select>
        <span class="text-xs text-gray-400" v-if="activeDatabase">（切换后自动刷新表数据）</span>
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <span>删除数据库：</span>
        <select v-model="databaseToDelete" class="px-2 py-1.5 border border-gray-300 rounded text-sm">
          <option value="" disabled>请选择非当前数据库</option>
          <option v-for="db in databases.filter(name => name !== activeDatabase)" :key="db" :value="db">{{ db }}</option>
        </select>
        <button @click="deleteDatabase" :disabled="!databaseToDelete" class="px-2.5 py-1.5 rounded text-sm text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed">删除</button>
      </div>
    </div>

    <!-- ====== 数据源导入 ====== -->
    <div class="border border-gray-200 rounded-lg p-3 bg-gray-50/70">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 class="text-sm font-semibold text-gray-700">数据源导入</h3>
          <p class="text-xs text-gray-400 mt-0.5">上传 CSV、SQLite/DB、ZIP 压缩包，或通过远程地址导入；主键会自动识别。</p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <select v-model="importMode" class="px-2 py-1.5 border border-gray-300 rounded text-sm">
            <option value="file">上传文件</option>
            <option value="url">远程地址</option>
          </select>
          <input v-if="importMode === 'file'" ref="csvFileInput" type="file" class="text-sm text-gray-500" accept=".csv,.sqlite,.sqlite3,.db,.zip" multiple />
          <input v-else v-model="importUrl" placeholder="https://.../database.sqlite" class="px-2 py-1.5 border border-gray-300 rounded text-sm min-w-[280px]" />
          <input v-model="importTableName" placeholder="表名（可选）" class="px-2 py-1.5 border border-gray-300 rounded text-sm" />
          <button @click="handleImportCsv" :disabled="importing" class="px-3 py-1.5 bg-primary text-white rounded text-sm hover:opacity-90 disabled:opacity-50">
            {{ importing ? '导入中...' : '导入' }}
          </button>
        </div>
      </div>
      <div v-if="importMessage" class="mt-3 text-sm" :class="importMessageType === 'success' ? 'text-success' : 'text-red-600'">
        {{ importMessage }}
      </div>
    </div>

    <div class="flex gap-4 h-[calc(100vh-220px)]">
    <!-- ====== 左侧表列表 ====== -->
    <div class="w-56 flex-shrink-0 border border-gray-200 rounded-lg overflow-hidden flex flex-col">
      <div class="bg-gray-50 px-3 py-2 border-b border-gray-200 flex items-center justify-between">
        <span class="text-sm font-medium text-gray-600">数据表</span>
        <span class="text-sm text-gray-400">{{ filteredTableTabs.length }}</span>
      </div>
      <!-- 表搜索框 -->
      <div class="px-2 py-1.5 border-b border-gray-100">
        <input
          v-model="tableFilterKeyword"
          type="text"
          placeholder="搜索表名..."
          class="w-full px-2 py-1 text-xs border border-gray-300 rounded outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        />
      </div>
      <div class="overflow-y-auto flex-1">
        <div
          v-for="name in filteredTableTabs"
          :key="name"
          @click="activeTab = name"
          class="px-3 py-2 text-sm cursor-pointer transition flex items-center justify-between border-b border-gray-50 hover:bg-gray-50"
          :class="activeTab === name ? 'bg-primary/10 text-primary border-l-2 border-primary' : 'text-gray-600'"
        >
          <span class="font-mono text-sm truncate">{{ name }}</span>
          <span v-if="getTableData(name)?.row_count !== undefined" class="text-[10px] text-gray-400 flex-shrink-0 ml-2">
            {{ getTableData(name)?.row_count }}行
          </span>
        </div>
        <div v-if="loading" class="px-3 py-4 text-center text-sm text-gray-400">加载中...</div>
        <div v-if="!loading && filteredTableTabs.length === 0" class="px-3 py-4 text-center text-sm text-gray-400">
          {{ tableFilterKeyword ? '未找到匹配的表' : '暂无数据表' }}
        </div>
      </div>
    </div>

    <!-- ====== 右侧详情 ====== -->
    <div class="flex-1 min-w-0 border border-gray-200 rounded-lg overflow-hidden flex flex-col">
      <!-- 表头信息 -->
      <div v-if="currentTableData" class="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
        <div class="flex items-center gap-3">
          <span class="font-mono text-sm font-semibold text-gray-700">{{ currentTableData.table_name }}</span>
          <span class="text-sm text-gray-400">共 {{ currentTableData.columns?.length || 0 }} 个字段</span>
        </div>
        <div class="flex items-center gap-3 text-sm text-gray-400">
          <span>{{ currentTableData.row_count ?? 0 }} 行</span>
        </div>
      </div>

      <!-- 内容区 -->
      <div v-if="currentTableData" class="flex-1 flex flex-col overflow-hidden">
        <!-- Tab 切换栏 -->
        <div class="flex items-center justify-between px-4 py-2 border-b border-gray-200 flex-shrink-0 bg-gray-50/80">
          <div class="flex gap-1 p-0.5 bg-gray-100 rounded-lg">
            <button
              @click="activeTabView = 'fields'"
              class="px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
              :class="activeTabView === 'fields' 
                ? 'bg-white text-primary shadow-sm' 
                : 'text-gray-500 hover:text-gray-700'"
            >
              📋 字段
            </button>
            <button
              @click="activeTabView = 'sample'"
              class="px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
              :class="activeTabView === 'sample' 
                ? 'bg-white text-primary shadow-sm' 
                : 'text-gray-500 hover:text-gray-700'"
            >
              📊 样例数据
            </button>
            <button
              @click="activeTabView = 'relationships'"
              class="px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
              :class="activeTabView === 'relationships' 
                ? 'bg-white text-primary shadow-sm' 
                : 'text-gray-500 hover:text-gray-700'"
            >
              🔗 表关系
            </button>
          </div>
          <!-- 搜索（只在字段 Tab 显示） -->
          <div v-if="activeTabView === 'fields'" class="flex items-center gap-2">
            <input
              v-model="filterKeyword"
              type="text"
              placeholder="搜索字段名或备注..."
              class="px-2 py-1 text-xs border border-gray-300 rounded outline-none focus:border-primary focus:ring-1 focus:ring-primary w-48"
            />
            <button
              v-if="filterKeyword"
              @click="filterKeyword = ''"
              class="text-xs text-gray-400 hover:text-gray-600"
            >
              ✕
            </button>
          </div>
          <!-- 关系数量提示 -->
          <div v-else-if="activeTabView === 'relationships'" class="text-xs text-gray-400">
            共 {{ relationships.length }} 条关系
          </div>
        </div>

        <!-- ====== 字段列表 Tab ====== -->
        <div v-if="activeTabView === 'fields'" class="flex-1 overflow-y-auto px-4 py-2">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 sticky top-0 z-10">
              <tr>
                <th class="px-3 py-1.5 text-left font-medium text-gray-500 text-base">字段名</th>
                <th class="px-3 py-1.5 text-left font-medium text-gray-500 text-base">类型</th>
                <th class="px-3 py-1.5 text-left font-medium text-gray-500 text-base">可空</th>
                <th class="px-3 py-1.5 text-left font-medium text-gray-500 text-base">主键</th>
                <th class="px-3 py-1.5 text-left font-medium text-gray-500 text-base">备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="col in filteredColumns" :key="col.name" class="border-t border-gray-100 hover:bg-gray-50/50 transition">
                <td class="px-3 py-1.5 font-mono text-primary text-sm">{{ col.name }}</td>
                <td class="px-3 py-1.5 text-gray-500 text-sm">{{ col.type }}</td>
                <td class="px-3 py-1.5 text-gray-400 text-sm">{{ col.nullable ? '✅' : '❌' }}</td>
                <td class="px-3 py-1.5 text-gray-400 text-sm">{{ col.primary_key ? '✅' : '' }}</td>
                <!-- 可编辑备注 -->
                <td class="px-3 py-1 text-sm">
                  <div
                    v-if="editingColumn !== col.name"
                    @click="startEdit(col)"
                    class="cursor-pointer text-gray-400 hover:text-primary hover:bg-gray-100 px-2 py-0.5 rounded min-h-[24px] transition group flex items-center"
                  >
                    <span class="truncate max-w-[120px]">{{ col.comment  }}</span>
                    <span class="ml-1 opacity-0 group-hover:opacity-100 text-[10px] text-gray-300">✏️</span>
                  </div>
                  <div v-else class="flex items-center gap-1">
                    <input
                      ref="commentInput"
                      v-model="editValue"
                      @blur="saveComment(col)"
                      @keyup.enter="saveComment(col)"
                      @keyup.esc="cancelEdit"
                      class="flex-1 px-2 py-0.5 text-sm border border-primary rounded outline-none min-w-[100px]"
                      placeholder="输入备注..."
                      maxlength="255"
                    />
                    <button @click="saveComment(col)" class="text-primary hover:text-primary-dark text-xs" title="保存">💾</button>
                    <button @click="cancelEdit" class="text-gray-400 hover:text-gray-600 text-xs" title="取消">✕</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- ====== 样例数据 Tab ====== -->
        <div v-if="activeTabView === 'sample'" class="flex-1 overflow-y-auto px-4 py-2">
          <div v-if="currentTableData.sample_data?.length" class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-gray-400 bg-gray-50 sticky top-0 z-10">
                  <th
                    v-for="key in Object.keys(currentTableData.sample_data[0])"
                    :key="key"
                    class="px-2 py-1.5 font-mono font-normal text-sm"
                  >
                    {{ key }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, rowIdx) in currentTableData.sample_data"
                  :key="rowIdx"
                  class="border-t border-gray-50 hover:bg-gray-50/50 transition"
                >
                  <td
                    v-for="(val, key) in row"
                    :key="key"
                    class="px-2 py-1 text-gray-600 font-mono text-sm max-w-[150px] truncate relative"
                    :title="String(val)"
                    @dblclick="startEditSample(row, key, rowIdx, val)"
                  >
                    <!-- 编辑状态 -->
                    <div v-if="editingSample.rowIdx === rowIdx && editingSample.cellKey === key" class="flex items-center gap-1">
                      <input
                        ref="sampleInputRef"
                        v-model="editingSample.value"
                        @blur="saveSampleEdit(row, key)"
                        @keyup.enter="saveSampleEdit(row, key)"
                        @keyup.esc="cancelSampleEdit"
                        class="w-full px-1 py-0.5 text-sm font-mono border border-primary rounded outline-none"
                        :class="editingSample.loading ? 'opacity-50' : ''"
                        :disabled="editingSample.loading"
                      />
                      <span v-if="editingSample.loading" class="text-[10px] text-gray-400 animate-pulse">⏳</span>
                    </div>
                    <!-- 显示状态 -->
                    <div v-else class="cursor-text hover:bg-primary/5 rounded px-1 py-0.5 transition min-h-[24px]">
                      {{ val !== null && val !== undefined ? val : 'null' }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="flex items-center justify-between text-xs text-gray-400 mt-2">
              <span>共 {{ currentTableData.sample_data.length }} 条样例数据</span>
              <span class="text-[10px] text-gray-300">💡 双击单元格可编辑</span>
            </div>
          </div>
          <div v-else class="flex items-center justify-center h-32 text-gray-400 text-sm">
            暂无样例数据
          </div>
        </div>

        <!-- ====== 表关系 Tab ====== -->
        <div v-if="activeTabView === 'relationships'" class="flex-1 overflow-y-auto px-4 py-2">
          <div v-if="relationshipsLoading" class="flex items-center justify-center h-32 text-gray-400 text-sm">
            加载中...
          </div>
          <div v-else-if="relationships.length === 0" class="flex items-center justify-center h-32 text-gray-400 text-sm">
            暂无表间关系数据
          </div>
          <div v-else class="space-y-3">
            <!-- 按源表分组显示 -->
            <div
              v-for="(group, sourceTable) in groupedRelationships"
              :key="sourceTable"
              class="border border-gray-200 rounded-lg overflow-hidden"
            >
              <!-- 源表名 -->
              <div class="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2">
                <span class="font-mono text-sm font-semibold text-gray-700">{{ sourceTable }}</span>
                <span class="text-xs text-gray-400">{{ group.length }} 条关系</span>
              </div>
              <!-- 关系列表 -->
              <div class="divide-y divide-gray-100">
                <div
                  v-for="(rel, idx) in group"
                  :key="idx"
                  class="px-4 py-2.5 flex items-center gap-3 hover:bg-gray-50/50 transition"
                >
                  <!-- 源字段 -->
                  <span class="font-mono text-sm text-primary">{{ rel.source_column }}</span>
                  <!-- 箭头 -->
                  <div class="flex items-center gap-1 text-gray-300">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </div>
                  <!-- 目标表 -->
                  <span class="font-mono text-sm text-gray-700">{{ rel.target_table }}</span>
                  <span class="text-gray-400 text-xs">.</span>
                  <span class="font-mono text-sm text-gray-500">{{ rel.target_column }}</span>
                  <!-- 关系类型标签 -->
                  <span
                    class="ml-auto text-[10px] px-2 py-0.5 rounded-full"
                    :class="rel.type === 'foreign_key' ? 'bg-blue-100 text-blue-600' : 'bg-purple-100 text-purple-600'"
                  >
                    {{ rel.type === 'foreign_key' ? '外键' : '业务关联' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <!-- 图例 -->
          <div class="mt-4 flex items-center gap-4 text-xs text-gray-400 border-t border-gray-100 pt-3">
            <span>💡 表间关系说明：</span>
            <span><span class="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1"></span> 外键约束</span>
            <span><span class="inline-block w-2 h-2 rounded-full bg-purple-500 mr-1"></span> 业务关联</span>
            <span class="ml-auto text-[10px]">关系总数：{{ relationships.length }}</span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else-if="loading" class="flex-1 flex items-center justify-center text-gray-400 text-sm">
        加载中...
      </div>
      <div v-else class="flex-1 flex items-center justify-center text-gray-400 text-sm">
        请从左侧选择一张表
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'

// ========== 类型定义 ==========
interface Column {
  name: string
  type: string
  nullable: boolean
  comment: string
  primary_key: boolean
}

interface TableDetail {
  table_name: string
  columns: Column[]
  sample_data: Record<string, any>[]
  row_count: number
}

// ========== 状态 ==========
const loading = ref(false)
const allTables = ref<TableDetail[]>([])
const activeTab = ref('')
const activeTabView = ref<'fields' | 'sample' | 'relationships'>('fields')

// ========== 备注编辑相关 ==========
const editingColumn = ref<string | null>(null)
const editValue = ref('')
const commentInput = ref<HTMLInputElement | null>(null)

// ========== 样例数据编辑相关 ==========
const editingSample = ref({
  rowIdx: -1,
  cellKey: '',
  value: '',
  loading: false
})
const sampleInputRef = ref<HTMLInputElement | null>(null)

// ========== 搜索相关 ==========
const filterKeyword = ref('')
const tableFilterKeyword = ref('')

// ========== 表关系相关 ==========
const relationships = ref<any[]>([])
const relationshipsLoading = ref(false)

// ========== 计算属性 ==========
const tableTabs = computed(() => allTables.value.map(t => t.table_name))

const filteredTableTabs = computed(() => {
  if (!tableFilterKeyword.value.trim()) {
    return tableTabs.value
  }
  const keyword = tableFilterKeyword.value.trim().toLowerCase()
  return tableTabs.value.filter(name =>
    name.toLowerCase().includes(keyword)
  )
})

const currentTableData = computed(() => {
  return allTables.value.find(t => t.table_name === activeTab.value)
})

const getTableData = (name: string) => {
  return allTables.value.find(t => t.table_name === name)
}

const filteredColumns = computed(() => {
  const columns = currentTableData.value?.columns || []
  if (!filterKeyword.value.trim()) {
    return columns
  }
  const keyword = filterKeyword.value.trim().toLowerCase()
  return columns.filter(col =>
    col.name.toLowerCase().includes(keyword) ||
    (col.comment && col.comment.toLowerCase().includes(keyword))
  )
})

// 按源表分组
const groupedRelationships = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const rel of relationships.value) {
    if (!groups[rel.source_table]) {
      groups[rel.source_table] = []
    }
    groups[rel.source_table].push(rel)
  }
  return groups
})

// ========== 获取主键 ==========
const getPrimaryKey = (tableName: string): string => {
  const table = allTables.value.find(t => t.table_name === tableName)
  if (!table) return 'id'
  const pkCol = table.columns.find(col => col.primary_key === true)
  return pkCol?.name || 'id'
}

// ========== 备注编辑方法 ==========
const startEdit = (col: Column) => {
  editingColumn.value = col.name
  editValue.value = col.comment || ''
  nextTick(() => {
    commentInput.value?.focus()
    commentInput.value?.select()
  })
}

const cancelEdit = () => {
  editingColumn.value = null
  editValue.value = ''
}

const saveComment = async (col: Column) => {
  const newComment = editValue.value.trim()
  editingColumn.value = null
  editValue.value = ''

  if (newComment === (col.comment || '')) return

  const tableName = activeTab.value
  if (!tableName) return

  const oldComment = col.comment

  try {
    const targetTable = allTables.value.find(t => t.table_name === tableName)
    const targetCol = targetTable?.columns.find(c => c.name === col.name)
    if (targetCol) {
      targetCol.comment = newComment
    }

    const res = await fetch(`/api/tables/tables/${tableName}/columns/${col.name}/comment`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: newComment })
    })

    if (!res.ok) {
      if (targetCol) {
        targetCol.comment = oldComment
      }
      const err = await res.json()
      console.error('保存备注失败:', err)
      alert('保存失败: ' + (err.detail || '未知错误'))
    }
  } catch (error) {
    console.error('保存备注失败:', error)
    const targetTable = allTables.value.find(t => t.table_name === tableName)
    const targetCol = targetTable?.columns.find(c => c.name === col.name)
    if (targetCol) {
      targetCol.comment = oldComment
    }
    alert('保存失败，请检查网络连接')
  }
}

// ========== 样例数据编辑方法 ==========
const startEditSample = (_row: Record<string, any>, key: string, rowIdx: number, val: any) => {
  if (editingSample.value.loading) return

  editingSample.value.rowIdx = rowIdx
  editingSample.value.cellKey = key
  editingSample.value.value = val !== null && val !== undefined ? String(val) : ''

  nextTick(() => {
    sampleInputRef.value?.focus()
    sampleInputRef.value?.select()
  })
}

const cancelSampleEdit = () => {
  editingSample.value.rowIdx = -1
  editingSample.value.cellKey = ''
  editingSample.value.value = ''
  editingSample.value.loading = false
}

const saveSampleEdit = async (row: Record<string, any>, key: string) => {
  const newValue = editingSample.value.value.trim()
  const oldValue = row[key]

  if (String(newValue) === String(oldValue !== null && oldValue !== undefined ? oldValue : '')) {
    cancelSampleEdit()
    return
  }

  const tableName = activeTab.value
  if (!tableName) {
    cancelSampleEdit()
    return
  }

  const pkColumn = getPrimaryKey(tableName)
  const pkValue = row[pkColumn]

  if (!pkValue) {
    alert('无法找到主键，请检查数据表结构')
    cancelSampleEdit()
    return
  }

  editingSample.value.loading = true

  try {
    const res = await fetch('/api/tables/data/update', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        table_name: tableName,
        column_name: key,
        row_id: String(pkValue),
        id_column: pkColumn,
        new_value: newValue === '' ? null : newValue
      })
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || '更新失败')
    }

    // 更新本地数据
    const targetTable = allTables.value.find(t => t.table_name === tableName)
    if (targetTable) {
      const targetRow = targetTable.sample_data.find(
        (r: any) => String(r[pkColumn]) === String(pkValue)
      )
      if (targetRow) {
        const originalCol = targetTable.columns.find(col => col.name === key)
        if (originalCol) {
          const colType = originalCol.type.toUpperCase()
          if (colType.includes('INT') || colType.includes('NUMERIC') || colType.includes('DECIMAL')) {
            targetRow[key] = newValue === '' ? null : Number(newValue)
          } else if (colType.includes('BOOL')) {
            targetRow[key] = newValue === '' ? null : newValue.toLowerCase() === 'true'
          } else {
            targetRow[key] = newValue === '' ? null : newValue
          }
        } else {
          targetRow[key] = newValue === '' ? null : newValue
        }
      }
    }

    cancelSampleEdit()

  } catch (error: any) {
    console.error('更新失败:', error)
    alert('更新失败: ' + (error.message || '未知错误'))
    editingSample.value.loading = false
  }
}

// ========== 加载表关系 ==========
const loadRelationships = async () => {
  relationshipsLoading.value = true
  try {
    const res = await fetch('/api/tables/relationships')
    const data = await res.json()
    relationships.value = data.relationships || []
  } catch (error) {
    console.error('加载表关系失败:', error)
  } finally {
    relationshipsLoading.value = false
  }
}

// ========== 加载数据 ==========
// 数据库工作区切换
const databases = ref<string[]>([])
const activeDatabase = ref('')
const databaseToDelete = ref('')

// 数据源导入
const csvFileInput = ref<HTMLInputElement | null>(null)
const importTableName = ref('')
const importMode = ref<'file' | 'url'>('file')
const importUrl = ref('')
const importing = ref(false)
const importMessage = ref('')
const importMessageType = ref<'success' | 'error'>('success')

const formatImportError = (error: unknown): string => {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  if (Array.isArray(error)) {
    return error.map(item => {
      if (item && typeof item === 'object' && 'msg' in item) {
        const detail = item as { loc?: unknown[]; msg: string }
        return `${detail.loc?.slice(1).join(' / ') || '请求'}：${detail.msg}`
      }
      return formatImportError(item)
    }).join('；')
  }
  if (error && typeof error === 'object') {
    const detail = error as { detail?: unknown; message?: unknown }
    if (detail.detail !== undefined) return formatImportError(detail.detail)
    if (typeof detail.message === 'string') return detail.message
  }
  return '导入失败，请检查文件格式或后端服务日志'
}

const parseImportResponse = async (res: Response) => {
  const payload = await res.json().catch(() => ({}))
  if (!res.ok) throw payload.detail ?? payload
  if (payload.success === false) throw payload.message ?? payload
  return payload
}

const handleImportCsv = async () => {
  if (importing.value) return

  if (importMode.value === 'url') {
    if (!importUrl.value.trim()) {
      importMessage.value = '请输入远程数据源地址'
      importMessageType.value = 'error'
      return
    }
    importing.value = true
    importMessage.value = ''
    try {
      const form = new FormData()
      form.append('source_type', 'url')
      form.append('source_url', importUrl.value.trim())
      form.append('table_name', importTableName.value.trim())
      const res = await fetch('/api/tables/import-csv', { method: 'POST', body: form })
      const data = await parseImportResponse(res)
      const tables = data.mode === 'folder' || data.mode === 'sqlite'
        ? (data.files || data.tables || []).map((t: any) => t.table_name).join('、')
        : data.table_name
      importMessage.value = `导入成功：${tables}（共 ${data.row_count ?? data.tables?.length ?? 0} 行）`
      importMessageType.value = 'success'
      importUrl.value = ''
      importTableName.value = ''
      await loadTables()
    } catch (error) {
      importMessage.value = formatImportError(error)
      importMessageType.value = 'error'
    } finally {
      importing.value = false
    }
    return
  }

  // 文件模式
  const files = csvFileInput.value?.files
  if (!files || files.length === 0) {
    importMessage.value = '请先选择要导入的文件'
    importMessageType.value = 'error'
    return
  }

  importing.value = true
  importMessage.value = ''
  try {
    const form = new FormData()
    for (const file of Array.from(files)) {
      form.append('files', file)
    }
    form.append('table_name', importTableName.value.trim())
    form.append('source_type', 'file')
    const res = await fetch('/api/tables/import-csv', { method: 'POST', body: form })
    const data = await parseImportResponse(res)
    const tables = data.mode === 'folder' || data.mode === 'sqlite'
      ? (data.files || data.tables || []).map((t: any) => t.table_name).join('、')
      : data.table_name
    importMessage.value = `导入成功：${tables}（共 ${data.row_count ?? data.tables?.length ?? 0} 行）`
    importMessageType.value = 'success'
    importTableName.value = ''
    if (csvFileInput.value) csvFileInput.value.value = ''
    await loadTables()
  } catch (error) {
    importMessage.value = formatImportError(error)
    importMessageType.value = 'error'
  } finally {
    importing.value = false
  }
}

const loadDatabases = async () => {
  try {
    const res = await fetch('/api/config/databases')
    const data = await res.json()
    databases.value = data.databases || []
    activeDatabase.value = data.active || ''
  } catch (error) {
    console.error('加载数据库列表失败:', error)
  }
}

const switchDatabase = async () => {
  if (!activeDatabase.value) return
  try {
    const res = await fetch(`/api/config/databases/${encodeURIComponent(activeDatabase.value)}/activate`, { method: 'POST' })
    const data = await res.json()
    if (data.success) {
      databases.value = data.profiles || databases.value
      activeDatabase.value = data.active || activeDatabase.value
      relationships.value = []
      await loadTables()
    } else {
      alert(data.message || '切换失败')
      await loadDatabases()
    }
  } catch (error) {
    console.error('切换数据库失败:', error)
    alert('切换数据库失败，请检查后端服务')
  }
}

const deleteDatabase = async () => {
  if (!databaseToDelete.value) return
  if (!window.confirm(`确认永久删除数据库"${databaseToDelete.value}"及其中全部数据表吗？此操作不可恢复。`)) return
  try {
    const res = await fetch(`/api/config/databases/${encodeURIComponent(databaseToDelete.value)}`, { method: 'DELETE' })
    const data = await res.json()
    if (data.success) {
      databases.value = data.profiles || databases.value
      databaseToDelete.value = ''
    } else {
      alert(data.message || '删除失败')
    }
  } catch (error) {
    console.error('删除数据库失败:', error)
    alert('删除数据库失败，请检查后端服务')
  }
}

const loadTables = async () => {
  loading.value = true
  try {
    const res = await fetch('/api/tables/')
    const data = await res.json()
    allTables.value = data.tables || []
    if (allTables.value.length > 0) {
      activeTab.value = allTables.value[0].table_name
    }
  } catch (error) {
    console.error('加载表结构失败:', error)
  } finally {
    loading.value = false
  }
}

const loadTableDetail = async (tableName: string) => {
  if (allTables.value.find(t => t.table_name === tableName)?.sample_data) return

  try {
    const res = await fetch(`/api/tables/${tableName}`)
    const data = await res.json()
    const index = allTables.value.findIndex(t => t.table_name === tableName)
    if (index !== -1) {
      const oldRowCount = allTables.value[index].row_count ?? 0
      allTables.value[index] = {
        ...data,
        row_count: oldRowCount
      }
    } else {
      allTables.value.push(data)
    }
  } catch (error) {
    console.error('加载表详情失败:', error)
  }
}

// ========== 监听 ==========
watch(activeTab, (newTab) => {
  if (newTab) {
    loadTableDetail(newTab)
  }
})

watch(activeTab, () => {
  activeTabView.value = 'fields'
})

watch(activeTabView, (newTab) => {
  if (newTab === 'relationships' && relationships.value.length === 0) {
    loadRelationships()
  }
})

onMounted(() => {
  loadDatabases()
  loadTables()
})
</script>
