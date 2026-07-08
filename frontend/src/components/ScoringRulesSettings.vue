<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Plus, RotateCcw, Save, Trash2 } from "lucide-vue-next";

interface ScoringWeight {
  key: string;
  label: string;
  percent: number;
}
interface ScoringRule {
  points: number;
  description: string;
}
interface ScoringThreshold {
  min: number;
  max: number;
  level: string; // strong | medium | weak | reject
  label: string;
}
interface ScoringRules {
  weights: ScoringWeight[];
  positive_rules: ScoringRule[];
  negative_rules: ScoringRule[];
  thresholds: ScoringThreshold[];
  updated_at: string;
}

const props = defineProps<{
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
}>();

const loading = ref(true);
const saving = ref(false);
const toast = ref<{ text: string; kind: "ok" | "err" } | null>(null);
const activeType = ref<"distributor" | "kol">("distributor");
const typeTabs: { value: "distributor" | "kol"; label: string }[] = [
  { value: "distributor", label: "代理商" },
  { value: "kol", label: "KOL" },
];
const rules = ref<ScoringRules>({
  weights: [],
  positive_rules: [],
  negative_rules: [],
  thresholds: [],
  updated_at: "",
});

const levelOptions = [
  { value: "strong", label: "强匹配" },
  { value: "medium", label: "中匹配" },
  { value: "weak", label: "弱匹配" },
  { value: "reject", label: "建议拒绝" },
];

// Global (not per-type): when on, strong-match leads skip the 待确认 queue and
// are auto-confirmed. Persisted via /settings, not the scoring-rules payload.
const autoConfirmStrong = ref(false);
async function loadAutoConfirm(): Promise<void> {
  try {
    const s = await props.request<{ auto_confirm_strong?: boolean }>("/settings");
    autoConfirmStrong.value = !!s.auto_confirm_strong;
  } catch {
    /* settings.manage may be absent; leave default */
  }
}
async function toggleAutoConfirm(): Promise<void> {
  const next = !autoConfirmStrong.value;
  autoConfirmStrong.value = next;
  try {
    await props.request("/settings", {
      method: "PUT",
      body: JSON.stringify({ auto_confirm_strong: next }),
    });
    flash(next ? "已开启：强匹配线索自动确认" : "已关闭：强匹配线索需人工确认");
  } catch (e) {
    autoConfirmStrong.value = !next;
    flash(errText(e), "err");
  }
}

const weightTotal = computed(() => rules.value.weights.reduce((sum, w) => sum + (w.percent || 0), 0));

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
function fmtTime(iso: string): string {
  if (!iso) return "从未修改（使用默认规则）";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `上次更新：${d.toLocaleString()}`;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    rules.value = await props.request<ScoringRules>(`/scoring/rules?lead_type=${activeType.value}`);
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    loading.value = false;
  }
}

function switchType(type: "distributor" | "kol"): void {
  if (type === activeType.value) return;
  activeType.value = type;
  void load();
}

async function save(): Promise<void> {
  if (rules.value.weights.some((w) => !w.key.trim() || !w.label.trim())) {
    flash("权重项的 key 和名称不能为空", "err");
    return;
  }
  if (rules.value.positive_rules.some((r) => !r.description.trim()) ||
      rules.value.negative_rules.some((r) => !r.description.trim())) {
    flash("加分/扣分项说明不能为空", "err");
    return;
  }
  saving.value = true;
  try {
    rules.value = await props.request<ScoringRules>(`/scoring/rules?lead_type=${activeType.value}`, {
      method: "PUT",
      body: JSON.stringify({
        weights: rules.value.weights,
        positive_rules: rules.value.positive_rules,
        negative_rules: rules.value.negative_rules,
        thresholds: rules.value.thresholds,
      }),
    });
    flash(`${activeType.value === "kol" ? "KOL" : "代理商"}评分规则已保存，Agent 下次打分时会读取新规则`);
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    saving.value = false;
  }
}

