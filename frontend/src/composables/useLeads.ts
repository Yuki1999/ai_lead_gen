/**
 * Leads / workspace state and CRUD operations.
 *
 * All refs are module-level for direct function access.
 */
import { computed, ref } from "vue";
import { request } from "@/api";
import { notice, error, setNotice } from "@/composables/useNotifications";
import { loading, currentAction, runAction } from "@/composables/useActionState";
import { hasPermission } from "@/composables/useAuth";

// ── Interfaces ────────────────────────────────────────

export interface Lead {
  id: number;
  company_name: string;
  region: string;
  country: string;
  website: string;
  contact_name: string;
  email: string;
  category: string;
  match_reason: string;
  source: string;
  score: number;
  status: string;
  notes: string;
  reply_count?: number;
  draft_count?: number;
}

export interface Metrics {
  total_leads: number;
  interested_leads: number;
  sent_emails: number;
  human_review: number;
}

export interface SearchResponse {
  created_count: number;
  leads: Lead[];
}

export interface LeadListResponse {
  total: number;
  leads: Lead[];
}

export interface EmailEvent {
  id: number;
  lead_id: number;
  company_name?: string;
  lead_email?: string;
  country?: string;
  subject: string;
  body: string;
  sent_to: string;
  region: string;
  status: string;
  message_id: string;
  source: string;
  created_at: string;
}

export interface DraftListResponse {
  total: number;
  drafts: EmailEvent[];
}

export interface SendResponse {
  sent_count: number;
  events: EmailEvent[];
}

export interface ReplyAnalysis {
  id?: number;
  lead_id?: number | null;
  reply_text?: string;
  intent: string;
  confidence: number;
  summary: string;
  next_action: string;
  requires_human: boolean;
  message_id?: string;
  created_at?: string;
}

export interface ProductProfile {
  search_keywords: string[];
  value_points: string[];
  source_files: string[];
  video_assets: string[];
}

export interface SourcePreview {
  url: string;
  title: string;
  text: string;
  email: string;
  emails: string[];
  email_found: boolean;
}

export interface HighlightChunk {
  text: string;
  highlight: boolean;
}

// ── Leads state ───────────────────────────────────────

export const leads = ref<Lead[]>([]);
export const productProfile = ref<ProductProfile | null>(null);
export const metrics = ref<Metrics>({
  total_leads: 0,
  interested_leads: 0,
  sent_emails: 0,
  human_review: 0,
});
export const selectedLeadIds = ref<number[]>([]);
export const targetRegions = ref(
  "Germany, United Arab Emirates, Singapore, Saudi Arabia",
);
export const productKeywords = ref(
  "orthopedic implant distributor, total knee arthroplasty distributor, joint replacement distributor",
);
export const maxResults = ref(5);
export const requireEmail = ref(true);
export const filterRegion = ref("");
export const filterStatus = ref("");
export const query = ref("");
export const sortField = ref("id");
export const sortDir = ref<"asc" | "desc">("desc");
export const replyText = ref("");
export const lastEmail = ref<EmailEvent | null>(null);
export const analysis = ref<ReplyAnalysis | null>(null);
export const sourcePreview = ref<SourcePreview | null>(null);
export const sourcePreviewLead = ref<Lead | null>(null);
export const sourcePreviewLoading = ref(false);
export const sourcePreviewError = ref("");
export const sourcePreviewMode = ref<"page" | "text">("page");

// Pagination
export const leadPage = ref(1);
export const leadPageSize = ref(20);
export const leadTotal = ref(0);

// Custom email
export const showCustomEmail = ref(false);
export const customEmail = ref({
  lead_id: 0,
  company_name: "",
  email: "",
  subject: "",
  body: "",
});
export const customEmailSending = ref(false);
export const availableAttachments = ref<string[]>([]);
export const customEmailAttachments = ref<string[]>([]);

// Edit lead
export const showEditLead = ref(false);
export const editLead = ref({
  id: 0,
  company_name: "",
  region: "",
  country: "",
  website: "",
  contact_name: "",
  email: "",
  category: "",
  match_reason: "",
  source: "",
  score: 50,
  status: "",
  notes: "",
});
export const editLeadSaving = ref(false);

