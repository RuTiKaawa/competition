<template>
  <div class="connection-console space-y-4">
    <div class="rounded-xl border border-blue-100 bg-blue-50/50 p-4 text-sm text-gray-600">
      支持切换不同的数据库软件（PostgreSQL / MySQL）和不同的数据库工作区。切换成功后，数据表、字段、行数、表关系和分析主题会从新数据库重新读取。
    </div>

    <!-- 数据库软件类型 + 连接配置 -->
    <div class="grid grid-cols-2 gap-4">
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">数据库软件类型</label>
        <select
          v-model="form.db_type"
          @change="onDbTypeChange"
          class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50 bg-white"
        >
          <option value="postgresql">PostgreSQL</option>
          <option value="mysql">MySQL</option>
        </select>
      </div>
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">主机地址</label>
        <input v-model="form.host" type="text" placeholder="localhost"
               class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50" />
      </div>
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">端口</label>
        <input v-model.number="form.port" type="number" placeholder="5432"
               class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50" />
      </div>
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">数据库名称</label>
        <input v-model="form.database" type="text" placeholder="enterprise_data"
               class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50" />
      </div>
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">用户名</label>
        <input v-model="form.user" type="text" placeholder="postgres"
               class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50" />
      </div>
      <div class="p-4 border border-gray-200 rounded-lg">
        <label class="text-xs text-gray-400 font-medium">密码</label>
        <input v-model="form.password" type="password" placeholder="请输入数据库密码"
               class="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary/50" />
      </div>
    </div>

    <div class="flex items-center gap-3">
      <button @click="testConnection" :disabled="loading" class="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition disabled:opacity-50">
        测试连接
      </button>
      <button @click="saveDbConfig" :disabled="loading" class="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition disabled:opacity-50">
        保存配置
      </button>
      <button @click="switchConnection" :disabled="loading" class="px-4 py-2 bg-primary text-white rounded-lg text-sm hover:opacity-90 transition disabled:opacity-50">
        {{ loading ? '处理中...' : '切换数据库' }}
      </button>
      <span v-if="message" class="text-sm" :class="success ? 'text-green-600' : 'text-red-600'">{{ message }}</span>
    </div>

    <!-- 数据库工作区管理 -->
    <div class="p-4 border border-gray-200 rounded-lg">
      <div class="text-xs font-medium text-gray-500 mb-3">数据库工作区</div>
      <div class="flex items-center gap-2 flex-wrap">
        <select v-model="activeDatabase" class="px-2 py-1.5 border border-gray-300 rounded text-sm max-w-52">
          <option v-for="db in databases" :key="db" :value="db">库：{{ db }}</option>
        </select>
        <button @click="switchWorkspace" :disabled="!activeDatabase || activeDatabase === activeName" class="px-3 py-1.5 bg-primary text-white rounded text-sm hover:opacity-90 disabled:opacity-40">
          切换工作区
        </button>
        <input v-model="newDatabaseName" placeholder="新建数据库名（可选）" class="px-2 py-1.5 border border-gray-300 rounded text-sm" />
        <button @click="createWorkspace" class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50">新建并切换</button>
        <select v-model="databaseToDelete" class="px-2 py-1.5 border border-gray-300 rounded text-sm max-w-52 ml-4">
          <option value="" disabled>删除非当前数据库…</option>
          <option v-for="db in databases.filter(name => name !== activeName)" :key="db" :value="db">{{ db }}</option>
        </select>
        <button @click="deleteWorkspace" :disabled="!databaseToDelete" class="px-2.5 py-1.5 rounded text-sm text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed">
          删除
        </button>
      </div>
      <div v-if="workspaceMessage" class="mt-3 text-sm" :class="workspaceSuccess ? 'text-green-600' : 'text-red-600'">
        {{ workspaceMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

const emit = defineEmits<{ (event: 'database-switched'): void }>()
const form = reactive({ db_type: 'postgresql', host: '', port: 5432, database: '', user: '', password: '' })
const loading = ref(false)
const success = ref(false)
const message = ref('')

// 数据库工作区
const databases = ref<string[]>([])
const activeName = ref('')
const activeDatabase = ref('')
const newDatabaseName = ref('')
const databaseToDelete = ref('')
const workspaceMessage = ref('')
const workspaceSuccess = ref(false)

const request = async (url: string, method: 'POST') => {
  loading.value = true
  message.value = ''
  try {
    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, name: form.database }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '操作失败')
    success.value = data.success !== false
    message.value = data.message
    return data.success !== false
  } catch (error: any) {
    success.value = false
    message.value = error.message || '操作失败'
    return false
  } finally {
    loading.value = false
  }
}

