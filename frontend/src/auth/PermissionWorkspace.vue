<script setup lang="ts">
import { onMounted, ref } from "vue";

import { createUser, fetchUsers, updateUser } from "./api";
import type { SessionUser } from "./session";

const users = ref<SessionUser[]>([]);
const username = ref("");
const displayName = ref("");
const password = ref("");
const role = ref("operator");
const message = ref("");

async function load() {
  users.value = (await fetchUsers()).items;
}

async function submit() {
  message.value = "";
  try {
    await createUser({
      username: username.value,
      display_name: displayName.value,
      password: password.value,
      roles: [role.value],
    });
    username.value = "";
    displayName.value = "";
    password.value = "";
    message.value = "用户已创建";
    await load();
  } catch (error) {
    message.value = error instanceof Error ? error.message : "创建失败";
  }
}

async function changeRole(user: SessionUser, event: Event) {
  const target = event.target as HTMLSelectElement;
  await changeUser(user.id, { roles: [target.value] });
}

async function changeEnabled(user: SessionUser, event: Event) {
  const target = event.target as HTMLInputElement;
  await changeUser(user.id, { enabled: target.checked });
}

async function changeUser(userId: string, payload: { roles?: string[]; enabled?: boolean }) {
  message.value = "";
  try {
    await updateUser(userId, payload);
    message.value = "权限设置已更新，目标账号的旧会话已失效";
  } catch (error) {
    message.value = error instanceof Error ? error.message : "更新失败";
  } finally {
    await load();
  }
}

onMounted(load);
</script>

<template>
  <CRow>
    <CCol :lg="8">
      <CCard class="mb-4">
        <CCardHeader><strong>用户与角色</strong></CCardHeader>
        <CCardBody class="p-0">
          <CTable align="middle" class="mb-0" hover responsive>
            <CTableHead
              ><CTableRow
                ><CTableHeaderCell>用户</CTableHeaderCell><CTableHeaderCell>角色</CTableHeaderCell
                ><CTableHeaderCell>状态</CTableHeaderCell
                ><CTableHeaderCell>权限</CTableHeaderCell></CTableRow
              ></CTableHead
            >
            <CTableBody>
              <CTableRow v-for="user in users" :key="user.id">
                <CTableDataCell
                  ><strong>{{ user.display_name }}</strong>
                  <div class="small text-body-secondary">
                    {{ user.username }} · {{ user.tenant_id }}
                  </div></CTableDataCell
                >
                <CTableDataCell
                  ><CFormSelect
                    size="sm"
                    :model-value="user.roles[0]"
                    @change="changeRole(user, $event)"
                    ><option value="operator">运营人员</option>
                    <option value="approver">审批人员</option>
                    <option value="admin">系统管理员</option></CFormSelect
                  ></CTableDataCell
                >
                <CTableDataCell
                  ><CFormSwitch
                    :model-value="user.enabled"
                    :label="user.enabled ? '启用' : '停用'"
                    @change="changeEnabled(user, $event)"
                /></CTableDataCell>
                <CTableDataCell
                  ><span class="small text-body-secondary">{{
                    user.permissions.join(" · ")
                  }}</span></CTableDataCell
                >
              </CTableRow>
            </CTableBody>
          </CTable>
        </CCardBody>
      </CCard>
    </CCol>
    <CCol :lg="4">
      <CCard>
        <CCardHeader><strong>创建用户</strong></CCardHeader>
        <CCardBody
          ><form class="d-grid gap-3" @submit.prevent="submit">
            <CFormInput v-model="username" label="用户名" required />
            <CFormInput v-model="displayName" label="显示名称" required />
            <CFormInput v-model="password" label="初始密码" type="password" required />
            <CFormSelect v-model="role" label="角色"
              ><option value="operator">运营人员</option>
              <option value="approver">审批人员</option>
              <option value="admin">系统管理员</option></CFormSelect
            >
            <CAlert v-if="message" color="info" class="mb-0 py-2">{{ message }}</CAlert>
            <CButton color="primary" type="submit">创建用户</CButton>
          </form></CCardBody
        >
      </CCard>
    </CCol>
  </CRow>
</template>
