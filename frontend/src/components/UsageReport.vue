<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Activity, Coins, Gauge, RotateCcw, Save, TrendingUp, Wallet } from "lucide-vue-next";
import { Area } from "@antv/g2plot";

interface UsageReportData {
  month_start: string;
  used_tokens: number;
  budget_tokens: number;
  remaining_tokens: number | null;
  percent_used: number | null;
  by_source: Record<string, number>;
  daily_series: { date: string; total_tokens: number }[];
}

const props = defineProps<{
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
}>();

const SOURCE_META: Record<string, { label: string; color: string }> = {
  agent_chat: { label: "Agent 对话", color: "#6366f1" },
  reply_analysis: { label: "回复分析", color: "#06b6d4" },
  email_generation: { label: "邮件生成", color: "#10b981" },
};
const FALLBACK_COLORS = ["#f59e0b", "#ec4899", "#8b5cf6", "#f43f5e"];

const loading = ref(true);
const saving = ref(false);
const toast = ref<{ text: string; kind: "ok" | "err" } | null>(null);
const budgetInput = ref(0);
const report = ref<UsageReportData>({
  month_start: "",
  used_tokens: 0,
  budget_tokens: 0,
  remaining_tokens: null,
  percent_used: null,
  by_source: {},
  daily_series: [],
});

// ── Derived data ────────────────────────────────────────────────────────────
const hasBudget = computed(() => report.value.budget_tokens > 0);
const percentUsed = computed(() => Math.min(999, report.value.percent_used ?? 0));
const meterKind = computed<"ok" | "warn" | "danger">(() => {
  const pct = report.value.percent_used ?? 0;
  if (pct >= 100) return "danger";
  if (pct >= 80) return "warn";
  return "ok";
});
const meterColor = computed(() =>
  ({ ok: "#2563eb", warn: "#d97706", danger: "#dc2626" }[meterKind.value]),
);

// Days elapsed in the current (UTC) month, for a fair daily average.
const daysElapsed = computed(() => {
  const start = report.value.month_start ? new Date(report.value.month_start) : new Date();
  const now = new Date();
  return Math.max(1, Math.floor((now.getTime() - start.getTime()) / 86_400_000) + 1);
});
const dailyAvg = computed(() => Math.round(report.value.used_tokens / daysElapsed.value));

// A continuous 30-day axis (backend only returns days that have records).
const series = computed(() => {
  const map = new Map(report.value.daily_series.map((d) => [d.date, d.total_tokens]));
  const out: { date: string; total: number }[] = [];
  const today = new Date();
  for (let i = 29; i >= 0; i -= 1) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - i));
    const iso = d.toISOString().slice(0, 10);
    out.push({ date: iso, total: map.get(iso) ?? 0 });
  }
  return out;
});
const peakDay = computed(() =>
  series.value.reduce((m, d) => Math.max(m, d.total), 0),
);
const has30dData = computed(() => series.value.some((d) => d.total > 0));

const sourceEntries = computed(() => {
  const total = Math.max(1, report.value.used_tokens);
  let fb = 0;
  return Object.entries(report.value.by_source)
    .map(([key, tokens]) => {
      const meta = SOURCE_META[key];
      const color = meta ? meta.color : FALLBACK_COLORS[fb++ % FALLBACK_COLORS.length];
      return { key, label: meta?.label || key, tokens, color, pct: (tokens / total) * 100 };
    })
    .sort((a, b) => b.tokens - a.tokens);
});

// ── 30-day trend chart (AntV / G2Plot) ──────────────────────────────────────
const chartEl = ref<HTMLDivElement | null>(null);
let chart: Area | null = null;

function chartConfig(): Record<string, unknown> {
  return {
    data: series.value,
    xField: "date",
    yField: "total",
    smooth: true,
    autoFit: true,
    height: 280,
    padding: [18, 18, 36, 48],
    color: "#2563eb",
    areaStyle: { fill: "l(90) 0:#2563eb 1:#ffffff", fillOpacity: 0.18 },
    line: { color: "#2563eb", size: 2.5 },
    meta: {
      date: { alias: "日期" },
      total: { alias: "token" },
    },
    xAxis: {
      tickCount: 6,
      line: null,
      tickLine: null,
      label: {
        style: { fill: "#94a3b8", fontSize: 10 },
        formatter: (v: string) => fmtDay(v),
      },
    },
    yAxis: {
      label: { style: { fill: "#94a3b8", fontSize: 10 }, formatter: (v: string) => compact(Number(v)) },
      grid: { line: { style: { stroke: "#eef2f7", lineWidth: 1 } } },
    },
    tooltip: {
      showCrosshairs: true,
      crosshairs: { type: "x", line: { style: { stroke: "#cbd5e1", lineDash: [3, 3] } } },
      formatter: (datum: { total: number }) => ({
        name: "token",
        value: Number(datum.total).toLocaleString("en-US"),
      }),
    },
    animation: { appear: { animation: "wave-in", duration: 500 } },
  };
}

