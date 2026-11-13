/**
 * Zero-dependency builder and .vsix packager for `apps/vscode-extension`.
 *
 * 1. Strips TypeScript annotations from `packages/shared-types/index.ts` and
 *    `apps/vscode-extension/src/extension.ts` into `dist/` so the extension runs
 *    directly in the VS Code Node extension host.
 * 2. Generates a valid OPC `.vsix` archive (`statescout-vscode-0.1.0.vsix`)
 *    installable via `code --install-extension statescout-vscode-0.1.0.vsix`.
 */

import fs from "node:fs";
import path from "node:path";
import { stripTypeScriptTypes } from "node:module";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(extDir, "../..");
const distDir = path.join(extDir, "dist");

fs.mkdirSync(distDir, { recursive: true });

const sharedTsPath = path.join(repoRoot, "packages/shared-types/index.ts");
const extTsPath = path.join(extDir, "src/extension.ts");

const sharedJs = stripTypeScriptTypes(fs.readFileSync(sharedTsPath, "utf8"));
let extJs = stripTypeScriptTypes(fs.readFileSync(extTsPath, "utf8"));
extJs = extJs.replace(
  /from\s+["']@statescout\/shared-types["']/g,
  'from "./shared-types.js"',
);

fs.writeFileSync(path.join(distDir, "shared-types.js"), sharedJs, "utf8");
fs.writeFileSync(path.join(distDir, "extension.js"), extJs, "utf8");

// Also build a CommonJS bundle (`dist/extension.cjs`) for the VS Code Node extension host,
// where `require("vscode")` is only injected into CommonJS modules.
const cjsShared = sharedJs.replace(/\bexport\s+(const|function|class)\s+/g, "$1 ");
const cjsExt = extJs
  .replace(/import\s*\{[\s\S]*?\}\s*from\s*["']\.\/shared-types\.js["'];?/g, "")
  .replace(/\bexport\s+(const|function|class)\s+/g, "$1 ");
const cjsBundle = `"use strict";\n${cjsShared}\n${cjsExt}\nmodule.exports = {\n  COMMANDS,\n  DEFAULT_API_BASE_URL,\n  describeRun,\n  describeAudit,\n  rankViolations,\n  rankFindings,\n  buildAuditPayload,\n  AuditApiClient,\n  renderAuditWebviewHtml,\n  activate,\n  deactivate,\n};\n`;
fs.writeFileSync(path.join(distDir, "extension.cjs"), cjsBundle, "utf8");

if (process.argv.includes("--build-only")) {
  console.log("Built apps/vscode-extension/dist/extension.js and extension.cjs");
  process.exit(0);
}

// Minimal ZIP writer (DEFLATE) for standard OPC .vsix archives
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function buildZip(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const { name, data } of entries) {
    const nameBuf = Buffer.from(name, "utf8");
    const raw = Buffer.isBuffer(data) ? data : Buffer.from(data, "utf8");
    const compressed = zlib.deflateRawSync(raw);
    const crc = crc32(raw);

    const localHeader = Buffer.alloc(30 + nameBuf.length);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0, 6);
    localHeader.writeUInt16LE(8, 8);
    localHeader.writeUInt16LE(0, 10);
    localHeader.writeUInt16LE(0, 12);
    localHeader.writeUInt32LE(crc, 14);
    localHeader.writeUInt32LE(compressed.length, 18);
    localHeader.writeUInt32LE(raw.length, 22);
    localHeader.writeUInt16LE(nameBuf.length, 26);
    localHeader.writeUInt16LE(0, 28);
    nameBuf.copy(localHeader, 30);

    const centralHeader = Buffer.alloc(46 + nameBuf.length);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0, 8);
    centralHeader.writeUInt16LE(8, 10);
    centralHeader.writeUInt16LE(0, 12);
    centralHeader.writeUInt16LE(0, 14);
    centralHeader.writeUInt32LE(crc, 16);
    centralHeader.writeUInt32LE(compressed.length, 20);
    centralHeader.writeUInt32LE(raw.length, 24);
    centralHeader.writeUInt16LE(nameBuf.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);
    nameBuf.copy(centralHeader, 46);

    localParts.push(localHeader, compressed);
    centralParts.push(centralHeader);
    offset += localHeader.length + compressed.length;
  }

  const centralDir = Buffer.concat(centralParts);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralDir.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, centralDir, eocd]);
}

const pkg = JSON.parse(
  fs.readFileSync(path.join(extDir, "package.json"), "utf8"),
);

const contentTypesXml = `<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".cjs" ContentType="application/javascript"/>
  <Default Extension=".svg" ContentType="image/svg+xml"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>`;

const vsixManifest = `<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="${pkg.name}" Version="${pkg.version}" Publisher="${pkg.publisher || "statescout-ai"}"/>
    <DisplayName>${pkg.displayName}</DisplayName>
    <Description xml:space="preserve">${pkg.description}</Description>
    <Categories>Testing</Categories>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
  </Assets>
</PackageManifest>`;

const vsixPath = path.join(extDir, `${pkg.name}-${pkg.version}.vsix`);
const vsixEntries = [
  { name: "[Content_Types].xml", data: contentTypesXml },
  { name: "extension.vsixmanifest", data: vsixManifest },
  {
    name: "extension/package.json",
    data: fs.readFileSync(path.join(extDir, "package.json")),
  },
  {
    name: "extension/README.md",
    data: fs.readFileSync(path.join(extDir, "README.md")),
  },
  {
    name: "extension/media/sidebar-icon.svg",
    data: fs.readFileSync(path.join(extDir, "media/sidebar-icon.svg")),
  },
  {
    name: "extension/dist/shared-types.js",
    data: fs.readFileSync(path.join(distDir, "shared-types.js")),
  },
  {
    name: "extension/dist/extension.js",
    data: fs.readFileSync(path.join(distDir, "extension.js")),
  },
  {
    name: "extension/dist/extension.cjs",
    data: fs.readFileSync(path.join(distDir, "extension.cjs")),
  },
];
const defaultReportPath = path.join(distDir, "default-report.json");
if (fs.existsSync(defaultReportPath)) {
  vsixEntries.push({
    name: "extension/dist/default-report.json",
    data: fs.readFileSync(defaultReportPath),
  });
}
const zipBuffer = buildZip(vsixEntries);

fs.writeFileSync(vsixPath, zipBuffer);
console.log(`Packaged VSIX: ${vsixPath} (${zipBuffer.length} bytes)`);