// Lead detail panel
export const detailLeadId = ref<number | null>(null);
export const detailStatus = ref("");
export const detailNotes = ref("");
export const detailOutreach = ref<EmailEvent[]>([]);
export const detailReplies = ref<ReplyAnalysis[]>([]);
export const detailLoading = ref(false);

// Outreach preview
export const showOutreachPreview = ref(false);
export const outreachLoading = ref(false);
export const outreachPreviews = ref<
  Array<{
    lead_id: number;
    company_name: string;
    email: string;
    subject: string;
    body: string;
  }>
>([]);

// Reply analyzer (used in lead detail)
export const showReplyAnalyzer = ref(false);

// ── Computed ──────────────────────────────────────────

export const selectedCount = computed(() => selectedLeadIds.value.length);

export const detailLead = computed(() =>
  leads.value.find((l) => l.id === detailLeadId.value) || null,
);

export interface TimelineEvent {
  kind: "outreach" | "reply";
  id: number;
  subject: string;
  intent?: string;
  status?: string;
  message_id?: string;
  created_at: string;
}

export const timelineEvents = computed<TimelineEvent[]>(() => {
  const items: TimelineEvent[] = [];
  for (const ev of detailOutreach.value) {
    items.push({
      kind: "outreach",
      id: ev.id,
      subject: ev.subject,
      status: ev.status,
      message_id: ev.message_id,
      created_at: ev.created_at,
    });
  }
  for (const r of detailReplies.value) {
    items.push({
      kind: "reply",
      id: r.id || 0,
      subject: r.summary || "",
      intent: r.intent,
      message_id: r.message_id,
      created_at: r.created_at || "",
    });
  }
  items.sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  return items;
});

// ── Helper functions ──────────────────────────────────

export function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildHighlightedChunks(
  text: string,
  email: string,
): HighlightChunk[] {
  if (!email) return [{ text, highlight: false }];
  const escaped = escapeRegex(email);
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));
  return parts.map((part) => ({
    text: part,
    highlight: part.toLowerCase() === email.toLowerCase(),
  }));
}

export const highlightedSourceText = computed(() =>
  buildHighlightedChunks(
    sourcePreview.value?.text || "",
    sourcePreview.value?.email || sourcePreviewLead.value?.email || "",
  ),
);

export const highlightedEvidenceExcerpt = computed(() => {
  const chunks = highlightedSourceText.value;
  const idx = chunks.findIndex((c) => c.highlight);
  if (idx < 0) return chunks;
  const start = Math.max(0, idx - 2);
  const end = Math.min(chunks.length, idx + 3);
  return chunks.slice(start, end);
});

export const sourceHost = computed(() => {
  try {
    const url = sourcePreviewLead.value?.source || "";
    return new URL(url).hostname;
  } catch {
    return "";
  }
});

export function formatStatus(status: string): string {
  const map: Record<string, string> = {
    new: "新线索",
    emailed: "已邮件",
    interested: "有兴趣",
    human_review: "转人工",
    qualified: "已确认",
    rejected: "拒绝",
    needs_review: "待审核",
  };
  return map[status] || status;
}

export function statusClass(status: string): string {
  if (["interested", "qualified"].includes(status)) return "status-positive";
  if (["human_review", "needs_review"].includes(status))
    return "status-warning";
  if (status === "rejected") return "status-negative";
  if (status === "emailed") return "status-info";
  return "";
}

export function statusTagType(
  status: string,
): "default" | "info" | "success" | "warning" | "error" {
  if (["interested", "qualified"].includes(status)) return "success";
  if (["human_review", "needs_review"].includes(status)) return "warning";
  if (status === "rejected") return "error";
  if (status === "emailed") return "info";
  return "default";
}

// ── Dashboard / Leads CRUD ────────────────────────────

