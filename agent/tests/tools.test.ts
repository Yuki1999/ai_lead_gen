import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type {
  AnalyzeReplyInput,
  BackendClient,
  CreateOutreachRecordsInput,
  FetchUrlInput,
  ListLeadsInput,
  SearchLeadsInput,
  WebSearchInput,
} from "../src/backendClient.js";
import { createBusinessTools } from "../src/tools.js";

type MockClient = Pick<
  BackendClient,
  | "getProductProfile"
  | "webSearch"
  | "fetchUrl"
  | "searchLeads"
  | "listLeads"
  | "createOutreachRecords"
  | "analyzeReply"
>;

describe("createBusinessTools", () => {
  it("returns the business tool names in order", () => {
    const tools = createBusinessTools(mockClient());

    assert.deepEqual(
      tools.map((tool) => tool.name),
      [
        "get_product_profile",
        "web_search",
        "fetch_url",
        "search_leads",
        "list_leads",
        "create_outreach_records",
        "analyze_reply",
      ],
    );
  });

  it("executes web_search through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | { input: WebSearchInput; options: { signal?: AbortSignal } | undefined }
      | undefined;
    const client = mockClient({
      webSearch: async (input, options) => {
        calledWith = { input, options };
        return { query: input.query, results: [{ url: "https://ortho.example" }] };
      },
    });
    const tool = getTool("web_search", client);

    const result = await tool.execute(
      "call-1",
      { query: "orthopedic implant distributor India", max_results: 3 },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: { query: "orthopedic implant distributor India", max_results: 3 },
      options: { signal },
    });
    assertToolResult(result, {
      query: "orthopedic implant distributor India",
      results: [{ url: "https://ortho.example" }],
    });
  });

  it("executes fetch_url through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | { input: FetchUrlInput; options: { signal?: AbortSignal } | undefined }
      | undefined;
    const client = mockClient({
      fetchUrl: async (input, options) => {
        calledWith = { input, options };
        return { title: "Contact Ortho", url: input.url };
      },
    });
    const tool = getTool("fetch_url", client);

    const result = await tool.execute(
      "call-1",
      { url: "https://ortho.example/contact", email: "sales@ortho.example" },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: {
        url: "https://ortho.example/contact",
        email: "sales@ortho.example",
      },
      options: { signal },
    });
    assertToolResult(result, {
      title: "Contact Ortho",
      url: "https://ortho.example/contact",
    });
  });

  it("executes search_leads through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | { input: SearchLeadsInput; options: { signal?: AbortSignal } | undefined }
      | undefined;
    const client = mockClient({
      searchLeads: async (input, options) => {
        calledWith = { input, options };
        return { created_count: 1, regions: input.target_regions };
      },
    });
    const tool = createBusinessTools(client).find(
      (candidate) => candidate.name === "search_leads",
    );
    assert.ok(tool);

    const result = await tool.execute(
      "call-1",
      {
        target_regions: ["India"],
        max_results: 5,
      },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: {
        target_regions: ["India"],
        max_results: 5,
      },
      options: { signal },
    });
    assertToolResult(result, {
      created_count: 1,
      regions: ["India"],
    });
  });

  it("executes get_product_profile through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith: { signal?: AbortSignal } | undefined;
    const client = mockClient({
      getProductProfile: async (options) => {
        calledWith = options;
        return { product_name: "SkyWalker" };
      },
    });
    const tool = getTool("get_product_profile", client);

    const result = await tool.execute(
      "call-1",
      {},
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, { signal });
    assertToolResult(result, { product_name: "SkyWalker" });
  });

  it("executes list_leads through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | { input: ListLeadsInput; options: { signal?: AbortSignal } | undefined }
      | undefined;
    const client = mockClient({
      listLeads: async (input, options) => {
        calledWith = { input: input ?? {}, options };
        return { total: 1, leads: [{ id: 7 }] };
      },
    });
    const tool = getTool("list_leads", client);

    const result = await tool.execute(
      "call-1",
      { region: "India", status: "new", q: "robotics" },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: { region: "India", status: "new", q: "robotics" },
      options: { signal },
    });
    assertToolResult(result, { total: 1, leads: [{ id: 7 }] });
  });

  it("executes create_outreach_records through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | {
          input: CreateOutreachRecordsInput;
          options: { signal?: AbortSignal } | undefined;
        }
      | undefined;
    const client = mockClient({
      createOutreachRecords: async (input, options) => {
        calledWith = { input, options };
        return { sent_count: 2 };
      },
    });
    const tool = getTool("create_outreach_records", client);

    const result = await tool.execute(
      "call-1",
      { lead_ids: [7, 8] },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: { lead_ids: [7, 8] },
      options: { signal },
    });
    assertToolResult(result, { sent_count: 2 });
  });

  it("executes analyze_reply through the backend client", async () => {
    const signal = new AbortController().signal;
    let calledWith:
      | { input: AnalyzeReplyInput; options: { signal?: AbortSignal } | undefined }
      | undefined;
    const client = mockClient({
      analyzeReply: async (input, options) => {
        calledWith = { input, options };
        return { intent: "interested", lead_id: input.lead_id };
      },
    });
    const tool = getTool("analyze_reply", client);

    const result = await tool.execute(
      "call-1",
      {
        reply_text: "We are interested. Please send details.",
        lead_id: 7,
      },
      signal,
      undefined,
      undefined as never,
    );

    assert.deepEqual(calledWith, {
      input: {
        reply_text: "We are interested. Please send details.",
        lead_id: 7,
      },
      options: { signal },
    });
    assertToolResult(result, { intent: "interested", lead_id: 7 });
  });
});

function mockClient(overrides: Partial<MockClient> = {}): MockClient {
  return {
    getProductProfile: async () => ({ product_name: "SkyWalker" }),
    webSearch: async () => ({ query: "", results: [] }),
    fetchUrl: async () => ({ url: "", title: "", text: "" }),
    searchLeads: async () => ({ created_count: 0 }),
    listLeads: async () => ({ leads: [] }),
    createOutreachRecords: async () => ({ created_count: 0 }),
    analyzeReply: async () => ({ intent: "unknown" }),
    ...overrides,
  };
}

function getTool(name: string, client: MockClient) {
  const tool = createBusinessTools(client).find((candidate) => candidate.name === name);
  assert.ok(tool);
  return tool;
}

function assertToolResult(
  result: Awaited<ReturnType<ReturnType<typeof createBusinessTools>[number]["execute"]>>,
  payload: Record<string, unknown>,
): void {
  const firstContent = result.content[0];
  assert.equal(firstContent.type, "text");
  assert.equal(firstContent.text, JSON.stringify(payload, null, 2));
  assert.deepEqual(result.details, payload);
}
