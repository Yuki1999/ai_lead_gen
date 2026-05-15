export interface SearchLeadsInput {
  target_regions: string[];
  product_keywords?: string[];
  max_results?: number;
  real_search?: boolean;
  require_email?: boolean;
}

export interface WebSearchInput {
  query: string;
  max_results?: number;
}

export interface FetchUrlInput {
  url: string;
  email?: string;
}

export interface ListLeadsInput {
  region?: string;
  status?: string;
  q?: string;
}

export interface CreateOutreachRecordsInput {
  lead_ids: number[];
}

export interface AnalyzeReplyInput {
  reply_text: string;
  lead_id?: number;
}

export interface BackendRequestOptions {
  signal?: AbortSignal;
}

type JsonObject = Record<string, unknown>;

export class BackendClient {
  readonly #baseUrl: string;

  constructor(baseUrl: string) {
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
  }

  getProductProfile(options: BackendRequestOptions = {}): Promise<JsonObject> {
    return this.#request("GET", "/product/profile", undefined, options);
  }

  searchLeads(
    input: SearchLeadsInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/leads/search", {
      target_regions: input.target_regions,
      product_keywords: input.product_keywords ?? [],
      max_results: input.max_results ?? 8,
      real_search: input.real_search ?? true,
      require_email: input.require_email ?? true,
    }, options);
  }

  webSearch(
    input: WebSearchInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/web/search", {
      query: input.query,
      max_results: input.max_results ?? 8,
    }, options);
  }

  fetchUrl(
    input: FetchUrlInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/web/fetch", {
      url: input.url,
      email: input.email ?? "",
    }, options);
  }

  listLeads(
    input: ListLeadsInput = {},
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    const params = new URLSearchParams();
    appendQueryParam(params, "region", input.region);
    appendQueryParam(params, "status", input.status);
    appendQueryParam(params, "q", input.q);
    const query = params.toString();

    return this.#request("GET", query ? `/leads?${query}` : "/leads", undefined, options);
  }

  createOutreachRecords(
    input: CreateOutreachRecordsInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/campaigns/outreach-records", input, options);
  }

  analyzeReply(
    input: AnalyzeReplyInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/replies/analyze", input, options);
  }

  async #request(
    method: "GET" | "POST",
    path: string,
    body?: object,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    const response = await fetch(`${this.#baseUrl}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: options.signal,
    });

    const responseText = await response.text();
    if (!response.ok) {
      throw new Error(
        `Backend request failed with ${response.status} ${response.statusText} for ${method} ${path}: ${responseText}`,
      );
    }

    if (!responseText) {
      return {};
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(responseText);
    } catch (error) {
      throw new Error(
        `Backend returned invalid JSON for ${method} ${path}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
    if (!isJsonObject(parsed)) {
      throw new Error(`Backend returned non-object JSON for ${method} ${path}`);
    }

    return parsed;
  }
}

function appendQueryParam(
  params: URLSearchParams,
  name: string,
  value: string | undefined,
): void {
  if (value !== undefined && value !== "") {
    params.set(name, value);
  }
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