export async function loadDashboard(resetPage = true): Promise<void> {
  if (resetPage) leadPage.value = 1;
  const params = new URLSearchParams();
  if (filterRegion.value) params.set("region", filterRegion.value);
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (query.value) params.set("q", query.value);
  params.set("sort", sortField.value);
  params.set("order", sortDir.value);
  params.set("limit", String(leadPageSize.value));
  params.set("offset", String((leadPage.value - 1) * leadPageSize.value));

  const [listResp, metricsResp] = await Promise.all([
    request<LeadListResponse>(`/leads?${params.toString()}`),
    request<Metrics>("/metrics"),
  ]);
  leads.value = listResp.leads;
  leadTotal.value = listResp.total;
  metrics.value = metricsResp;
}

export async function loadDrafts(): Promise<void> {
  try {
    const resp = await request<DraftListResponse>("/campaigns/drafts");
    const { setDrafts } = await import("@/composables/useSettings");
    setDrafts(resp.drafts, resp.total);
  } catch {
    // silently ignore
  }
}

export async function approveDraft(eventId: number): Promise<void> {
  await runAction("outreach", async () => {
    await request(`/campaigns/drafts/${eventId}/approve`, { method: "POST" });
    setNotice("已发送");
    await loadDashboard();
    await loadDrafts();
  });
}

export async function rejectDraft(eventId: number): Promise<void> {
  await runAction("outreach", async () => {
    await request(`/campaigns/drafts/${eventId}/reject`, { method: "POST" });
    setNotice("已拒绝");
    await loadDrafts();
  });
}

export function openCreateLead(): void {
  import("@/composables/useSettings").then((m) => {
    m.newLead.value = {
      company_name: "",
      region: "",
      country: "",
      website: "",
      contact_name: "",
      email: "",
      category: "medical device distributor",
    };
    m.createError.value = "";
    m.showCreateLead.value = true;
  });
}

export async function createLead(): Promise<void> {
  const { newLead, createError, showCreateLead } = await import(
    "@/composables/useSettings"
  );
  if (!newLead.value.company_name.trim()) {
    createError.value = "公司名称为必填项";
    return;
  }
  await runAction("search", async () => {
    await request("/leads", {
      method: "POST",
      body: JSON.stringify(newLead.value),
    });
    showCreateLead.value = false;
    setNotice("已创建新线索");
    await loadDashboard();
  });
}

