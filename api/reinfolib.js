
// 国土交通省「不動産情報ライブラリ」API を中継するサーバーレス関数。
//
// 目的:
//  - APIキーをサーバー側（環境変数 REINFOLIB_API_KEY）だけに保持し、フロントに露出させない
//  - ブラウザからの CORS 制約を回避する（本関数が CORS ヘッダを付与する）
//  - 取引価格情報を集計し、㎡単価（万円/㎡）の中央値をフロントに返す
//
// デプロイ: Vercel の場合、このファイルは自動で /api/reinfolib エンドポイントになります。
// 環境変数に REINFOLIB_API_KEY を設定してください（キーはコードに書かない）。
//
// APIキー取得: https://www.reinfolib.mlit.go.jp/ の「API機能」から無料申請。
//
// ※ 不動産情報ライブラリ API のエンドポイントID・パラメータ・レスポンス項目は
//    公式仕様に準拠していますが、仕様変更の可能性があるため、以下の定数で調整できます。

const BASE = "https://www.reinfolib.mlit.go.jp/ex-api/external";
const EP_PRICE = "/XIT001";     // 不動産価格（取引価格・成約価格）情報取得API
const EP_CITIES = "/XIT002";    // 都道府県内市区町村一覧取得API
const EP_LANDPRICE = "/XPT002"; // 地価公示・地価調査のポイント情報取得API（GISタイル）
const KEY_HEADER = "Ocp-Apim-Subscription-Key";

// 種別ごとの「Type」対応（不動産情報ライブラリの種類区分）
const TYPE_MAP = {
  mansion: ["中古マンション等"],
  house: ["宅地(土地と建物)"],
  land: ["宅地(土地)"]
};

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "public, max-age=3600");
}

function toNum(v) {
  if (v == null) return NaN;
  const n = parseFloat(String(v).replace(/,/g, ""));
  return isFinite(n) ? n : NaN;
}

function median(arr) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// 取引レコード配列から、種別ごとの ㎡単価（万円/㎡）中央値とサンプル数を算出
function summarize(rows) {
  const bucket = { mansion: [], house: [], land: [] };
  for (const r of rows) {
    const type = r.Type || r.type;
    const price = toNum(r.TradePrice);         // 取引総額（円）
    const area = toNum(r.Area);                // 面積（㎡）
    const unit = toNum(r.UnitPrice);           // 単価（円/㎡）※主に土地
    for (const key of Object.keys(TYPE_MAP)) {
      if (!TYPE_MAP[key].includes(type)) continue;
      let yenPerSqm = NaN;
      if (key === "land" && isFinite(unit) && unit > 0) {
        yenPerSqm = unit;                       // 土地は UnitPrice を優先
      } else if (isFinite(price) && isFinite(area) && area > 0) {
        yenPerSqm = price / area;               // それ以外は 総額 ÷ 面積
      }
      if (isFinite(yenPerSqm) && yenPerSqm > 0) {
        bucket[key].push(yenPerSqm / 10000);    // 円/㎡ → 万円/㎡
      }
    }
  }
  const out = {};
  for (const key of Object.keys(bucket)) {
    const med = median(bucket[key]);
    out[key] = med == null
      ? { median: null, count: 0 }
      : { median: Math.round(med * 10) / 10, count: bucket[key].length };
  }
  return out;
}

// 1レコードから、指定種別の ㎡単価（万円/㎡）を返す（該当しなければ NaN）
function unitForType(r, type) {
  const t = r.Type || r.type;
  if (!TYPE_MAP[type] || !TYPE_MAP[type].includes(t)) return NaN;
  const price = toNum(r.TradePrice), area = toNum(r.Area), unit = toNum(r.UnitPrice);
  let yen = NaN;
  if (type === "land" && isFinite(unit) && unit > 0) yen = unit;
  else if (isFinite(price) && isFinite(area) && area > 0) yen = price / area;
  return (isFinite(yen) && yen > 0) ? yen / 10000 : NaN;
}

// 緯度経度 → Webメルカトルのタイル座標(x,y)
function deg2tile(lat, lon, z) {
  const n = Math.pow(2, z);
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  );
  return { x: x, y: y };
}

// GeoJSON の feature.properties から「円/㎡ の地価」らしき数値を拾う（項目名の変動に強く）
function pickLandPrice(props) {
  if (!props) return NaN;
  // 代表的な項目名の候補（公示地価API）
  const cands = [
    "u_current_years_price_ja", "current_years_price", "price",
    "u_current_years_price", "L01_006", "L02_006"
  ];
  for (const k of cands) {
    if (props[k] != null) { const n = toNum(props[k]); if (isFinite(n) && n > 0) return n; }
  }
  // フォールバック: 「価格 / price」を含むキーで最初の妥当な数値
  for (const k of Object.keys(props)) {
    if (/price|価格/i.test(k)) { const n = toNum(props[k]); if (isFinite(n) && n > 1000) return n; }
  }
  return NaN;
}

async function callUpstream(path, params, key) {
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") url.searchParams.set(k, v);
  }
  const r = await fetch(url.toString(), { headers: { [KEY_HEADER]: key } });
  const text = await r.text();
  let json;
  try { json = JSON.parse(text); } catch (_) { json = null; }
  if (!r.ok) {
    const err = new Error("upstream " + r.status);
    err.status = r.status;
    err.detail = json || text.slice(0, 300);
    throw err;
  }
  return json;
}

