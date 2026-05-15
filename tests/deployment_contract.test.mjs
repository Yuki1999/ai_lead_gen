import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";

const root = new URL("../", import.meta.url);

function read(path) {
  return readFileSync(new URL(path, root), "utf8");
}

describe("deployment contract", () => {
  it("defines a Docker Compose stack for frontend, backend, and agent", () => {
    const compose = read("docker-compose.yml");

    for (const service of ["frontend:", "backend:", "agent:"]) {
      assert.match(compose, new RegExp(service));
    }

    assert.match(compose, /AGENT_BASE_URL:\s*http:\/\/agent:8011/);
    assert.match(compose, /BACKEND_BASE_URL:\s*http:\/\/backend:8000/);
    assert.match(compose, /VITE_API_BASE_URL:\s*\/api/);
    assert.match(compose, /medbot-data:/);
  });

  it("ships container build files and an nginx api proxy", () => {
    for (const path of [
      "backend/Dockerfile",
      "agent/Dockerfile",
      "frontend/Dockerfile",
      "frontend/nginx.conf",
    ]) {
      assert.equal(existsSync(new URL(path, root)), true, `${path} should exist`);
    }

    const nginx = read("frontend/nginx.conf");
    assert.match(nginx, /location\s+\/api\//);
    assert.match(nginx, /proxy_pass\s+http:\/\/backend:8000\//);
    assert.match(nginx, /proxy_buffering\s+off/);
  });

  it("documents and automates the deploy flow", () => {
    const deployScript = read("scripts/deploy.sh");
    const readme = read("README.md");

    assert.match(deployScript, /docker compose up -d --build/);
    assert.match(deployScript, /agent\/\.env\.example/);
    assert.match(deployScript, /ensure_shared_agent_token/);
    assert.match(readme, /Docker Compose/);
    assert.match(readme, /scripts\/deploy\.sh/);
    assert.match(readme, /AGENT_TOKEN/);
    assert.equal(existsSync(new URL(".env.deploy.example", root)), true);
  });
});
