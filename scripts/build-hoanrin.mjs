#!/usr/bin/env node
/*
 * 保安林 GeoJSON ビルドスクリプト
 * ---------------------------------------------------------------------------
 * 国土数値情報「森林地域データ(A13)」から「保安林」ポリゴンだけを抽出し、
 * api/hoanrin.js が使う data/hoanrin/{都道府県コード}.geojson を生成します。
 *
 * 依存: mapshaper（npx で自動取得。事前インストール不要）
 *
 * ■ 元データの入手（無償）
 *   国土数値情報 森林地域データ(A13):
 *     https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A13.html
 *   都道府県ごとに Shapefile（.shp 一式）または GeoJSON をダウンロードして展開します。
 *   ※ このダウンロードサイトはネットワークによっては直リンク不可のため、
 *      ブラウザから取得 → ローカルに展開してください。
 *
 * ■ 使い方
 *   node scripts/build-hoanrin.mjs --input <A13の.shp または .geojson> --pref <2桁コード>
 *
 *   例（東京都=13 の Shapefile を変換）:
 *     node scripts/build-hoanrin.mjs --input ./A13-15_13_GML/A13-15_13.shp --pref 13
 *
 *   オプション:
 *     --codes 3          抽出する森林地域種別コード（既定 "3"=保安林）。
 *                        保安施設地区も含めたい場合は --codes 3,4 のように指定。
 *     --field A13_001    種別コードの属性名（既定 A13_001）。年次で異なる場合に変更。
 *     --simplify 15%     ジオメトリ簡略化率（既定 15%。ファイルを小さくしたいほど下げる）。
 *     --out <path>       出力先（既定 data/hoanrin/{pref}.geojson）。
 *
 *   属性名が分からないときは、まず中身を確認:
 *     npx mapshaper <input> -info
 *     npx mapshaper <input> -fields
 * ---------------------------------------------------------------------------
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, existsSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k.startsWith("--")) { a[k.slice(2)] = argv[i + 1]; i++; }
  }
  return a;
}

const args = parseArgs(process.argv.slice(2));
const input = args.input;
const pref = String(args.pref || "").padStart(2, "0");
const codes = String(args.codes || "3").split(",").map(function (s) { return s.trim(); });
const field = args.field || "A13_001";
const simplify = args.simplify || "15%";
const out = args.out || resolve(repoRoot, "data", "hoanrin", pref + ".geojson");

if (!input || !/^\d{2}$/.test(pref)) {
  console.error("使い方: node scripts/build-hoanrin.mjs --input <A13.shp|A13.geojson> --pref <2桁コード>");
  console.error("例:     node scripts/build-hoanrin.mjs --input ./A13-15_13_GML/A13-15_13.shp --pref 13");
  process.exit(1);
}
if (!existsSync(input)) {
  console.error("入力ファイルが見つかりません: " + input);
  process.exit(1);
}

mkdirSync(dirname(out), { recursive: true });

// 森林地域種別コード → 名称（A13 の区分）
const KIND = { "1": "国有林", "2": "地域森林計画対象民有林", "3": "保安林", "4": "保安施設地区" };

// mapshaper のコマンドを組み立て:
//  1) 指定コード（既定=保安林3）だけを filter
//  2) hoanrinKind を付与し、属性は hoanrinKind のみ残す（サイズ削減）
//  3) simplify（トポロジ保持）
//  4) GeoJSON 出力（座標精度を落として軽量化）
const codeExpr = codes
  .map(function (c) { return "String(" + field + ") === '" + c + "'"; })
  .join(" || ");
const kindExpr =
  "hoanrinKind = (" + JSON.stringify(KIND) + ")[String(" + field + ")] || '保安林'";

const mapshaperArgs = [
  "mapshaper", input,
  "-filter", codeExpr,
  "-each", kindExpr,
  "-filter-fields", "hoanrinKind",
  "-simplify", simplify, "keep-shapes",
  "-clean",
  "-o", "format=geojson", "precision=0.00001", "rfc7946", out
];

console.log("▶ 保安林を抽出中… pref=" + pref + " codes=[" + codes.join(",") + "] field=" + field);
console.log("  input : " + input);
console.log("  output: " + out);

try {
  execFileSync("npx", ["--yes", ...mapshaperArgs], { stdio: "inherit" });
} catch (e) {
  console.error("mapshaper の実行に失敗しました。属性名(--field)が正しいか、");
  console.error("`npx mapshaper " + input + " -fields` で確認してください。");
  process.exit(1);
}

if (existsSync(out)) {
  const kb = (statSync(out).size / 1024).toFixed(0);
  console.log("✓ 生成しました: " + out + " (" + kb + " KB)");
  console.log("  api/hoanrin.js が /api/hoanrin?area=" + pref + "&lat=..&lon=.. で参照します。");
} else {
  console.error("出力が生成されませんでした（該当コードの地物が無い可能性）。--codes/--field を確認してください。");
  process.exit(1);
}
