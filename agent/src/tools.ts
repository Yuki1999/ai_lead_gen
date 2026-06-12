import { defineTool, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import type {
  AddLeadsInput,
  AnalyzeReplyInput,
  BackendRequestOptions,
  BackendClient,
  CreateOutreachRecordsInput,
  FetchUrlInput,
  ListLeadsInput,
  SearchLeadsInput,
  WebSearchInput,
} from "./backendClient.js";

type ToolPayload = Record<string, unknown>;

export function createBusinessTools(client: Pick<BackendClient, BusinessMethod>) {
  return [
    defineTool({
      name: "add_leads",
      label: "Add Leads",
      description:
        "Save manually discovered distributor leads to the database. Use when you found leads via web_search/fetch_url and want to persist them.",
      parameters: Type.Object({
        leads: Type.Array(
          Type.Object({
            company_name: Type.String({ description: "Company name" }),
            region: Type.String({ description: "Region like Europe, North America" }),
            country: Type.String({ description: "Country" }),
            website: Type.Optional(Type.String({ description: "Website URL" })),
            contact_name: Type.Optional(Type.String({ description: "Contact person or department" })),
            email: Type.Optional(Type.String({ description: "Email address" })),
            category: Type.Optional(Type.String({ description: "Distributor category" })),
            match_reason: Type.Optional(Type.String({ description: "Why this lead matches" })),
            source: Type.Optional(Type.String({ description: "Source URL or note" })),
          }),
          { description: "Array of leads to save" }
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.addLeads(
            params as unknown as AddLeadsInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "get_product_profile",
      label: "Get Product Profile",
      description: "Fetch the SkyWalker product profile and positioning from the business API.",
      parameters: Type.Object({}),
      execute: async (_toolCallId, _params, signal) =>
        toolResult(await client.getProductProfile(signalOptions(signal))),
    }),
    defineTool({
      name: "web_search",
      label: "Web Search",
      description:
        "Search the public web for current pages, directories, exhibitor lists, competitors, and distributor evidence.",
      parameters: Type.Object({
        query: Type.String({
          description: "Search query to run on the public web.",
          minLength: 2,
        }),
        max_results: Type.Optional(
          Type.Integer({
            description: "Maximum number of search results to return.",
            minimum: 1,
            maximum: 20,
          }),
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.webSearch(
            params satisfies WebSearchInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "fetch_url",
      label: "Fetch URL",
      description:
        "Open a public URL and extract title, page text, visible emails, and whether a target email appears on the page.",
      parameters: Type.Object({
        url: Type.String({
          description: "HTTP or HTTPS URL to fetch.",
          minLength: 8,
        }),
        email: Type.Optional(
          Type.String({
            description: "Optional email to verify against the fetched page.",
          }),
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.fetchUrl(
            params satisfies FetchUrlInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "search_leads",
      label: "Search Leads",
      description: "Search for distributor leads and save discovered candidates in the business API.",
      parameters: Type.Object({
        target_regions: Type.Array(Type.String(), {
          description: "Target regions or countries to prospect.",
        }),
        product_keywords: Type.Optional(
          Type.Array(Type.String(), {
            description: "Optional additional product or procedure keywords.",
          }),
        ),
        max_results: Type.Optional(
          Type.Integer({
            description: "Maximum number of candidates to search for.",
            minimum: 1,
          }),
        ),
        real_search: Type.Optional(
          Type.Boolean({ description: "Use live web search when true." }),
        ),
        require_email: Type.Optional(
          Type.Boolean({ description: "Require discovered email addresses when true." }),
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.searchLeads(
            params satisfies SearchLeadsInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "list_leads",
      label: "List Leads",
      description: "List saved distributor leads, optionally filtering by region, status, or query.",
      parameters: Type.Object({
        region: Type.Optional(Type.String({ description: "Region or country filter." })),
        status: Type.Optional(Type.String({ description: "Lead status filter." })),
        q: Type.Optional(Type.String({ description: "Free-text search query." })),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.listLeads(
            params satisfies ListLeadsInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "create_outreach_records",
      label: "Create Outreach Records",
      description: "Create outreach email records for saved leads.",
      parameters: Type.Object({
        lead_ids: Type.Array(
          Type.Integer({
            minimum: 1,
            description: "Saved lead ID to create an outreach record for.",
          }),
          {
            description: "Saved lead IDs to create outreach records for.",
            minItems: 1,
          },
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.createOutreachRecords(
            params satisfies CreateOutreachRecordsInput,
            signalOptions(signal),
          ),
        ),
    }),
    defineTool({
      name: "analyze_reply",
      label: "Analyze Reply",
      description: "Analyze a prospect reply and optionally update the linked lead status.",
      parameters: Type.Object({
        reply_text: Type.String({ description: "Full reply text to analyze." }),
        lead_id: Type.Optional(
          Type.Integer({
            description: "Optional saved lead ID associated with the reply.",
            minimum: 1,
          }),
        ),
      }),
      execute: async (_toolCallId, params, signal) =>
        toolResult(
          await client.analyzeReply(
            params satisfies AnalyzeReplyInput,
            signalOptions(signal),
          ),
        ),
    }),
  ] satisfies ToolDefinition[];
}

function signalOptions(signal: AbortSignal | undefined): BackendRequestOptions {
  return signal ? { signal } : {};
}

export function toolResult(payload: ToolPayload) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

type BusinessMethod =
  | "getProductProfile"
  | "webSearch"
  | "fetchUrl"
  | "searchLeads"
  | "listLeads"
  | "addLeads"
  | "createOutreachRecords"
  | "analyzeReply";
