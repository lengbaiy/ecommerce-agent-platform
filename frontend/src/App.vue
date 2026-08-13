<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CChart } from "@coreui/vue-chartjs";

import { useOperationsWorkspace } from "./composables/useOperationsWorkspace";
import { navigationItems } from "./config/navigation";
import ModuleWorkspace from "./modules/ModuleWorkspace.vue";
import { logout } from "./auth/api";
import LoginPage from "./auth/LoginPage.vue";
import PermissionWorkspace from "./auth/PermissionWorkspace.vue";
import { currentSession, hasPermission, setSession } from "./auth/session";

const activeModuleId = ref("dashboard");
const selectedShopId = ref("amazon-us-demo");
const sidebarVisible = ref(true);
const currentModule = computed(
  () => navigationItems.find((item) => item.id === activeModuleId.value) ?? navigationItems[0],
);
const isDashboard = computed(() => activeModuleId.value === "dashboard");
const isPermissions = computed(() => activeModuleId.value === "permissions");
const visibleNavigationItems = computed(() =>
  navigationItems.filter((item) => item.id !== "permissions" || hasPermission("user:read")),
);
const {
  overview,
  tasks,
  pendingTasks,
  loading,
  creating,
  errorMessage,
  dataCutoff,
  loadWorkspace,
  createTask,
} = useOperationsWorkspace();

watch(selectedShopId, (shopId) => {
  if (currentSession.value) void loadWorkspace(shopId);
});
watch(
  currentSession,
  (session) => {
    if (session) void loadWorkspace(selectedShopId.value);
  },
  { immediate: true },
);

const statusLabels: Record<string, string> = {
  PENDING: "待处理",
  PLANNING: "规划中",
  RUNNING: "运行中",
  WAITING_APPROVAL: "待审批",
  RETRYING: "重试中",
  COMPLETED: "已完成",
  DEGRADED: "降级完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};

const intentLabels: Record<string, string> = {
  market_entry: "市场机会",
  product_strategy: "商品策略",
  listing_generation: "Listing",
  operations_diagnosis: "经营诊断",
};

const navIcons: Record<string, string> = {
  dashboard: "cil-speedometer",
  tasks: "cil-task",
  market: "cil-globe-alt",
  strategy: "cil-lightbulb",
  listing: "cil-notes",
  diagnosis: "cil-chart-pie",
  knowledge: "cil-layers",
  evaluation: "cil-check-circle",
  permissions: "cil-lock-locked",
};

const salesChartData = {
  labels: ["8月5日", "8月6日", "8月7日", "8月8日", "8月9日", "8月10日", "今天"],
  datasets: [
    {
      label: "GMV",
      backgroundColor: "rgba(50, 31, 219, 0.08)",
      borderColor: "#321fdb",
      pointBackgroundColor: "#fff",
      pointBorderColor: "#321fdb",
      data: [82, 94, 91, 108, 116, 121, 129],
      fill: true,
      tension: 0.35,
    },
    {
      label: "目标",
      borderColor: "#9da5b1",
      borderDash: [6, 5],
      pointRadius: 0,
      data: [90, 95, 100, 105, 110, 118, 125],
      tension: 0.2,
    },
  ],
};

const salesChartOptions = {
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#768192" } },
    y: {
      beginAtZero: true,
      grid: { color: "rgba(0,0,0,.06)" },
      ticks: { color: "#768192", callback: (value: string | number) => `¥${value}k` },
    },
  },
};

const widgetData = [
  [65, 59, 84, 81, 90, 102, 118],
  [1200, 1420, 1350, 1600, 1710, 1680, 1864],
  [4.2, 4.0, 4.1, 3.9, 3.8, 3.7, 3.86],
  [18, 16, 17, 15, 14, 13, 12],
];

const widgetColors = ["primary", "info", "warning", "danger"];

function widgetChartData(index: number) {
  return {
    labels: ["一", "二", "三", "四", "五", "六", "日"],
    datasets: [
      {
        backgroundColor: "transparent",
        borderColor: "rgba(255,255,255,.75)",
        pointBackgroundColor: "rgba(255,255,255,.9)",
        data: widgetData[index],
        tension: 0.4,
      },
    ],
  };
}

const widgetChartOptions = {
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: { x: { display: false }, y: { display: false } },
  elements: { line: { borderWidth: 2 }, point: { radius: 0, hoverRadius: 4 } },
};