const testConnection = async () => {
  const res = await fetch('/api/config/db', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...form, name: form.database, test_connection: true }),
  })
  const data = await res.json()
  success.value = data.success
  message.value = data.message
}

const saveDbConfig = async () => {
  const res = await fetch('/api/config/db', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...form, name: form.database, test_connection: false }),
  })
  const data = await res.json()
  success.value = data.success
  message.value = data.message
  if (data.success) {
    await loadWorkspaces()
    emit('database-switched')
  }
}

const switchConnection = async () => {
  if (await request('/api/database/switch', 'POST')) {
    emit('database-switched')
    await loadWorkspaces()
  }
}

const onDbTypeChange = () => {
  if (form.db_type === 'mysql' && form.port === 5432) {
    form.port = 3306
  } else if (form.db_type === 'postgresql' && form.port === 3306) {
    form.port = 5432
  }
}

// ===== 工作区管理 =====
const loadWorkspaces = async () => {
  try {
    const res = await fetch('/api/config/databases')
    const data = await res.json()
    databases.value = data.databases || []
    activeName.value = data.active || ''
    activeDatabase.value = activeName.value
    if (!databases.value.includes(databaseToDelete.value) || databaseToDelete.value === activeName.value) {
      databaseToDelete.value = ''
    }
  } catch (e) {
    console.error('加载数据库工作区失败', e)
  }
}

const switchWorkspace = async () => {
  if (!activeDatabase.value || activeDatabase.value === activeName.value) return
  try {
    const res = await fetch(`/api/config/databases/${encodeURIComponent(activeDatabase.value)}/activate`, { method: 'POST' })
    const data = await res.json()
    workspaceSuccess.value = data.success
    workspaceMessage.value = data.message
    if (data.success) {
      databases.value = data.profiles || databases.value
      activeName.value = data.active || activeName.value
      activeDatabase.value = activeName.value
      emit('database-switched')
    }
  } catch (error: any) {
    workspaceSuccess.value = false
    workspaceMessage.value = error.message || '切换失败'
  }
}

const createWorkspace = async () => {
  const name = newDatabaseName.value.trim()
  if (!name) return
  try {
    const res = await fetch(`/api/config/databases/${encodeURIComponent(name)}/activate`, { method: 'POST' })
    const data = await res.json()
    workspaceSuccess.value = data.success
    workspaceMessage.value = data.message
    if (data.success) {
      newDatabaseName.value = ''
      databases.value = data.profiles || databases.value
      activeName.value = data.active || activeName.value
      activeDatabase.value = activeName.value
      emit('database-switched')
    }
  } catch (error: any) {
    workspaceSuccess.value = false
    workspaceMessage.value = error.message || '新建失败'
  }
}

const deleteWorkspace = async () => {
  if (!databaseToDelete.value) return
  if (!window.confirm(`确认永久删除数据库"${databaseToDelete.value}"及其中全部数据表吗？此操作不可恢复。`)) return
  try {
    const res = await fetch(`/api/config/databases/${encodeURIComponent(databaseToDelete.value)}`, { method: 'DELETE' })
    const data = await res.json()
    workspaceSuccess.value = data.success
    workspaceMessage.value = data.message
    if (data.success) {
      databases.value = data.profiles || databases.value
      databaseToDelete.value = ''
    }
  } catch (error: any) {
    workspaceSuccess.value = false
    workspaceMessage.value = error.message || '删除失败'
  }
}

onMounted(async () => {
  const response = await fetch('/api/config/db')
  if (response.ok) {
    const data = await response.json()
    Object.assign(form, {
      db_type: data.db_type || 'postgresql',
      host: data.host,
      port: data.port,
      database: data.name,
      user: data.user,
      password: data.password || '',
    })
  }
  await loadWorkspaces()
})
</script>
