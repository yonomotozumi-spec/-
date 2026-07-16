#!/usr/bin/env node
/*
 * 保安林データ 取得＋生成（ワンコマンド）
 * ---------------------------------------------------------------------------
 * 国土数値情報 森林地域(A13) の zip をダウンロード → 展開 → shapefile を自動検出
 * → 保安林を抽出して data/hoanrin/{都道府県コード}.geojson を生成します。
 * （内部で scripts/build-hoanrin.mjs を呼びます）
 *
 * ■ 前提: この環境のネットワークポリシーで nlftp.mlit.go.jp を許可していること
 *   （Claude Code on the web の場合: 環境設定 → Network access → Custom →
 *    Allowed domains に nlftp.mlit.go.jp（と msearch.gsi.go.jp）を追加）
 *
 * ■ 使い方
 *   node scripts/fetch-hoanrin.mjs --pref 13
 *   node scripts/fetch-hoanrin.mjs --pref 01 --year 15
 *
 *   オプション:
 *     --year 15        A13 の整備年度（既定 15 = 2015年度版）。年度で配布URLが変わります。
 *     --url  <zipURL>  配布URLを明示指定（--year のパターンで合わない場合）。
 *     --zip  <path>    手元にダウンロード済みの zip を使う（ダウンロードを省略）。
 *     --inspect        展開した属性一覧だけ表示して終了（--field/--codes 確認用）。
 *     --field / --codes / --simplify … build-hoanrin.mjs にそのまま渡します。
 *
 *   属性名が年度で異なることがあります。0件になったら:
 *     node scripts/fetch-hoanrin.mjs --pref 13 --inspect   # 属性名を確認
 *     node scripts/build-hoanrin.mjs --input <展開した.shp> --pref 13 --field <名> --codes 3
 * ---------------------------------------------------------------------------
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k.startsWith("--")) {
      const next = argv[i + 1];
      if (next == null || next.startsWith("--")) { a[k.slice(2)] = true; }
      else { a[k.slice(2)] = next; i++; }
    }
  }
  return a;
}

const args = parseArgs(process.argv.slice(2));
const pref = String(args.pref || "").padStart(2, "0");
const year = String(args.year || "15");
if (!/^\d{2}$/.test(pref)) {
  console.error("使い方: node scripts/fetch-hoanrin.mjs --pref <2桁コード> [--year 15]");
  process.exit(1);
}

const url = args.url ||
  "https://nlftp.mlit.go.jp/ksj/gml/data/A13/A13-" + year + "/A13-" + year + "_" + pref + "_GML.zip";

const work = mkdtempSync(join(tmpdir(), "hoanrin-" + pref + "-"));
const zipPath = args.zip ? resolve(String(args.zip)) : join(work, "a13.zip");

// 再帰的にファイルを探索
function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

async function download(u, dest) {
  console.log("↓ ダウンロード: " + u);
  const r = await fetch(u);
  if (!r.ok) {
    throw new Error("HTTP " + r.status + " : " + u +
      "\n  → 年度(--year)違い、URL変更、またはネットワーク未許可の可能性。" +
      "\n  → 配布ページ: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A13.html");
  }
  const buf = Buffer.from(await r.arrayBuffer());
  writeFileSync(dest, buf);
  console.log("  取得 " + (buf.length / 1024 / 1024).toFixed(1) + " MB");
}

try {
  if (!args.zip) {
    await download(url, zipPath);
  } else if (!existsSync(zipPath)) {
    throw new Error("--zip のファイルが見つかりません: " + zipPath);
  }

  const exdir = join(work, "ex");
  execFileSync("unzip", ["-o", "-q", zipPath, "-d", exdir], { stdio: "inherit" });

  const files = walk(exdir, []);
  const shp = files.find(function (f) { return extname(f).toLowerCase() === ".shp"; });
  const geo = files.find(function (f) { return /\.(geojson|json)$/i.test(f); });
  const input = shp || geo;
  if (!input) {
    throw new Error("展開先に .shp / .geojson が見つかりませんでした: " + exdir);
  }
  console.log("✓ 入力を検出: " + input);

  if (args.inspect) {
    console.log("--- 属性一覧（--field/--codes の確認用）---");
    execFileSync("npx", ["--yes", "mapshaper", input, "-info"], { stdio: "inherit" });
    process.exit(0);
  }

  // build-hoanrin.mjs に委譲（抽出・簡略化・出力・検証はそちらでテスト済み）
  const buildArgs = ["scripts/build-hoanrin.mjs", "--input", input, "--pref", pref];
  if (args.field) buildArgs.push("--field", String(args.field));
  if (args.codes) buildArgs.push("--codes", String(args.codes));
  if (args.simplify) buildArgs.push("--simplify", String(args.simplify));
  execFileSync("node", buildArgs, { stdio: "inherit", cwd: repoRoot });
} catch (e) {
  console.error("✗ " + (e && e.message ? e.message : e));
  process.exit(1);
}