const channelRows = [
  {
    name: "Amazon US",
    gmv: "¥82,460",
    share: 64,
    orders: 1198,
    conversion: "4.12%",
    color: "primary",
  },
  {
    name: "Shopify",
    gmv: "¥28,960",
    share: 23,
    orders: 426,
    conversion: "3.48%",
    color: "success",
  },
  {
    name: "TikTok Shop",
    gmv: "¥17,220",
    share: 13,
    orders: 240,
    conversion: "2.91%",
    color: "warning",
  },
];

const insightRows = [
  {
    level: "机会",
    color: "success",
    title: "便携咖啡机市场进入窗口扩大",
    detail: "US 站搜索热度上涨，头部集中度下降 4.2%。",
  },
  {
    level: "优化",
    color: "warning",
    title: "核心 SKU Listing 可优化",
    detail: "流量稳定但转化下降，建议复核首屏卖点。",
  },
  {
    level: "风险",
    color: "danger",
    title: "补货节点需要提前",
    detail: "当前可售库存覆盖 12 天，低于补货周期。",
  },
];

function statusLabel(value: string) {
  return statusLabels[value] ?? value;
}

function intentLabel(value: string) {
  return intentLabels[value] ?? value;
}

function statusColor(value: string) {
  if (value === "COMPLETED") return "success";
  if (value === "WAITING_APPROVAL") return "warning";
  if (value === "FAILED" || value === "CANCELLED") return "danger";
  return "info";
}

async function signOut() {
  await logout();
  setSession(null);
}
</script>

