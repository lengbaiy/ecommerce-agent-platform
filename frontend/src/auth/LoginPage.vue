<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import SlideVerify, { type SlideVerifyInstance } from "vue3-slide-verify";
import "vue3-slide-verify/dist/style.css";

import { createCaptcha, login, type CaptchaChallenge } from "./api";
import { setSession } from "./session";

const tenantId = ref("local");
const username = ref("admin");
const password = ref("Admin@123456");
const captcha = ref<CaptchaChallenge | null>(null);
const sliderPosition = ref<number | null>(null);
const captchaMessage = ref("请拖动拼图滑块完成验证");
const block = ref<SlideVerifyInstance>();
const loading = ref(false);
const message = ref("");
const captchaReady = computed(() => Boolean(captcha.value));

async function refreshCaptcha(clearMessage = true) {
  captcha.value = await createCaptcha();
  sliderPosition.value = null;
  captchaMessage.value = "请拖动拼图滑块完成验证";
  if (clearMessage) message.value = "";
  block.value?.refresh();
}

function onSuccess(detail: { timestamp: number; left: number }) {
  sliderPosition.value = Math.round(detail.left);
  captchaMessage.value = `验证通过，用时 ${(detail.timestamp / 1000).toFixed(1)} 秒`;
  message.value = "";
}

function onFail() {
  sliderPosition.value = null;
  captchaMessage.value = "拼图位置不匹配，请重新拖动";
}

function onAgain() {
  sliderPosition.value = null;
  captchaMessage.value = "检测到异常滑动轨迹，请重新验证";
  block.value?.refresh();
}

async function submit() {
  if (!tenantId.value.trim() || !username.value.trim()) {
    message.value = "请输入租户标识和用户名";
    return;
  }
  if (password.value.length < 8) {
    message.value = "请输入至少 8 位密码";
    return;
  }
  if (!captcha.value || sliderPosition.value === null) {
    message.value = "请先完成拼图滑块验证";
    return;
  }
  loading.value = true;
  message.value = "";
  try {
    setSession(
      await login({
        tenant_id: tenantId.value,
        username: username.value,
        password: password.value,
        captcha_id: captcha.value.captcha_id,
        slider_position: sliderPosition.value,
      }),
    );
  } catch (error) {
    message.value = error instanceof Error ? error.message : "登录失败";
    await refreshCaptcha(false);
  } finally {
    loading.value = false;
  }
}

onMounted(refreshCaptcha);
</script>

