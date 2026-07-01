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
  lead_type?: string;
  q?: string;
}

export interface GetScoringRulesInput {
  lead_type?: string;
}

export interface AddLeadsInput {
  leads: Array<{
    company_name: string;
    region: string;
    country: string;
    website?: string;
    contact_name?: string;
    email?: string;
    category?: string;
    match_reason?: string;
    source?: string;
    lead_type?: string;
    score?: number;
  }>;
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

export interface BackendClientAuth {
  /** Blanket-privileged fallback used when no specific human user is delegating. */
  serviceToken?: string;
  /** The delegating human user's own JWT — preferred whenever available so
   * outbound tool calls run under that user's real RBAC permissions. */
  userToken?: string;
}

export class BackendClient {
  readonly #baseUrl: string;
  readonly #serviceToken: string | undefined;
  #userToken: string | undefined;

  constructor(baseUrl: string, auth: BackendClientAuth = {}) {
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
    this.#serviceToken = auth.serviceToken;
    this.#userToken = auth.userToken;
  }

  /** Update which user this client's outbound calls are delegated as. Called
   * per chat turn so a long-lived cached session always uses the current
   * request's identity rather than a stale one from session creation time. */
  setUserToken(userToken: string | undefined): void {
    this.#userToken = userToken;
  }

  getProductProfile(options: BackendRequestOptions = {}): Promise<JsonObject> {
    return this.#request("GET", "/product/profile", undefined, options);
  }

  getScoringRules(
    input: GetScoringRulesInput = {},
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    const leadType = input.lead_type === "kol" ? "kol" : "distributor";
    return this.#request("GET", `/scoring/rules?lead_type=${leadType}`, undefined, options);
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
    appendQueryParam(params, "lead_type", input.lead_type);
    appendQueryParam(params, "q", input.q);
    const query = params.toString();

    return this.#request("GET", query ? `/leads?${query}` : "/leads", undefined, options);
  }

  createOutreachRecords(
    input: CreateOutreachRecordsInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/campaigns/outreach-records", {
      ...input,
      source: "agent",
    }, options);
  }

  addLeads(
    input: AddLeadsInput,
    options: BackendRequestOptions = {},
  ): Promise<JsonObject> {
    return this.#request("POST", "/leads/batch", input.leads, options);
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
    const headers: Record<string, string> = {};
    if (body) {
      headers["Content-Type"] = "application/json";
    }
    if (this.#userToken) {
      // Delegate as the human user who started this chat, so RBAC is enforced
      // exactly as if they'd called the API directly (not a blanket service grant).
      headers["Authorization"] = `Bearer ${this.#userToken}`;
    } else if (this.#serviceToken) {
      // Fallback: no delegating user available, authenticate as the trusted
      // service principal (full permissions).
      headers["X-Service-Token"] = this.#serviceToken;
    }

    const response = await fetch(`${this.#baseUrl}${path}`, {
      method,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
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