<template>
  <LoginPage v-if="!currentSession" />
  <template v-else>
    <CSidebar
      class="border-end commerce-sidebar"
      color-scheme="dark"
      position="fixed"
      :visible="sidebarVisible"
      @visible-change="(value: boolean) => (sidebarVisible = value)"
    >
      <CSidebarHeader class="border-bottom">
        <CSidebarBrand>
          <span class="brand-mark">EC</span>
          <span class="sidebar-brand-full ms-2">
            <strong>电商智能运营</strong><small>Agent Platform</small>
          </span>
        </CSidebarBrand>
        <CCloseButton class="d-lg-none" dark @click="sidebarVisible = false" />
      </CSidebarHeader>

      <div class="px-3 pt-3">
        <CFormSelect v-model="selectedShopId" size="sm" aria-label="选择店铺">
          <option value="amazon-us-demo">Amazon US 演示店</option>
          <option value="shopify-demo">Shopify 演示店</option>
        </CFormSelect>
      </div>

      <CSidebarNav>
        <CNavTitle>运营控制台</CNavTitle>
        <CNavItem
          v-for="item in visibleNavigationItems.filter((nav) => nav.group === 'overview')"
          :key="item.id"
        >
          <button
            class="nav-link"
            :class="{ active: activeModuleId === item.id }"
            @click="activeModuleId = item.id"
          >
            <CIcon custom-class-name="nav-icon" :icon="navIcons[item.id]" />{{ item.label }}
            <CBadge
              v-if="item.id === 'tasks' && pendingTasks.length"
              color="warning"
              class="ms-auto"
            >
              {{ pendingTasks.length }}
            </CBadge>
          </button>
        </CNavItem>
        <CNavTitle>业务 Agent</CNavTitle>
        <CNavItem
          v-for="item in visibleNavigationItems.filter((nav) => nav.group === 'agent')"
          :key="item.id"
        >
          <button
            class="nav-link"
            :class="{ active: activeModuleId === item.id }"
            @click="activeModuleId = item.id"
          >
            <CIcon custom-class-name="nav-icon" :icon="navIcons[item.id]" />{{ item.label }}
          </button>
        </CNavItem>
        <CNavTitle>平台治理</CNavTitle>
        <CNavItem
          v-for="item in visibleNavigationItems.filter((nav) => nav.group === 'system')"
          :key="item.id"
        >
          <button
            class="nav-link"
            :class="{ active: activeModuleId === item.id }"
            @click="activeModuleId = item.id"
          >
            <CIcon custom-class-name="nav-icon" :icon="navIcons[item.id]" />{{ item.label }}
          </button>
        </CNavItem>
      </CSidebarNav>

      <CSidebarFooter class="border-top px-3 py-3">
        <div class="d-flex align-items-center gap-2 small">
          <CAvatar color="light" text-color="primary" size="sm">
            {{ currentSession.user.username.slice(0, 2).toUpperCase() }}
          </CAvatar>
          <div class="sidebar-brand-full">
            <div class="fw-semibold">{{ currentSession.user.display_name }}</div>
            <small class="text-secondary">{{ currentSession.user.roles.join(" / ") }}</small>
          </div>
        </div>
      </CSidebarFooter>
    </CSidebar>

    <div class="wrapper d-flex flex-column min-vh-100">
      <CHeader position="sticky" class="mb-4 p-0 border-bottom">
        <CContainer class="px-4" fluid>
          <CHeaderToggler class="ps-1" @click="sidebarVisible = !sidebarVisible">
            <CIcon icon="cil-menu" size="lg" />
          </CHeaderToggler>
          <CBreadcrumb class="mb-0 ms-3 d-none d-md-flex">
            <CBreadcrumbItem>运营工作台</CBreadcrumbItem
            ><CBreadcrumbItem active>{{ currentModule.label }}</CBreadcrumbItem>
          </CBreadcrumb>
          <CHeaderNav class="ms-auto align-items-center gap-2">
            <CInputGroup size="sm" class="header-search d-none d-md-flex">
              <CInputGroupText><CIcon icon="cil-magnifying-glass" /></CInputGroupText
              ><CFormInput placeholder="搜索任务、SKU 或报告" />
            </CInputGroup>
            <CNavItem>
              <CNavLink href="#"><CIcon icon="cil-bell" size="lg" /></CNavLink>
            </CNavItem>
            <CDropdown placement="bottom-end" variant="nav-item">
              <CDropdownToggle :caret="false">
                <CAvatar color="primary" text-color="white" size="sm">
                  {{ currentSession.user.username.slice(0, 2).toUpperCase() }}
                </CAvatar>
              </CDropdownToggle>
              <CDropdownMenu>
                <CDropdownHeader>{{ currentSession.user.display_name }}</CDropdownHeader
                ><CDropdownItem href="#">个人设置</CDropdownItem
                ><CDropdownItem href="#" @click.prevent="signOut">退出登录</CDropdownItem>
              </CDropdownMenu>
            </CDropdown>
          </CHeaderNav>
        </CContainer>
      </CHeader>

      <div class="body flex-grow-1">
        <CContainer class="px-4" lg>
          <template v-if="isDashboard">
            <CRow class="align-items-center mb-4">
              <CCol :md="7">
                <div class="text-body-secondary small mb-1">数据截止 {{ dataCutoff }}</div>
                <h2 class="mb-1">经营总览</h2>
                <div class="text-body-secondary">Amazon US 演示店 · 今日经营与 Agent 任务概况</div>
              </CCol>
              <CCol :md="5" class="text-md-end mt-3 mt-md-0">
                <CButton
                  color="secondary"
                  variant="outline"
                  class="me-2"
                  :disabled="loading"
                  @click="loadWorkspace(selectedShopId)"
                >
                  同步数据 </CButton
                ><CButton color="primary" :disabled="creating" @click="createTask(selectedShopId)">
                  <CIcon icon="cil-lightbulb" class="me-2" />{{
                    creating ? "创建中…" : "市场进入评估"
                  }}
                </CButton>
              </CCol>
            </CRow>

            <CAlert v-if="errorMessage" color="danger" dismissible>{{ errorMessage }}</CAlert>

            <CRow :xs="{ gutter: 4 }" class="mb-4">
              <CCol v-for="(metric, index) in overview?.metrics" :key="metric.code" :sm="6" :xl="3">
                <CWidgetStatsA :color="widgetColors[index]">
                  <template #value>
                    {{ metric.display_value }}
                    <span class="fs-6 fw-normal"
                      >({{ metric.change_display }}
                      <CIcon
                        :icon="metric.trend === 'down' ? 'cil-arrow-bottom' : 'cil-arrow-top'"
                      />)</span
                    >
                  </template>
                  <template #title>{{ metric.label }}</template>
                  <template #action>
                    <CDropdown placement="bottom-end">
                      <CDropdownToggle color="transparent" class="p-0 text-white" :caret="false">
                        <CIcon icon="cil-options" class="text-white" /> </CDropdownToggle
                      ><CDropdownMenu>
                        <CDropdownItem href="#">查看明细</CDropdownItem
                        ><CDropdownItem href="#">创建诊断任务</CDropdownItem>
                      </CDropdownMenu>
                    </CDropdown>
                  </template>
                  <template #chart>
                    <CChart
                      type="line"
                      class="mt-3 mx-3"
                      style="height: 70px"
                      :data="widgetChartData(index)"
                      :options="widgetChartOptions"
                    />
                  </template>
                </CWidgetStatsA>
              </CCol>
            </CRow>

            <CRow>
              <CCol :lg="8">
                <CCard class="mb-4">
                  <CCardBody>
                    <CRow>
                      <CCol :sm="5">
                        <h4 class="card-title mb-0">销售趋势</h4>
                        <div class="small text-body-secondary">过去 7 天 · 全渠道 GMV</div> </CCol
                      ><CCol :sm="7" class="d-none d-md-block">
                        <CButton color="primary" class="float-end">
                          <CIcon icon="cil-cloud-download" /> </CButton
                        ><CButtonGroup class="float-end me-3">
                          <CButton color="secondary" variant="outline">日</CButton
                          ><CButton color="secondary" variant="outline" active>周</CButton
                          ><CButton color="secondary" variant="outline">月</CButton>
                        </CButtonGroup>
                      </CCol>
                    </CRow>
                    <CChart
                      type="line"
                      style="height: 300px; margin-top: 32px"
                      :data="salesChartData"
                      :options="salesChartOptions"
                    />
                  </CCardBody>
                  <CCardFooter>
                    <CRow :xs="{ cols: 2, gutter: 4 }" :lg="{ cols: 4 }" class="text-center">
                      <CCol>
                        <div class="text-body-secondary small">GMV</div>
                        <div class="fw-semibold">¥764,820</div>
                        <CProgress class="mt-2" color="primary" thin :value="87" /> </CCol
                      ><CCol>
                        <div class="text-body-secondary small">订单量</div>
                        <div class="fw-semibold">11,284</div>
                        <CProgress class="mt-2" color="info" thin :value="76" /> </CCol
                      ><CCol>
                        <div class="text-body-secondary small">客单价</div>
                        <div class="fw-semibold">¥67.78</div>
                        <CProgress class="mt-2" color="warning" thin :value="63" /> </CCol
                      ><CCol>
                        <div class="text-body-secondary small">退款率</div>
                        <div class="fw-semibold">1.24%</div>
                        <CProgress class="mt-2" color="danger" thin :value="18" />
                      </CCol>
                    </CRow>
                  </CCardFooter>
                </CCard>
              </CCol>
              <CCol :lg="4">
                <CCard class="mb-4">
                  <CCardHeader class="d-flex justify-content-between align-items-center">
                    <span>机会与风险</span><CBadge color="primary">Agent 洞察</CBadge>
                  </CCardHeader>
                  <CListGroup flush>
                    <CListGroupItem v-for="item in insightRows" :key="item.title" class="py-3">
                      <div class="d-flex align-items-start gap-3">
                        <CBadge :color="item.color" shape="rounded-pill">{{ item.level }}</CBadge>
                        <div>
                          <div class="fw-semibold small">{{ item.title }}</div>
                          <div class="small text-body-secondary mt-1">{{ item.detail }}</div>
                        </div>
                      </div>
                    </CListGroupItem>
                  </CListGroup>
                  <CCardFooter>
                    <CButton
                      color="primary"
                      variant="ghost"
                      size="sm"
                      class="w-100"
                      @click="activeModuleId = 'diagnosis'"
                    >
                      查看经营诊断
                    </CButton>
                  </CCardFooter>
                </CCard>
              </CCol>
            </CRow>

            <CRow>
              <CCol :lg="8">
                <CCard class="mb-4">
                  <CCardHeader class="d-flex justify-content-between align-items-center">
                    <span>Agent 任务</span
                    ><CButton
                      color="primary"
                      variant="ghost"
                      size="sm"
                      @click="activeModuleId = 'tasks'"
                    >
                      查看全部
                    </CButton>
                  </CCardHeader>
                  <CCardBody class="p-0">
                    <CTable align="middle" class="mb-0" hover responsive>
                      <CTableHead class="text-nowrap">
                        <CTableRow>
                          <CTableHeaderCell class="bg-body-secondary">任务</CTableHeaderCell
                          ><CTableHeaderCell class="bg-body-secondary">工作流</CTableHeaderCell
                          ><CTableHeaderCell class="bg-body-secondary">负责人</CTableHeaderCell
                          ><CTableHeaderCell class="bg-body-secondary"> 状态 </CTableHeaderCell>
                        </CTableRow>
                      </CTableHead>
                      <CTableBody>
                        <CTableRow v-if="!tasks.length">
                          <CTableDataCell colspan="4" class="text-center py-5 text-body-secondary">
                            暂无任务，可从“市场进入评估”开始。
                          </CTableDataCell>
                        </CTableRow>
                        <CTableRow v-for="task in tasks.slice(0, 5)" :key="task.id">
                          <CTableDataCell>
                            <div class="fw-semibold text-truncate task-name">
                              {{ task.request.user_query }}
                            </div>
                            <div class="small text-body-secondary">
                              #{{ task.id.slice(0, 8) }} · {{ task.created_at.slice(0, 10) }}
                            </div> </CTableDataCell
                          ><CTableDataCell>
                            <CBadge color="secondary">
                              {{ intentLabel(task.request.intent) }}
                            </CBadge> </CTableDataCell
                          ><CTableDataCell>
                            <div class="d-flex align-items-center gap-2">
                              <CAvatar color="light" size="sm">
                                {{ task.request.user_id.slice(0, 2).toUpperCase() }} </CAvatar
                              ><span class="small">{{ task.request.user_id }}</span>
                            </div> </CTableDataCell
                          ><CTableDataCell>
                            <CBadge :color="statusColor(task.status)">
                              {{ statusLabel(task.status) }}
                            </CBadge>
                          </CTableDataCell>
                        </CTableRow>
                      </CTableBody>
                    </CTable>
                  </CCardBody>
                </CCard>
              </CCol>
              <CCol :lg="4">
                <CCard class="mb-4">
                  <CCardHeader>渠道贡献</CCardHeader
                  ><CCardBody>
                    <div
                      v-for="channel in channelRows"
                      :key="channel.name"
                      class="progress-group mb-4"
                    >
                      <div class="progress-group-header">
                        <span class="title fw-semibold">{{ channel.name }}</span
                        ><span class="ms-auto fw-semibold">{{ channel.gmv }}</span>
                      </div>
                      <div class="small text-body-secondary mb-2">
                        {{ channel.orders }} 单 · 转化 {{ channel.conversion }}
                      </div>
                      <CProgress thin :color="channel.color" :value="channel.share" />
                    </div>
                  </CCardBody>
                </CCard>
              </CCol>
            </CRow>
          </template>

          <PermissionWorkspace v-else-if="isPermissions" />
          <ModuleWorkspace v-else :module="currentModule" />
        </CContainer>
      </div>

      <CFooter class="px-4">
        <div>
          <a href="https://coreui.io" target="_blank" rel="noreferrer">CoreUI</a
          ><span class="ms-1">adapted for 电商智能运营 Agent 平台</span>
        </div>
        <div class="ms-auto"><span class="me-1">版本</span><strong>0.1.0</strong></div>
      </CFooter>
    </div>
  </template>