function addWeight(): void {
  rules.value.weights.push({ key: "", label: "", percent: 0 });
}
function removeWeight(index: number): void {
  rules.value.weights.splice(index, 1);
}
function addPositiveRule(): void {
  rules.value.positive_rules.push({ points: 5, description: "" });
}
function removePositiveRule(index: number): void {
  rules.value.positive_rules.splice(index, 1);
}
function addNegativeRule(): void {
  rules.value.negative_rules.push({ points: -5, description: "" });
}
function removeNegativeRule(index: number): void {
  rules.value.negative_rules.splice(index, 1);
}
function addThreshold(): void {
  rules.value.thresholds.push({ min: 0, max: 39, level: "reject", label: "" });
}
function removeThreshold(index: number): void {
  rules.value.thresholds.splice(index, 1);
}

onMounted(() => {
  void load();
  void loadAutoConfirm();
});
</script>

<template>
  <section class="sr-page">
    <div class="sr-head">
      <div>
        <p class="panel-label">Agent</p>
        <h2>线索评分规则</h2>
        <p class="sr-sub">
          决定 Agent 在渠道拓展调研中如何给候选线索打分（0–100 分）。保存后，Agent
          下次执行 <code>get_scoring_rules</code> 工具时会读到这里的最新配置，无需重启或改代码。
        </p>
      </div>
      <button class="btn-ghost" type="button" @click="load"><RotateCcw :size="14" /> 刷新</button>
    </div>

    <div class="sr-type-tabs" role="tablist" aria-label="线索分类">
      <button
        v-for="tab in typeTabs"
        :key="tab.value"
        type="button"
        role="tab"
        :aria-selected="activeType === tab.value"
        :class="['sr-type-tab', { active: activeType === tab.value }]"
        @click="switchType(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>
    <p class="sr-type-hint">
      代理商和 KOL 各自独立配置一套评分规则，互不影响；Agent 调 <code>get_scoring_rules</code>
      时会按线索的 <code>lead_type</code> 取对应的一套。
    </p>

    <transition name="sr-fade">
      <div v-if="toast" :class="['sr-toast', toast.kind]">{{ toast.text }}</div>
    </transition>

    <div v-if="loading" class="sr-loading">加载中…</div>

    <template v-else>
      <p class="sr-updated">{{ fmtTime(rules.updated_at) }}</p>

      <!-- Weights -->
      <section class="sr-card">
        <div class="sr-card-head">
          <div>
            <strong>评分权重</strong>
            <p>用于人工理解各维度重要性；总和建议为 100%（当前 {{ weightTotal }}%）。</p>
          </div>
          <span v-if="weightTotal !== 100" class="sr-warn-tag">总和 ≠ 100%</span>
        </div>
        <div class="sr-rows">
          <div v-for="(w, i) in rules.weights" :key="i" class="sr-row sr-row-weight">
            <input v-model="w.key" placeholder="key（如 channel_fit）" class="sr-input sr-input-key" />
            <input v-model="w.label" placeholder="名称（如 渠道匹配度）" class="sr-input sr-input-label" />
            <div class="sr-input-suffix">
              <input v-model.number="w.percent" type="number" min="0" max="100" class="sr-input sr-input-num" />
              <span>%</span>
            </div>
            <button type="button" class="sr-remove" title="删除" @click="removeWeight(i)"><Trash2 :size="14" /></button>
          </div>
        </div>
        <button type="button" class="sr-add" @click="addWeight"><Plus :size="14" /> 新增权重项</button>
      </section>

      <!-- Positive rules -->
      <section class="sr-card">
        <div class="sr-card-head">
          <div><strong>加分项</strong><p>候选线索满足条件时加分，从 0 分起累加。</p></div>
        </div>
        <div class="sr-rows">
          <div v-for="(r, i) in rules.positive_rules" :key="i" class="sr-row sr-row-rule">
            <div class="sr-input-suffix sr-input-suffix-points">
              <span>+</span>
              <input v-model.number="r.points" type="number" min="0" max="100" class="sr-input sr-input-num" />
            </div>
            <input v-model="r.description" placeholder="满足条件说明" class="sr-input sr-input-desc" />
            <button type="button" class="sr-remove" title="删除" @click="removePositiveRule(i)"><Trash2 :size="14" /></button>
          </div>
        </div>
        <button type="button" class="sr-add" @click="addPositiveRule"><Plus :size="14" /> 新增加分项</button>
      </section>

      <!-- Negative rules -->
      <section class="sr-card">
        <div class="sr-card-head">
          <div><strong>扣分项</strong><p>候选线索存在问题时扣分。</p></div>
        </div>
        <div class="sr-rows">
          <div v-for="(r, i) in rules.negative_rules" :key="i" class="sr-row sr-row-rule">
            <div class="sr-input-suffix sr-input-suffix-points sr-input-suffix-negative">
              <span>−</span>
              <input
                :value="Math.abs(r.points)"
                @input="r.points = -Math.abs(Number(($event.target as HTMLInputElement).value) || 0)"
                type="number"
                min="0"
                max="100"
                class="sr-input sr-input-num"
              />
            </div>
            <input v-model="r.description" placeholder="扣分条件说明" class="sr-input sr-input-desc" />
            <button type="button" class="sr-remove" title="删除" @click="removeNegativeRule(i)"><Trash2 :size="14" /></button>
          </div>
        </div>
        <button type="button" class="sr-add" @click="addNegativeRule"><Plus :size="14" /> 新增扣分项</button>
      </section>

      <!-- Thresholds -->
      <section class="sr-card">
        <div class="sr-card-head">
          <div>
            <strong>分数区间 → 匹配度</strong>
            <p>
              分数决定线索的「匹配度」徽章（强/中/弱）。除「建议拒绝」区间会直接置为「已拒绝」外，
              其余线索统一进入「待确认」队列，由人工确认——分数只影响匹配度徽章，不再直接决定流程状态。
            </p>
          </div>
        </div>
        <div class="sr-rows">
          <div v-for="(t, i) in rules.thresholds" :key="i" class="sr-row sr-row-threshold">
            <input v-model.number="t.min" type="number" min="0" max="100" class="sr-input sr-input-num" />
            <span class="sr-range-sep">–</span>
            <input v-model.number="t.max" type="number" min="0" max="100" class="sr-input sr-input-num" />
            <select v-model="t.level" class="sr-input sr-input-select">
              <option v-for="opt in levelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
            <input v-model="t.label" placeholder="展示名称（如 强匹配）" class="sr-input sr-input-label" />
            <button type="button" class="sr-remove" title="删除" @click="removeThreshold(i)"><Trash2 :size="14" /></button>
          </div>
        </div>
        <button type="button" class="sr-add" @click="addThreshold"><Plus :size="14" /> 新增区间</button>

        <label class="sr-autoconfirm">
          <input type="checkbox" :checked="autoConfirmStrong" @change="toggleAutoConfirm" />
          <span>
            <strong>强匹配自动确认</strong>
            <em>开启后，「强匹配」线索跳过「待确认」直接置为「已确认」；关闭则一律先人工确认。（全局设置，对代理商与 KOL 同时生效）</em>
          </span>
        </label>
      </section>

      <div class="sr-save-bar">
        <button type="button" class="sr-save-btn" :disabled="saving" @click="save">
          <Save :size="15" /> {{ saving ? "保存中..." : "保存规则" }}
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.sr-page { display: flex; flex-direction: column; gap: 16px; max-width: 780px; }
.sr-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.panel-label { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #64748b; margin: 0 0 4px; }
.sr-head h2 { margin: 0; font-size: 18px; color: #0f172a; }
.sr-sub { color: #64748b; font-size: 13px; margin: 6px 0 0; max-width: 560px; line-height: 1.6; }
.sr-sub code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
.btn-ghost { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; color: #475569; flex-shrink: 0; }
.btn-ghost:hover { background: #f8fafc; }

.sr-toast { position: fixed; top: 22px; left: 50%; transform: translateX(-50%); z-index: 1200; padding: 10px 18px; border-radius: 10px; font-size: 13px; font-weight: 700; box-shadow: 0 12px 28px rgba(15,23,42,.12); }
.sr-toast.ok { background: #ecfdf5; color: #047857; }
.sr-toast.err { background: #fef2f2; color: #b91c1c; }
.sr-fade-enter-active, .sr-fade-leave-active { transition: opacity 200ms ease; }
.sr-fade-enter-from, .sr-fade-leave-to { opacity: 0; }

.sr-type-tabs { display: flex; gap: 6px; }
.sr-type-tab {
  border: 1px solid #e2e8f0; background: #fff; color: #64748b;
  border-radius: 999px; padding: 6px 16px; font-size: 13px; font-weight: 700; cursor: pointer;
}
.sr-type-tab:hover { border-color: #cbd5e1; color: #0f172a; }
.sr-type-tab.active { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.sr-type-hint { margin: -6px 0 0; font-size: 12px; color: #94a3b8; line-height: 1.6; }
.sr-type-hint code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }

.sr-loading { padding: 40px; text-align: center; color: #94a3b8; }
.sr-updated { margin: -6px 0 0; font-size: 12px; color: #94a3b8; }

.sr-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.sr-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.sr-card-head strong { font-size: 14px; color: #0f172a; }
.sr-card-head p { margin: 3px 0 0; font-size: 12.5px; color: #64748b; }
.sr-warn-tag { font-size: 11px; font-weight: 700; color: #b45309; background: #fff7ed; padding: 3px 9px; border-radius: 999px; white-space: nowrap; }

.sr-rows { display: flex; flex-direction: column; gap: 8px; }
.sr-row { display: flex; align-items: center; gap: 8px; }
.sr-input {
  border: 1px solid #cbd5e1; border-radius: 8px; padding: 7px 10px; font-size: 13px;
  color: #0f172a; box-sizing: border-box; background: #fff;
}
.sr-input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.1); }
.sr-input-key { width: 160px; flex-shrink: 0; }
.sr-input-label { flex: 1; min-width: 120px; }
.sr-input-desc { flex: 1; min-width: 160px; }
.sr-input-num { width: 60px; text-align: right; }
.sr-input-select { width: 190px; flex-shrink: 0; cursor: pointer; }
.sr-input-suffix { display: flex; align-items: center; gap: 4px; flex-shrink: 0; color: #64748b; font-size: 13px; font-weight: 700; }
.sr-input-suffix-points { width: 76px; }
.sr-input-suffix-points span { width: 12px; text-align: center; }
.sr-input-suffix-negative span { color: #b91c1c; }
.sr-range-sep { color: #94a3b8; flex-shrink: 0; }

.sr-remove {
  width: 30px; height: 30px; flex-shrink: 0; display: grid; place-items: center;
  border: 1px solid #e2e8f0; background: #fff; border-radius: 8px; cursor: pointer; color: #94a3b8;
}
.sr-remove:hover { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }

.sr-add {
  align-self: flex-start; display: inline-flex; align-items: center; gap: 6px;
  border: 1px dashed #cbd5e1; background: #fff; color: #2563eb;
  border-radius: 8px; padding: 6px 12px; font-size: 12.5px; cursor: pointer;
}
.sr-add:hover { background: #eff6ff; border-color: #2563eb; }

.sr-autoconfirm { display: flex; align-items: flex-start; gap: 10px; margin-top: 4px; padding: 12px 14px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; cursor: pointer; }
.sr-autoconfirm input { margin-top: 2px; width: 16px; height: 16px; flex-shrink: 0; cursor: pointer; }
.sr-autoconfirm strong { font-size: 13px; color: #0f172a; display: block; }
.sr-autoconfirm em { font-style: normal; font-size: 12px; color: #64748b; line-height: 1.6; display: block; margin-top: 2px; }

.sr-save-bar { display: flex; justify-content: flex-end; }
.sr-save-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: #2563eb; color: #fff; border: 0; border-radius: 9px;
  padding: 10px 20px; font-size: 14px; font-weight: 700; cursor: pointer;
}
.sr-save-btn:hover { background: #1d4ed8; }
.sr-save-btn:disabled { opacity: .6; cursor: not-allowed; }

@media (max-width: 640px) {
  .sr-row { flex-wrap: wrap; }
  .sr-input-key, .sr-input-label, .sr-input-desc { width: 100%; }
}
</style>
