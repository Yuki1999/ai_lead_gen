import assert from "node:assert/strict";
import { createServer, type IncomingMessage } from "node:http";
import type { AddressInfo } from "node:net";
import { describe, it } from "node:test";

import { BackendClient } from "../src/backendClient.js";

interface CapturedRequest {
  method: string | undefined;
  path: string | undefined;
  body: unknown;
}

async function readJson(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }

  if (chunks.length === 0) {
    return undefined;
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

interface MockBackendOptions {
  encodeResponse?: (payload: object) => string;
}

async function withMockBackend<T>(
  handler: (
    request: IncomingMessage,
    captured: CapturedRequest[],
  ) => Promise<object> | object,
  run: (baseUrl: string, captured: CapturedRequest[]) => Promise<T>,
  options: MockBackendOptions = {},
): Promise<T> {
  const captured: CapturedRequest[] = [];
  const server = createServer(async (request, response) => {
    try {
      const body = request.method === "GET" ? undefined : await readJson(request);
      captured.push({ method: request.method, path: request.url, body });
      const payload = await handler(request, captured);
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(options.encodeResponse?.(payload) ?? JSON.stringify(payload));
    } catch (error) {
      response.writeHead(500, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          detail: error instanceof Error ? error.message : "mock failed",
        }),
      );
    }
  });

  server.listen(0);
  await new Promise<void>((resolve) => server.once("listening", resolve));
  const address = server.address();
  assert.equal(typeof address, "object");
  assert.ok(address);
  const baseUrl = `http://127.0.0.1:${(address as AddressInfo).port}/`;

  try {
    return await run(baseUrl, captured);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

describe("BackendClient", () => {
  it("gets the product profile", async () => {
    await withMockBackend(
      (request) => {
        assert.equal(request.method, "GET");
        assert.equal(request.url, "/product/profile");
        return { product_name: "SkyWalker" };
      },
      async (baseUrl) => {
        const client = new BackendClient(baseUrl);

        const profile = await client.getProductProfile();

        assert.equal(profile.product_name, "SkyWalker");
      },
    );
  });

  it("searches leads with defaulted payload", async () => {
    await withMockBackend(
      () => ({ created_count: 1 }),
      async (baseUrl, captured) => {
        const client = new BackendClient(baseUrl);

        const result = await client.searchLeads({ target_regions: ["India"] });

        assert.equal(result.created_count, 1);
        assert.deepEqual(captured[0], {
          method: "POST",
          path: "/leads/search",
          body: {
            target_regions: ["India"],
            product_keywords: [],
            max_results: 8,
            real_search: true,
            require_email: true,
          },
        });
      },
    );
  });

  it("performs a web search with defaulted payload", async () => {
    await withMockBackend(
      () => ({ query: "orthopedic implant distributor India", results: [{ url: "https://ortho.example" }] }),
      async (baseUrl, captured) => {
        const client = new BackendClient(baseUrl);

        const result = await client.webSearch({
          query: "orthopedic implant distributor India",
        });

        assert.deepEqual(result.results, [{ url: "https://ortho.example" }]);
        assert.deepEqual(captured[0], {
          method: "POST",
          path: "/web/search",
          body: {
            query: "orthopedic implant distributor India",
            max_results: 8,
          },
        });
      },
    );
  });

  it("fetches a URL preview", async () => {
    await withMockBackend(
      () => ({ title: "Contact Ortho", email_found: true }),
      async (baseUrl, captured) => {
        const client = new BackendClient(baseUrl);

        const result = await client.fetchUrl({
          url: "https://ortho.example/contact",
          email: "sales@ortho.example",
        });

        assert.equal(result.title, "Contact Ortho");
        assert.deepEqual(captured[0], {
          method: "POST",
          path: "/web/fetch",
          body: {
            url: "https://ortho.example/contact",
            email: "sales@ortho.example",
          },
        });
      },
    );
  });

  it("throws contextual errors for invalid JSON success responses", async () => {
    await withMockBackend(
      () => ({}),
      async (baseUrl) => {
        const client = new BackendClient(baseUrl);

        await assert.rejects(
          client.getProductProfile(),
          /Backend returned invalid JSON for GET \/product\/profile/,
        );
      },
      { encodeResponse: () => "not-json" },
    );
  });

  it("forwards AbortSignal to fetch", async () => {
    const controller = new AbortController();
    controller.abort();
    await withMockBackend(
      () => ({ product_name: "SkyWalker" }),
      async (baseUrl) => {
        const client = new BackendClient(baseUrl);

        await assert.rejects(
          client.getProductProfile({ signal: controller.signal }),
          /aborted|abort/i,
        );
      },
    );
  });
});