</template>

<style scoped>
:global(body) {
  background-color: var(--cui-tertiary-bg);
}
.wrapper {
  width: 100%;
  padding-inline-start: var(--cui-sidebar-occupy-start, 0);
  transition: padding 0.15s;
}
.commerce-sidebar {
  --cui-sidebar-bg: #212631;
  --cui-sidebar-brand-bg: #1b1f27;
}
.sidebar-header {
  min-height: 4rem;
}
.brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  color: #fff;
  background: var(--cui-primary);
  border-radius: 7px;
  place-items: center;
  font-size: 11px;
  font-weight: 800;
}
.sidebar-brand-full {
  display: inline-flex;
  flex-direction: column;
  text-align: left;
}
.sidebar-brand-full strong {
  font-size: 14px;
}
.sidebar-brand-full small {
  margin-top: 1px;
  font-size: 9px;
  font-weight: 400;
  opacity: 0.65;
}
.commerce-sidebar .nav-link {
  width: 100%;
  border: 0;
  text-align: left;
}
.commerce-sidebar .nav-link.active {
  color: #fff;
  background: var(--cui-primary);
}
.commerce-sidebar .sidebar-nav {
  padding-top: 0.5rem;
}
.commerce-sidebar .sidebar-footer {
  margin-top: auto;
}
.header-search {
  width: 260px;
}
.task-name {
  max-width: 360px;
}
.body {
  min-height: calc(100vh - 8rem);
}
@media (max-width: 991.98px) {
  .wrapper {
    padding-inline-start: 0;
  }
  .commerce-sidebar:not(.show) {
    margin-left: -256px;
  }
}
</style>
