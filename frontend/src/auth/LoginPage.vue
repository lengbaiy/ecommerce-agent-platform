<script setup lang="ts">
import { onMounted, ref } from "vue";

import { createCaptcha, login, verifyCaptcha, type CaptchaChallenge } from "./api";
import { setSession } from "./session";

const tenantId = ref("local");
const username = ref("admin");
const password = ref("");
const captcha = ref<CaptchaChallenge | null>(null);
const sliderPosition = ref(0);
const captchaVerified = ref(false);
const loading = ref(false);
const message = ref("");

async function refreshCaptcha(clearMessage = true) {
  captcha.value = await createCaptcha();
  sliderPosition.value = 0;
  captchaVerified.value = false;
  if (clearMessage) message.value = "";
}

async function finishSlider() {
  if (!captcha.value) return;
  try {
    await verifyCaptcha(captcha.value.id, sliderPosition.value);
    captchaVerified.value = true;
    message.value = "验证通过";
  } catch (error) {
    message.value = error instanceof Error ? error.message : "验证失败";
    await refreshCaptcha(false);
  }
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
  if (!captcha.value || !captchaVerified.value) {
    message.value = "请先完成滑块验证";
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
        captcha_id: captcha.value.id,
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
          <div v-if="captcha" class="captcha-scene">
            <img :src="captcha.image_url" alt="滑块验证码背景" />
            <div class="captcha-piece" :style="{ left: `${sliderPosition}%` }"></div>
          </div>
          <input
            v-model.number="sliderPosition"
            class="captcha-slider"
            type="range"
            min="0"
            max="100"
            :disabled="captchaVerified"
            aria-label="拖动滑块完成安全验证"
            @change="finishSlider"
          />
          <div class="captcha-tip" :class="{ verified: captchaVerified }">
            {{ captchaVerified ? "✓ 验证通过" : "拖动滑块，使拼图对准缺口" }}
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
        <CButton color="primary" size="lg" type="submit" :disabled="loading">
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
.captcha-scene {
  position: relative;
  height: 82px;
  overflow: hidden;
  border-radius: 8px;
  background: linear-gradient(135deg, #dbeafe, #eef2ff 45%, #d1fae5);
}
.captcha-scene img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.captcha-piece {
  position: absolute;
  top: 24px;
  width: 28px;
  height: 28px;
  transform: translateX(-50%);
  border-radius: 5px;
}
.captcha-piece {
  border: 2px solid white;
  background: #5856d6;
  box-shadow: 0 3px 10px rgb(16 24 40 / 25%);
}
.captcha-slider {
  width: 100%;
  margin-top: 12px;
  accent-color: #5856d6;
}
.captcha-tip {
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