function renderChart(): void {
  // The mount node only exists when there's data (v-if in the template).
  if (!chartEl.value) {
    chart?.destroy();
    chart = null;
    return;
  }
  if (chart) {
    chart.update(chartConfig() as never);
  } else {
    chart = new Area(chartEl.value, chartConfig() as never);
    chart.render();
  }
}

watch(
  () => [loading.value, has30dData.value, series.value] as const,
  () => nextTick(renderChart),
  { flush: "post" },
);
onBeforeUnmount(() => {
  chart?.destroy();
  chart = null;
});

// ── Donut geometry ──────────────────────────────────────────────────────────
const DONUT_R = 56;
const DONUT_C = 2 * Math.PI * DONUT_R;
const donutArcs = computed(() => {
  const total = sourceEntries.value.reduce((s, e) => s + e.tokens, 0);
  if (total <= 0) return [];
  let offset = 0;
  return sourceEntries.value.map((e) => {
    const dash = (e.tokens / total) * DONUT_C;
    const arc = { color: e.color, dasharray: `${dash} ${DONUT_C - dash}`, dashoffset: -offset };
    offset += dash;
    return arc;
  });
});

// ── Formatting ──────────────────────────────────────────────────────────────
function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return String(Math.round(n));
}
function fmt(n: number): string {
  return n.toLocaleString("en-US");
}
function fmtDay(iso: string): string {
  const parts = iso.split("-");
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : iso;
}

function flash(text: string, kind: "ok" | "err" = "ok"): void {
  toast.value = { text, kind };
  setTimeout(() => (toast.value = null), 2600);
}
function errText(e: unknown): string {
  if (e instanceof Error) {
    try {
      return (JSON.parse(e.message) as { detail?: string }).detail || e.message;
    } catch {
      return e.message;
    }
  }
  return "操作失败";
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    report.value = await props.request<UsageReportData>("/usage/token-report");
    budgetInput.value = report.value.budget_tokens;
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    loading.value = false;
  }
}

async function saveBudget(): Promise<void> {
  if (budgetInput.value < 0) {
    flash("额度不能为负数", "err");
    return;
  }
  saving.value = true;
  try {
    report.value = await props.request<UsageReportData>("/usage/token-budget", {
      method: "PUT",
      body: JSON.stringify({ budget_tokens: Math.round(budgetInput.value) }),
    });
    flash(budgetInput.value > 0 ? "已保存每月 token 额度" : "已取消额度上限");
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    saving.value = false;
  }
}

function applyPreset(v: number): void {
  budgetInput.value = v;
}

onMounted(load);
defineExpose({ reload: load });
</script>

