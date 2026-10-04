import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..");
const backendRoot = path.join(repoRoot, "backend");
const outputPath = path.join(webRoot, "src/lib/types.generated.ts");

function run(command, args, options) {
  const result = spawnSync(command, args, { encoding: "utf8", ...options });
  if (result.error || result.status !== 0) {
    if (result.stderr) process.stderr.write(result.stderr);
    throw result.error ?? new Error(`${command} exited with status ${result.status}`);
  }
  return result.stdout;
}

const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "avtorinok-openapi-"));
const schemaPath = path.join(temporaryDirectory, "openapi.json");

try {
  // Pydantic reads .env relative to cwd; a temporary cwd keeps deployment settings out of codegen.
  const schemaOutput = run(
    "uv",
    [
      "run",
      "--locked",
      "--project",
      backendRoot,
      "--directory",
      temporaryDirectory,
      "python",
      "-c",
      "import json; from app.main import app; print(json.dumps(app.openapi()))",
    ],
    {
      cwd: temporaryDirectory,
      env: {
        PATH: process.env.PATH ?? "",
        APP_ENV: "development",
        PYTHONPATH: backendRoot,
        UV_CACHE_DIR: path.join(temporaryDirectory, "uv-cache"),
        UV_NO_PROGRESS: "1",
      },
    },
  );
  const schema = JSON.parse(schemaOutput);
  if (!schema.openapi?.startsWith("3.") || !schema.paths) {
    throw new Error("FastAPI did not return an OpenAPI 3 document");
  }
  await writeFile(schemaPath, `${JSON.stringify(schema, null, 2)}\n`);

  run(
    path.join(webRoot, "node_modules/.bin/openapi-typescript"),
    [schemaPath, "--output", outputPath],
    { cwd: webRoot, stdio: "inherit" },
  );
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