module.exports = async function handler(req, res) {
  setCors(res);
  if (req.method === "OPTIONS") { res.status(204).end(); return; }

  const key = process.env.REINFOLIB_API_KEY;
  if (!key) {
    res.status(500).json({ error: "APIキー未設定", hint: "環境変数 REINFOLIB_API_KEY を設定してください" });
    return;
  }

  const q = req.query || {};
  const resource = q.resource || "price";

  try {
    // --- 市区町村一覧 ---
    if (resource === "cities") {
      if (!q.area) { res.status(400).json({ error: "area(都道府県コード)が必要です" }); return; }
      const data = await callUpstream(EP_CITIES, { area: q.area }, key);
      const list = (data && data.data ? data.data : []).map(function (c) {
        return { id: c.id || c.code, name: c.name };
      });
      res.status(200).json({ status: "OK", area: q.area, cities: list });
      return;
    }

    // --- 取引価格の集計 ---
    if (resource === "price") {
      if (!q.area) { res.status(400).json({ error: "area(都道府県コード)が必要です" }); return; }
      const now = new Date();
      // 直近の完了年を既定に（1〜3月は前々年まで確実にデータがある想定で -1）
      const defYear = String(now.getFullYear() - 1);
      const params = {
        year: q.year || defYear,
        area: q.area,
        city: q.city || undefined
      };
      if (q.quarter) params.quarter = q.quarter;
      const data = await callUpstream(EP_PRICE, params, key);
      const rows = (data && data.data) ? data.data : [];
      const results = summarize(rows);
      res.status(200).json({
        status: "OK",
        area: params.area,
        city: params.city || null,
        year: params.year,
        total: rows.length,
        results: results
      });
      return;
    }

    // --- 公示地価・地価調査（地点情報, 緯度経度→タイル） ---
    if (resource === "landprice") {
      const lat = toNum(q.lat), lon = toNum(q.lon);
      if (!isFinite(lat) || !isFinite(lon)) {
        res.status(400).json({ error: "lat/lon（緯度経度）が必要です" }); return;
      }
      const now = new Date();
      const year = q.year || String(now.getFullYear());
      const zoom = q.zoom ? parseInt(q.zoom, 10) : 14;
      const c = deg2tile(lat, lon, zoom);
      // 地価公示の地点はまばらなので、中心＋周囲8タイル(3×3)を収集
      const tiles = [];
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) tiles.push({ x: c.x + dx, y: c.y + dy });
      }
      const prices = [];
      let firstErr = null;
      await Promise.all(tiles.map(async function (t) {
        try {
          const data = await callUpstream(EP_LANDPRICE, {
            response_format: "geojson", z: zoom, x: t.x, y: t.y, year: year
          }, key);
          const feats = (data && data.features) ? data.features : [];
          for (const f of feats) {
            const p = pickLandPrice(f && f.properties);
            if (isFinite(p) && p > 0) prices.push(p / 10000); // 円/㎡ → 万円/㎡
          }
        } catch (e) { if (!firstErr) firstErr = e; }
      }));
      // 全タイルが上流エラーで、かつ1件も取れなければエラーとして報告
      if (!prices.length && firstErr) throw firstErr;
      const med = median(prices);
      res.status(200).json({
        status: "OK", lat: lat, lon: lon, year: year, zoom: zoom,
        center: c, count: prices.length,
        median: med == null ? null : Math.round(med * 10) / 10
      });
      return;
    }

    // --- 地区別の中古相場（DistrictNameで集計） ---
    if (resource === "districts") {
      if (!q.area) { res.status(400).json({ error: "area(都道府県コード)が必要です" }); return; }
      const now = new Date();
      const year = q.year || String(now.getFullYear() - 1);
      const type = q.type || "house";
      const data = await callUpstream(EP_PRICE, {
        year: year, area: q.area, city: q.city || undefined
      }, key);
      const rows = (data && data.data) ? data.data : [];
      const byDist = {}, all = [];
      for (const r of rows) {
        const u = unitForType(r, type);
        if (!isFinite(u)) continue;
        all.push(u);
        const d = r.DistrictName || r.districtName || "（地区不明）";
        (byDist[d] = byDist[d] || []).push(u);
      }
      const districts = Object.keys(byDist).map(function (name) {
        const m = median(byDist[name]);
        return { name: name, median: Math.round(m * 10) / 10, count: byDist[name].length };
      }).sort(function (a, b) { return b.median - a.median; });
      const cityMed = median(all);
      res.status(200).json({
        status: "OK", area: q.area, city: q.city || null, year: year, type: type,
        total: all.length,
        cityMedian: cityMed == null ? null : Math.round(cityMed * 10) / 10,
        districts: districts
      });
      return;
    }

    res.status(400).json({ error: "unknown resource", allowed: ["cities", "price", "landprice", "districts"] });
  } catch (e) {
    res.status(e.status || 502).json({
      error: "上流API呼び出しに失敗しました",
      status: e.status || null,
      detail: e.detail || String(e && e.message)
    });
  }
};