<template>
  <section class="ur">
    <transition name="ur-fade">
      <div v-if="toast" :class="['ur-toast', toast.kind]">{{ toast.text }}</div>
    </transition>

    <div v-if="loading" class="ur-loading">
      <span class="ur-spinner" /> 加载用量数据…
    </div>

    <template v-else>
      <!-- KPI row -->
      <div class="ur-kpis">
        <article class="ur-kpi">
          <div class="ur-kpi-top">
            <span class="ur-kpi-icon" style="--c: #6366f1"><Coins :size="17" /></span>
            <span class="ur-kpi-label">本月已用</span>
          </div>
          <div class="ur-kpi-value">{{ fmt(report.used_tokens) }}</div>
          <div class="ur-kpi-sub">token · 累计 {{ daysElapsed }} 天</div>
        </article>

        <article class="ur-kpi">
          <div class="ur-kpi-top">
            <span class="ur-kpi-icon" style="--c: #10b981"><Wallet :size="17" /></span>
            <span class="ur-kpi-label">剩余额度</span>
          </div>
          <div class="ur-kpi-value">
            {{ hasBudget ? fmt(report.remaining_tokens ?? 0) : "∞" }}
          </div>
          <div class="ur-kpi-sub">{{ hasBudget ? `总额度 ${compact(report.budget_tokens)}` : "未设置额度上限" }}</div>
        </article>

        <article class="ur-kpi">
          <div class="ur-kpi-top">
            <span class="ur-kpi-icon" :style="{ '--c': meterColor }"><Gauge :size="17" /></span>
            <span class="ur-kpi-label">额度使用率</span>
          </div>
          <div class="ur-kpi-value" :style="{ color: hasBudget ? meterColor : undefined }">
            {{ hasBudget ? `${report.percent_used}%` : "—" }}
          </div>
          <div class="ur-kpi-mini">
            <div class="ur-kpi-mini-track">
              <div class="ur-kpi-mini-fill" :style="{ width: Math.min(100, percentUsed) + '%', background: meterColor }" />
            </div>
          </div>
        </article>

        <article class="ur-kpi">
          <div class="ur-kpi-top">
            <span class="ur-kpi-icon" style="--c: #0ea5e9"><Activity :size="17" /></span>
            <span class="ur-kpi-label">日均用量</span>
          </div>
          <div class="ur-kpi-value">{{ fmt(dailyAvg) }}</div>
          <div class="ur-kpi-sub">近 30 天峰值 {{ compact(peakDay) }}</div>
        </article>
      </div>

      <!-- Middle row: budget gauge + source donut -->
      <div class="ur-mid">
        <article class="ur-card ur-gauge-card">
          <div class="ur-card-head">
            <div><strong>月度额度</strong><p>本月 token 消耗占额度的比例。</p></div>
            <button class="ur-ghost" type="button" @click="load"><RotateCcw :size="13" /> 刷新</button>
          </div>

          <div class="ur-gauge-body">
            <div class="ur-radial">
              <svg viewBox="0 0 140 140" class="ur-radial-svg">
                <circle cx="70" cy="70" r="60" class="ur-radial-track" />
                <circle
                  cx="70"
                  cy="70"
                  r="60"
                  class="ur-radial-fill"
                  :stroke="hasBudget ? meterColor : '#cbd5e1'"
                  :stroke-dasharray="2 * Math.PI * 60"
                  :stroke-dashoffset="(1 - Math.min(1, (hasBudget ? percentUsed : 0) / 100)) * 2 * Math.PI * 60"
                  transform="rotate(-90 70 70)"
                />
              </svg>
              <div class="ur-radial-center">
                <template v-if="hasBudget">
                  <span class="ur-radial-pct" :style="{ color: meterColor }">{{ report.percent_used }}%</span>
                  <span class="ur-radial-cap">已使用</span>
                </template>
                <template v-else>
                  <span class="ur-radial-inf">∞</span>
                  <span class="ur-radial-cap">不限额度</span>
                </template>
              </div>
            </div>

            <div class="ur-gauge-stats">
              <div class="ur-stat-line">
                <span class="ur-dot" :style="{ background: meterColor }" />
                <span class="ur-stat-k">已用</span>
                <span class="ur-stat-v">{{ fmt(report.used_tokens) }}</span>
              </div>
              <div class="ur-stat-line">
                <span class="ur-dot ur-dot-ghost" />
                <span class="ur-stat-k">{{ hasBudget ? "剩余" : "本月请求" }}</span>
                <span class="ur-stat-v">{{ hasBudget ? fmt(report.remaining_tokens ?? 0) : "无上限" }}</span>
              </div>
              <div class="ur-stat-line ur-stat-total">
                <span class="ur-stat-k">总额度</span>
                <span class="ur-stat-v">{{ hasBudget ? fmt(report.budget_tokens) : "未设置" }}</span>
              </div>

              <div class="ur-budget-edit">
                <label>每月 token 额度</label>
                <div class="ur-budget-row">
                  <input v-model.number="budgetInput" type="number" min="0" step="10000" class="ur-input" />
                  <button type="button" class="ur-save" :disabled="saving" @click="saveBudget">
                    <Save :size="14" /> {{ saving ? "保存中" : "保存" }}
                  </button>
                </div>
                <div class="ur-presets">
                  <button type="button" @click="applyPreset(0)">不限</button>
                  <button type="button" @click="applyPreset(1_000_000)">1M</button>
                  <button type="button" @click="applyPreset(5_000_000)">5M</button>
                  <button type="button" @click="applyPreset(10_000_000)">10M</button>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="ur-card ur-donut-card">
          <div class="ur-card-head">
            <div><strong>用量来源</strong><p>本月各功能消耗占比。</p></div>
          </div>
          <div v-if="sourceEntries.length === 0" class="ur-empty">本月暂无用量记录</div>
          <div v-else class="ur-donut-body">
            <div class="ur-donut">
              <svg viewBox="0 0 140 140" class="ur-donut-svg">
                <circle cx="70" cy="70" :r="DONUT_R" class="ur-donut-track" />
                <circle
                  v-for="(arc, i) in donutArcs"
                  :key="i"
                  cx="70"
                  cy="70"
                  :r="DONUT_R"
                  fill="none"
                  :stroke="arc.color"
                  stroke-width="18"
                  :stroke-dasharray="arc.dasharray"
                  :stroke-dashoffset="arc.dashoffset"
                  transform="rotate(-90 70 70)"
                />
              </svg>
              <div class="ur-donut-center">
                <span class="ur-donut-total">{{ compact(report.used_tokens) }}</span>
                <span class="ur-donut-cap">总 token</span>
              </div>
            </div>
            <ul class="ur-legend">
              <li v-for="entry in sourceEntries" :key="entry.key">
                <span class="ur-dot" :style="{ background: entry.color }" />
                <span class="ur-legend-label">{{ entry.label }}</span>
                <span class="ur-legend-pct">{{ entry.pct.toFixed(0) }}%</span>
                <span class="ur-legend-val">{{ fmt(entry.tokens) }}</span>
              </li>
            </ul>
          </div>
        </article>
      </div>

      <!-- Trend chart -->
      <article class="ur-card ur-trend-card">
        <div class="ur-card-head">
          <div>
            <strong>近 30 天用量走势</strong>
            <p>每日 token 消耗总量（UTC）。</p>
          </div>
          <span class="ur-trend-tag"><TrendingUp :size="13" /> 日粒度</span>
        </div>

        <div v-if="!has30dData" class="ur-empty ur-empty-tall">近 30 天暂无用量记录</div>
        <div v-else ref="chartEl" class="ur-chart-mount"></div>
      </article>
    </template>
  </section>
