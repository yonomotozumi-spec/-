
// 保安林 判定 API（緯度経度 → 保安林ポリゴンの内包判定 / point-in-polygon）
//
// 目的:
//  - ある地点（緯度経度）が「保安林」に該当するかを完全自動で判定する
//  - 権威データは国土交通省「国土数値情報 森林地域データ(A13)」の保安林ポリゴン
//  - フロントからは APIキー不要で叩ける（reinfolib のキーはここでは使わない）
//
// データの用意:
//  - data/hoanrin/{都道府県コード}.geojson を配置する（例: data/hoanrin/13.geojson = 東京都）
//  - このファイルは scripts/build-hoanrin.mjs で A13 から生成する（保安林のみ抽出＋簡略化済み）
//  - 全国分をリポジトリに同梱すると巨大になるため、必要な都道府県だけ生成すればよい
//
// データ配信先の切り替え:
//  - 既定: このリポジトリに同梱した data/hoanrin/{area}.geojson を読む
//  - 環境変数 HOANRIN_DATA_BASE を設定すると、そのURLベースから {area}.geojson を取得
//    （例: HOANRIN_DATA_BASE=https://your-cdn.example.com/hoanrin ）
//
// デプロイ: Vercel の場合、このファイルは自動で /api/hoanrin エンドポイントになります。

const fs = require("fs");
const path = require("path");

// 都道府県ごとの FeatureCollection をプロセス内キャッシュ（ウォーム起動で再利用）
const cache = new Map();

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "public, max-age=3600");
}

function toNum(v) {
  if (v == null) return NaN;
  const n = parseFloat(String(v));
  return isFinite(n) ? n : NaN;
}

// --- 幾何計算（緯度経度=度 のまま。A13 は地理座標 JGD2011 で GSI ジオコーディングと整合） ---

// 点が単一のリング（[[lon,lat],...]）の内側にあるか（レイキャスティング法）
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const intersect = ((yi > y) !== (yj > y)) &&
      (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// polygon = [outerRing, hole1, hole2, ...]
function pointInPolygon(x, y, poly) {
  if (!poly || !poly.length || !pointInRing(x, y, poly[0])) return false;
  for (let k = 1; k < poly.length; k++) {
    if (pointInRing(x, y, poly[k])) return false; // 穴（ドーナツ）の中は該当外
  }
  return true;
}

function pointInGeometry(x, y, geom) {
  if (!geom) return false;
  if (geom.type === "Polygon") return pointInPolygon(x, y, geom.coordinates);
  if (geom.type === "MultiPolygon") {
    return geom.coordinates.some(function (p) { return pointInPolygon(x, y, p); });
  }
  return false;
}

// ジオメトリの外接矩形 [minX,minY,maxX,maxY]（高速な事前除外用）
function geomBbox(geom) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const walk = function (a) {
    if (typeof a[0] === "number") {
      if (a[0] < minX) minX = a[0]; if (a[0] > maxX) maxX = a[0];
      if (a[1] < minY) minY = a[1]; if (a[1] > maxY) maxY = a[1];
    } else {
      for (const b of a) walk(b);
    }
  };
  if (geom && geom.coordinates) walk(geom.coordinates);
  return [minX, minY, maxX, maxY];
}

function inBbox(x, y, b) {
  return b && x >= b[0] && y >= b[1] && x <= b[2] && y <= b[3];
}

// 都道府県コードを正規化（"13", 13, "13103"(市区町村) → "13"）
function normArea(area) {
  const s = String(area || "").trim();
  if (!/^\d+$/.test(s)) return null;
  return s.slice(0, 2).padStart(2, "0");
}

// feature から保安林の種別名を拾う（build スクリプトが付与する hoanrinKind を優先）
function kindOf(props) {
  if (!props) return "保安林";
  return props.hoanrinKind || props.HOANRIN_KIND || props.kind ||
    props.A13_002 || props.A13_001 || "保安林";
}

// 都道府県の保安林データを読み込む（無ければ null）
async function loadPref(area) {
  if (cache.has(area)) return cache.get(area);
  let fc = null;
  const base = process.env.HOANRIN_DATA_BASE;
  try {
    if (base) {
      const url = base.replace(/\/+$/, "") + "/" + area + ".geojson";
      const r = await fetch(url);
      if (r.ok) fc = await r.json();
    } else {
      const p = path.join(__dirname, "..", "data", "hoanrin", area + ".geojson");
      if (fs.existsSync(p)) fc = JSON.parse(fs.readFileSync(p, "utf8"));
    }
  } catch (_) {
    fc = null;
  }
  // 各 feature に bbox を前計算（未計算のもののみ）
  if (fc && Array.isArray(fc.features)) {
    for (const f of fc.features) {
      if (!f._bbox && f.geometry) f._bbox = geomBbox(f.geometry);
    }
  }
  cache.set(area, fc);
  return fc;
}

module.exports = async function handler(req, res) {
  setCors(res);
  if (req.method === "OPTIONS") { res.status(204).end(); return; }

  const q = req.query || {};
  const lat = toNum(q.lat), lon = toNum(q.lon);
  const area = normArea(q.area);

  if (!isFinite(lat) || !isFinite(lon)) {
    res.status(400).json({ error: "lat/lon（緯度経度）が必要です" });
    return;
  }
  if (!area) {
    res.status(400).json({ error: "area（都道府県コード 01〜47）が必要です" });
    return;
  }

  try {
    const fc = await loadPref(area);

    // データ未整備（この都道府県の保安林 GeoJSON が無い）
    if (!fc || !Array.isArray(fc.features)) {
      res.status(200).json({
        status: "OK", area: area, lat: lat, lon: lon,
        available: false, hit: false, kinds: [],
        hint: "この都道府県の保安林データ(data/hoanrin/" + area +
          ".geojson)が未整備です。scripts/build-hoanrin.mjs で生成してください。"
      });
      return;
    }

    // 内包判定（bbox で高速に絞り込んでから厳密判定）
    const kinds = [];
    let hit = false;
    for (const f of fc.features) {
      if (!f.geometry) continue;
      if (f._bbox && !inBbox(lon, lat, f._bbox)) continue;
      if (pointInGeometry(lon, lat, f.geometry)) {
        hit = true;
        const k = kindOf(f.properties);
        if (kinds.indexOf(k) < 0) kinds.push(k);
      }
    }

    res.status(200).json({
      status: "OK", area: area, lat: lat, lon: lon,
      available: true, hit: hit, kinds: kinds,
      count: fc.features.length,
      source: process.env.HOANRIN_DATA_BASE ? "remote" : "bundled"
    });
  } catch (e) {
    res.status(500).json({
      error: "保安林判定に失敗しました",
      detail: String(e && e.message)
    });
  }
};