<template>
  <main class="login-page">
    <section class="login-brand">
      <span class="brand-mark">EC</span>
      <p class="eyebrow">COMMERCE OPERATIONS</p>
      <h1>电商智能运营<br />Agent 平台</h1>
      <p class="brand-copy">
        让市场洞察、商品策略、内容生产与经营诊断在统一的权限与审计体系中协作。
      </p>
      <ul>
        <li>多租户数据隔离</li>
        <li>角色权限与人工审批</li>
        <li>任务状态持久化与审计</li>
      </ul>
    </section>

    <section class="login-panel">
      <form class="login-card" novalidate @submit.prevent="submit">
        <div>
          <p class="eyebrow">WELCOME BACK</p>
          <h2>登录运营工作台</h2>
          <p class="muted">请输入企业租户与账号信息</p>
        </div>

        <label
          >租户标识<CFormInput v-model="tenantId" autocomplete="organization" required
        /></label>
        <label>用户名<CFormInput v-model="username" autocomplete="username" required /></label>
        <label
          >密码<CFormInput
            v-model="password"
            type="password"
            autocomplete="current-password"
            minlength="8"
            required
        /></label>

        <div class="captcha-field">
          <div class="captcha-header">
            <span>安全验证</span>
            <button type="button" @click="refreshCaptcha()">换一张</button>
          </div>
          <p class="captcha-help">拖动滑块至缺口处，完成登录校验</p>
          <SlideVerify
            v-if="captchaReady"
            ref="block"
            :w="captcha?.canvas_width"
            :h="captcha?.canvas_height"
            :offset="captcha?.puzzle_offset"
            :accuracy="4"
            slider-text="向右拖动完成拼图验证"
            @success="onSuccess"
            @fail="onFail"
            @again="onAgain"
            @refresh="onFail"
          />
          <div class="captcha-tip" :class="{ verified: sliderPosition !== null }">
            {{ captchaMessage }}
          </div>
        </div>

        <CAlert
          v-if="message && message !== '验证通过'"
          color="danger"
          class="py-2 mb-0"
          role="alert"
        >
          {{ message }}
        </CAlert>
        <CButton
          color="primary"
          size="lg"
          type="submit"
          :disabled="!captchaReady || loading || sliderPosition === null"
        >
          {{ loading ? "正在登录…" : "登录" }}
        </CButton>
        <p class="demo-account">首次启动账号：<strong>local / admin / Admin@123456</strong></p>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(360px, 46%) 1fr;
  background: #f4f6f9;
}
.login-brand {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(48px, 8vw, 120px);
  overflow: hidden;
  color: white;
  background: linear-gradient(145deg, #1b1f27, #272d3a 65%, #321fdb);
}
.login-brand::after {
  position: absolute;
  width: 420px;
  height: 420px;
  right: -170px;
  bottom: -160px;
  content: "";
  border: 80px solid rgb(255 255 255 / 7%);
  border-radius: 50%;
}
.brand-mark {
  display: grid;
  width: 46px;
  height: 46px;
  margin-bottom: 52px;
  place-items: center;
  border-radius: 10px;
  color: white;
  background: #5856d6;
  font-weight: 800;
}
.eyebrow {
  margin: 0 0 10px;
  color: #8f8cff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
}
.login-brand h1 {
  margin: 0;
  font-size: clamp(38px, 4vw, 58px);
  line-height: 1.15;
}
.brand-copy {
  max-width: 520px;
  margin: 28px 0;
  color: #c7cbd3;
  font-size: 17px;
  line-height: 1.8;
}
.login-brand ul {
  padding: 0;
  list-style: none;
  color: #e5e7eb;
  line-height: 2.2;
}
.login-brand li::before {
  margin-right: 12px;
  content: "✓";
  color: #66d9a7;
}
.login-panel {
  display: grid;
  place-items: center;
  padding: 32px;
}
.login-card {
  width: min(440px, 100%);
  display: grid;
  gap: 20px;
  padding: 38px;
  border: 1px solid #e4e7ec;
  border-radius: 18px;
  background: white;
  box-shadow: 0 20px 55px rgb(16 24 40 / 9%);
}
.login-card h2 {
  margin: 0;
  font-size: 28px;
}
.muted,
.demo-account {
  color: #667085;
}
.login-card label {
  display: grid;
  gap: 8px;
  color: #344054;
  font-size: 14px;
  font-weight: 600;
}
.captcha-field {
  padding: 14px;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
}
.captcha-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
}
.captcha-header button {
  border: 0;
  color: #5856d6;
  background: transparent;
}
.captcha-help {
  margin: 7px 0 10px;
  color: #8491a5;
  font-size: 12px;
}
.captcha-field :deep(.slide-verify) {
  max-width: 100%;
  margin: 0 auto;
}
.captcha-field :deep(.slide-verify-block) {
  max-width: 100%;
}
.captcha-tip {
  margin-top: 8px;
  text-align: center;
  color: #667085;
  font-size: 12px;
}
.captcha-tip.verified {
  color: #198754;
  font-weight: 700;
}
.demo-account {
  margin: 0;
  text-align: center;
  font-size: 12px;
}
@media (max-width: 820px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .login-brand {
    display: none;
  }
  .login-panel {
    min-height: 100vh;
    padding: 18px;
  }
  .login-card {
    padding: 26px;
  }
}
</style>