export async function batchDeleteLeads(): Promise<void> {
  if (selectedLeadIds.value.length === 0) return;
  const ids = [...selectedLeadIds.value];
  await runAction("dashboard", async () => {
    await request("/leads/batch-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    selectedLeadIds.value = [];
    setNotice(`已删除 ${ids.length} 条线索`);
    await loadDashboard();
  });
}

export async function deleteLead(leadId: number): Promise<void> {
  await runAction("dashboard", async () => {
    await request(`/leads/${leadId}`, { method: "DELETE" });
    setNotice("已删除线索");
    await loadDashboard();
  });
}

export async function approveAllDrafts(): Promise<void> {
  await runAction("outreach", async () => {
    const resp = await request<{ sent_count: number }>(
      "/campaigns/drafts/approve-all",
      { method: "POST" },
    );
    setNotice(`已批量发送 ${resp.sent_count} 封邮件`);
    await loadDashboard();
    await loadDrafts();
  });
}

export async function loadProductProfile(): Promise<void> {
  productProfile.value = await request<ProductProfile>("/product/profile");
}

export async function generateLeads(): Promise<void> {
  await runAction("search", async () => {
    const payload = await request<SearchResponse>("/leads/search", {
      method: "POST",
      body: JSON.stringify({
        target_regions: splitCsv(targetRegions.value),
        product_keywords: splitCsv(productKeywords.value),
        max_results: maxResults.value,
        real_search: true,
        require_email: requireEmail.value,
      }),
    });
    selectedLeadIds.value = payload.leads.map((lead) => lead.id);
    setNotice(
      payload.created_count > 0
        ? `新增 ${payload.created_count} 条真实网页线索`
        : "本轮未发现符合条件的公开邮箱线索",
    );
    await loadDashboard();
  });
}

export async function createOutreachRecords(): Promise<void> {
  if (selectedLeadIds.value.length === 0) return;
  await runAction("outreach", async () => {
    const payload = await request<SendResponse>("/campaigns/outreach-records", {
      method: "POST",
      body: JSON.stringify({ lead_ids: selectedLeadIds.value }),
    });
    lastEmail.value =
      payload.events[payload.events.length - 1] || null;
    setNotice(`已生成 ${payload.sent_count} 条触达记录`);
    await loadDashboard();
  });
}

export async function syncReplies(): Promise<void> {
  await runAction("sync", async () => {
    const payload = await request<{
      total_inbox: number;
      synced: number;
      skipped: number;
      items: Array<{
        lead_id: number;
        company: string;
        intent: string;
        auto_reply: boolean;
      }>;
    }>("/replies/sync", { method: "POST" });
    if (payload.synced > 0) {
      const companies = [...new Set(payload.items.map((i) => i.company))].join(
        "、",
      );
      setNotice(
        `同步了 ${payload.synced} 条回复（${companies}），跳过 ${payload.skipped} 条`,
      );
    } else {
      setNotice(`未发现新回复（扫描 ${payload.total_inbox} 封邮件）`);
    }
    await loadDashboard();
  });
}

export async function analyzeCurrentReply(): Promise<void> {
  await runAction("reply", async () => {
    analysis.value = await request<ReplyAnalysis>("/replies/analyze", {
      method: "POST",
      body: JSON.stringify({
        lead_id: detailLeadId.value || null,
        reply_text: replyText.value,
      }),
    });
    showReplyAnalyzer.value = true;
    await loadDashboard();
  });
}

export async function generateFollowupAndOpen(): Promise<void> {
  if (!detailLeadId.value || !replyText.value.trim()) return;
  await runAction("followup", async () => {
    const result = await request<{
      subject: string;
      body: string;
      sent_to: string;
    }>("/replies/followup", {
      method: "POST",
      body: JSON.stringify({
        lead_id: detailLeadId.value,
        reply_text: replyText.value,
      }),
    });
    const lead = leads.value.find((l) => l.id === detailLeadId.value);
    if (lead) {
      customEmail.value = {
        lead_id: lead.id,
        company_name: lead.company_name,
        email: lead.email,
        subject: result.subject,
        body: result.body,
      };
      showCustomEmail.value = true;
    }
  });
}

// ── Outreach ──────────────────────────────────────────

export async function sendOutreachSingle(leadId: number): Promise<void> {
  await fetchOutreachPreview([leadId]);
}

export async function sendOutreachBatch(): Promise<void> {
  await fetchOutreachPreview(selectedLeadIds.value);
}

export async function fetchOutreachPreview(
  leadIds: number[],
): Promise<void> {
  if (leadIds.length === 0) return;
  outreachLoading.value = true;
  try {
    outreachPreviews.value = await request<typeof outreachPreviews.value>(
      "/campaigns/outreach-preview",
      {
        method: "POST",
        body: JSON.stringify({ lead_ids: leadIds }),
      },
    );
    showOutreachPreview.value = true;
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : "生成邮件预览失败";
  } finally {
    outreachLoading.value = false;
  }
}

export async function confirmSendOutreach(): Promise<void> {
  if (outreachPreviews.value.length === 0) return;
  await runAction("outreach", async () => {
    const resp = await request<SendResponse>("/campaigns/outreach-records", {
      method: "POST",
      body: JSON.stringify({
        lead_ids: outreachPreviews.value.map((p) => p.lead_id),
        customizations: outreachPreviews.value.map((p) => ({
          lead_id: p.lead_id,
          subject: p.subject,
          body: p.body,
        })),
      }),
    });
    showOutreachPreview.value = false;
    lastEmail.value = resp.events[resp.events.length - 1] || null;
    setNotice(`已发送 ${resp.sent_count} 封邮件`);
    await loadDashboard();
  });
}

export async function openCustomEmail(leadId: number): Promise<void> {
  const lead = leads.value.find((l) => l.id === leadId);
  if (!lead) return;
  try {
    availableAttachments.value = await request<string[]>("/attachments");
  } catch {
    availableAttachments.value = [];
  }
  customEmail.value = {
    lead_id: lead.id,
    company_name: lead.company_name,
    email: lead.email,
    subject: "",
    body: "",
  };
  customEmailAttachments.value = [];
  showCustomEmail.value = true;
}

export async function sendCustomEmail(): Promise<void> {
  if (customEmailSending.value) return;
  customEmailSending.value = true;
  try {
    await request("/campaigns/custom-send", {
      method: "POST",
      body: JSON.stringify({
        lead_id: customEmail.value.lead_id,
        subject: customEmail.value.subject,
        body: customEmail.value.body,
        attachments: customEmailAttachments.value,
      }),
    });
    showCustomEmail.value = false;
    setNotice("邮件已发送");
    await loadDashboard();
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : "发送失败";
  } finally {
    customEmailSending.value = false;
  }
}

// ── Reply analyzer ────────────────────────────────────

export function openReplyAnalyzer(replyTextContent?: string): void {
  replyText.value = replyTextContent || "";
  showReplyAnalyzer.value = true;
}

export async function reactivateLead(leadId: number): Promise<void> {
  await request(`/leads/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "new" }),
  });
  setNotice("已重新激活");
  await loadDashboard();
}

export async function markQualified(leadId: number): Promise<void> {
  await request(`/leads/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "qualified" }),
  });
  setNotice("已标记为确认合格");
  await loadDashboard();
}

