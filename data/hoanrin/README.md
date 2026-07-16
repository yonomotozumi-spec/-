# 保安林データ（point-in-polygon 判定用）

`api/hoanrin.js` は、このフォルダの `{都道府県コード}.geojson` を読み込み、
緯度経度が保安林ポリゴンに含まれるかを判定します（例: `13.geojson` = 東京都）。

## データの生成

国土数値情報「森林地域データ(A13)」から保安林だけを抽出して生成します。

**ワンコマンド（nlftp.mlit.go.jp に通信できる環境）**:
```bash
node scripts/fetch-hoanrin.mjs --pref 13   # DL→展開→抽出→13.geojson まで一括
```

**手動**:
1. A13 を都道府県ごとにダウンロード（無償）
   https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A13.html
2. 展開したら変換:
   ```bash
   node scripts/build-hoanrin.mjs --input ./A13-15_13_GML/A13-15_13.shp --pref 13
   ```
   → `data/hoanrin/13.geojson` が生成されます。

全国分をまとめて同梱すると巨大になるため、**必要な都道府県だけ**生成すれば十分です。
（蓄電池の候補地が特定県に集中するなら、その県だけでよい）

## 配信を外部化する場合（任意）

大容量になる場合は、生成した GeoJSON を CDN 等に置き、
環境変数 `HOANRIN_DATA_BASE` にそのベースURLを設定すると、
`api/hoanrin.js` は `{HOANRIN_DATA_BASE}/{area}.geojson` を取得します。

## 注意

- A13 は概ね市区町村/地区単位のポリゴンで、更新は不定期です。最新性が必要な場合は
  都道府県の森林GIS・林野庁「保安林ポータル」も併せて確認してください。
- 判定結果は参考値です。開発可否の最終判断は必ず所管（都道府県林務部局）に照会してください。