</template>

<style scoped>
.ur { display: flex; flex-direction: column; gap: 18px; }

.ur-toast { position: fixed; top: 22px; left: 50%; transform: translateX(-50%); z-index: 1200; padding: 10px 18px; border-radius: 10px; font-size: 13px; font-weight: 700; box-shadow: 0 12px 28px rgba(15,23,42,.14); }
.ur-toast.ok { background: #ecfdf5; color: #047857; }
.ur-toast.err { background: #fef2f2; color: #b91c1c; }
.ur-fade-enter-active, .ur-fade-leave-active { transition: opacity 200ms ease; }
.ur-fade-enter-from, .ur-fade-leave-to { opacity: 0; }

.ur-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 60px; color: #94a3b8; font-size: 14px; }
.ur-spinner { width: 18px; height: 18px; border: 2px solid #e2e8f0; border-top-color: #2563eb; border-radius: 50%; animation: ur-spin .7s linear infinite; }
@keyframes ur-spin { to { transform: rotate(360deg); } }

/* KPI cards */
.ur-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.ur-kpi {
  background: #fff; border: 1px solid #e9eef5; border-radius: 16px; padding: 16px 18px;
  display: flex; flex-direction: column; gap: 8px;
  box-shadow: 0 1px 2px rgba(15,23,42,.03);
  transition: box-shadow .2s ease, transform .2s ease;
}
.ur-kpi:hover { box-shadow: 0 8px 24px rgba(15,23,42,.07); transform: translateY(-2px); }
.ur-kpi-top { display: flex; align-items: center; gap: 9px; }
.ur-kpi-icon { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; color: var(--c); background: color-mix(in srgb, var(--c) 12%, #fff); }
.ur-kpi-label { font-size: 12.5px; color: #64748b; font-weight: 600; }
.ur-kpi-value { font-size: 26px; font-weight: 800; color: #0f172a; letter-spacing: -.02em; font-variant-numeric: tabular-nums; line-height: 1.1; }
.ur-kpi-sub { font-size: 12px; color: #94a3b8; }
.ur-kpi-mini { padding-top: 4px; }
.ur-kpi-mini-track { height: 6px; border-radius: 999px; background: #f1f5f9; overflow: hidden; }
.ur-kpi-mini-fill { height: 100%; border-radius: 999px; transition: width .4s ease; }

/* Generic card */
.ur-card { background: #fff; border: 1px solid #e9eef5; border-radius: 16px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(15,23,42,.03); }
.ur-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
.ur-card-head strong { font-size: 15px; color: #0f172a; }
.ur-card-head p { margin: 3px 0 0; font-size: 12.5px; color: #64748b; }
.ur-ghost { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 11px; cursor: pointer; font-size: 12.5px; display: inline-flex; align-items: center; gap: 5px; color: #475569; }
.ur-ghost:hover { background: #f8fafc; }

.ur-mid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 14px; }

/* Radial gauge */
.ur-gauge-body { display: flex; gap: 24px; align-items: center; }
.ur-radial { position: relative; width: 140px; height: 140px; flex-shrink: 0; }
.ur-radial-svg { width: 140px; height: 140px; }
.ur-radial-track { fill: none; stroke: #f1f5f9; stroke-width: 12; }
.ur-radial-fill { fill: none; stroke-width: 12; stroke-linecap: round; transition: stroke-dashoffset .6s cubic-bezier(.4,0,.2,1), stroke .3s; }
.ur-radial-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; }
.ur-radial-pct { font-size: 26px; font-weight: 800; letter-spacing: -.02em; }
.ur-radial-inf { font-size: 30px; font-weight: 800; color: #94a3b8; }
.ur-radial-cap { font-size: 11.5px; color: #94a3b8; }
.ur-gauge-stats { flex: 1; display: flex; flex-direction: column; gap: 9px; min-width: 0; }
.ur-stat-line { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.ur-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.ur-dot-ghost { background: #e2e8f0; }
.ur-stat-k { color: #64748b; }
.ur-stat-v { margin-left: auto; font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }
.ur-stat-total { border-top: 1px dashed #e9eef5; padding-top: 9px; }
.ur-stat-total .ur-stat-k { padding-left: 17px; }

.ur-budget-edit { margin-top: 6px; padding-top: 12px; border-top: 1px solid #f1f5f9; }
.ur-budget-edit > label { font-size: 12px; color: #64748b; display: block; margin-bottom: 6px; }
.ur-budget-row { display: flex; gap: 8px; }
.ur-input { flex: 1; min-width: 0; border: 1px solid #cbd5e1; border-radius: 9px; padding: 7px 10px; font-size: 13px; color: #0f172a; box-sizing: border-box; background: #fff; font-variant-numeric: tabular-nums; }
.ur-input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.1); }
.ur-save { display: inline-flex; align-items: center; gap: 5px; background: #2563eb; color: #fff; border: 0; border-radius: 9px; padding: 7px 14px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.ur-save:hover { background: #1d4ed8; }
.ur-save:disabled { opacity: .6; cursor: not-allowed; }
.ur-presets { display: flex; gap: 6px; margin-top: 8px; }
.ur-presets button { flex: 1; border: 1px solid #e2e8f0; background: #fff; color: #64748b; border-radius: 7px; padding: 5px 0; font-size: 11.5px; cursor: pointer; }
.ur-presets button:hover { border-color: #2563eb; color: #1d4ed8; background: #eff6ff; }

/* Donut */
.ur-donut-body { display: flex; gap: 20px; align-items: center; }
.ur-donut { position: relative; width: 140px; height: 140px; flex-shrink: 0; }
.ur-donut-svg { width: 140px; height: 140px; }
.ur-donut-track { fill: none; stroke: #f1f5f9; stroke-width: 18; }
.ur-donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.ur-donut-total { font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -.02em; }
.ur-donut-cap { font-size: 11px; color: #94a3b8; }
.ur-legend { flex: 1; list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 11px; min-width: 0; }
.ur-legend li { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.ur-legend-label { color: #334155; }
.ur-legend-pct { margin-left: auto; font-weight: 700; color: #0f172a; }
.ur-legend-val { width: 74px; text-align: right; color: #94a3b8; font-size: 12px; font-variant-numeric: tabular-nums; }

/* Trend chart (AntV / G2Plot mount node) */
.ur-trend-tag { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: #64748b; background: #f1f5f9; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }
.ur-chart-mount { width: 100%; height: 280px; }

.ur-empty { padding: 26px; text-align: center; color: #94a3b8; font-size: 13px; }
.ur-empty-tall { padding: 70px 26px; }

@media (max-width: 1080px) {
  .ur-kpis { grid-template-columns: repeat(2, 1fr); }
  .ur-mid { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .ur-kpis { grid-template-columns: 1fr; }
  .ur-gauge-body, .ur-donut-body { flex-direction: column; align-items: stretch; }
  .ur-radial, .ur-donut { align-self: center; }
}
</style>