// ── Lead detail ───────────────────────────────────────

export async function openLeadDetail(leadId: number): Promise<void> {
  detailLeadId.value = leadId;
  detailLoading.value = true;
  try {
    const history = await request<{
      outreach: EmailEvent[];
      replies: ReplyAnalysis[];
    }>(`/leads/${leadId}/history`);
    detailOutreach.value = history.outreach;
    detailReplies.value = history.replies;
    const lead = leads.value.find((l) => l.id === leadId);
    if (lead) {
      detailStatus.value = lead.status;
      detailNotes.value = lead.notes || "";
    }
  } catch {
    // silently ignore
  } finally {
    detailLoading.value = false;
  }
}

export function closeLeadDetail(): void {
  detailLeadId.value = null;
  detailOutreach.value = [];
  detailReplies.value = [];
  detailStatus.value = "";
  detailNotes.value = "";
}

export async function saveLeadDetail(): Promise<void> {
  if (detailLeadId.value === null) return;
  await request(`/leads/${detailLeadId.value}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: detailStatus.value,
      notes: detailNotes.value,
    }),
  });
  setNotice("线索已更新");
  await loadDashboard();
}

// ── Edit lead ─────────────────────────────────────────

export async function openEditLead(leadId: number): Promise<void> {
  const lead = await request<Lead>(`/leads/${leadId}`);
  editLead.value = {
    id: lead.id,
    company_name: lead.company_name,
    region: lead.region,
    country: lead.country,
    website: lead.website,
    contact_name: lead.contact_name,
    email: lead.email,
    category: lead.category,
    match_reason: lead.match_reason,
    source: lead.source,
    score: lead.score,
    status: lead.status,
    notes: lead.notes || "",
  };
  showEditLead.value = true;
}

export async function saveEditLead(): Promise<void> {
  if (editLeadSaving.value) return;
  editLeadSaving.value = true;
  try {
    await request(`/leads/${editLead.value.id}`, {
      method: "PATCH",
      body: JSON.stringify(editLead.value),
    });
    showEditLead.value = false;
    setNotice("线索已更新");
    await loadDashboard();
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : "保存失败";
  } finally {
    editLeadSaving.value = false;
  }
}

// ── Source preview ────────────────────────────────────

export async function openSourcePreview(lead: Lead): Promise<void> {
  sourcePreviewLead.value = lead;
  sourcePreviewLoading.value = true;
  sourcePreviewError.value = "";
  try {
    sourcePreview.value = await request<SourcePreview>("/sources/preview", {
      method: "POST",
      body: JSON.stringify({ url: lead.source, email: lead.email }),
    });
  } catch (caught) {
    sourcePreviewError.value =
      caught instanceof Error ? caught.message : "页面抓取失败";
  } finally {
    sourcePreviewLoading.value = false;
  }
}

export function closeSourcePreview(): void {
  sourcePreview.value = null;
  sourcePreviewLead.value = null;
  sourcePreviewLoading.value = false;
  sourcePreviewError.value = "";
  sourcePreviewMode.value = "page";
}

// ── Selection / pagination / sort ─────────────────────

export function toggleLead(leadId: number): void {
  const idx = selectedLeadIds.value.indexOf(leadId);
  if (idx >= 0) {
    selectedLeadIds.value = selectedLeadIds.value.filter((id) => id !== leadId);
  } else {
    selectedLeadIds.value = [...selectedLeadIds.value, leadId];
  }
}

export function toggleSelectAll(checked: boolean): void {
  selectedLeadIds.value = checked ? leads.value.map((l) => l.id) : [];
}

export function toggleSort(field: string): void {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortField.value = field;
    sortDir.value = "desc";
  }
  loadDashboard();
}

export function onLeadPageChange(page: number): void {
  leadPage.value = page;
  loadDashboard(false);
}

export function setLeadSelection(leadId: number, checked: boolean): void {
  if (checked) {
    if (!selectedLeadIds.value.includes(leadId)) {
      selectedLeadIds.value = [...selectedLeadIds.value, leadId];
    }
  } else {
    selectedLeadIds.value = selectedLeadIds.value.filter((id) => id !== leadId);
  }
}

// ── Aggregator ────────────────────────────────────────

export function useLeads() {
  return {
    // State
    leads,
    productProfile,
    metrics,
    selectedLeadIds,
    targetRegions,
    productKeywords,
    maxResults,
    requireEmail,
    filterRegion,
    filterStatus,
    query,
    sortField,
    sortDir,
    replyText,
    lastEmail,
    analysis,
    sourcePreview,
    sourcePreviewLead,
    sourcePreviewLoading,
    sourcePreviewError,
    sourcePreviewMode,
    leadPage,
    leadPageSize,
    leadTotal,
    showCustomEmail,
    customEmail,
    customEmailSending,
    availableAttachments,
    customEmailAttachments,
    showEditLead,
    editLead,
    editLeadSaving,
    detailLeadId,
    detailStatus,
    detailNotes,
    detailOutreach,
    detailReplies,
    detailLoading,
    showOutreachPreview,
    outreachLoading,
    outreachPreviews,
    showReplyAnalyzer,
    // Computed
    selectedCount,
    detailLead,
    timelineEvents,
    highlightedSourceText,
    highlightedEvidenceExcerpt,
    sourceHost,
    // Helpers
    splitCsv,
    escapeRegex,
    buildHighlightedChunks,
    formatStatus,
    statusClass,
    statusTagType,
    // Functions
    loadDashboard,
    loadDrafts,
    approveDraft,
    rejectDraft,
    openCreateLead,
    createLead,
    batchDeleteLeads,
    deleteLead,
    approveAllDrafts,
    loadProductProfile,
    generateLeads,
    createOutreachRecords,
    syncReplies,
    analyzeCurrentReply,
    generateFollowupAndOpen,
    sendOutreachSingle,
    sendOutreachBatch,
    fetchOutreachPreview,
    confirmSendOutreach,
    openCustomEmail,
    sendCustomEmail,
    openReplyAnalyzer,
    reactivateLead,
    markQualified,
    openLeadDetail,
    closeLeadDetail,
    saveLeadDetail,
    openEditLead,
    saveEditLead,
    openSourcePreview,
    closeSourcePreview,
    toggleLead,
    toggleSelectAll,
    toggleSort,
    onLeadPageChange,
    setLeadSelection,
  };
}
