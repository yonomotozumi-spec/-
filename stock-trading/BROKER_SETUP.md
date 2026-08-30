# 実弾移行ロードマップ — 三菱UFJ eスマート証券 (kabuステーションAPI)

2026-08-28 口座開設完了を受けた移行手順。上から順に進める。

## 進捗チェックリスト

### あなたの作業 (証券会社側の手続き)

- [x] 口座開設申込・本人確認 (8/24)
- [x] **口座開設完了** (8/28 完了メール受信済み)
- [ ] 書留郵便「口座開設のご通知」を受け取る (ユーザーID・初期認証番号が記載)
- [ ] 初回ログイン → 「お取引前のご登録」「認証メールアドレスの登録」
      https://s10.kabu.co.jp/_mem_bin/members/login.asp
- [ ] 出金口座の登録
- [ ] **入金 150万円** (スムーズ入金/フルタイム入金)
- [ ] **信用取引口座の申込** (審査あり)
      ※目的は2つ: ①kabuステーションProfessionalプラン(API利用に必要)の無料適用条件
        ②将来の動的レバレッジ運用 (実測Sharpe≥0.8で解禁判定)
- [x] **kabuステーションのインストール** (Windows PCが必要)
- [x] **API利用設定** (2026-08-30 完了):

  **ステップ1: マイページでの「kabuステーションAPI利用設定」**
  1. メンバーズサイト (PC版) にログイン
  2. 「設定・申込」→「らくらく電子契約」をクリック
  3. 「取引ツール」の「設定」ボタン → 「kabuステーションAPI利用設定」の「設定」
  4. 設問にすべて回答し、利用規定に同意 → パスワード入力 →「設定する」
  5. 「らくらく電子契約」画面で**「利用可」**表示になっていることを確認
     ※ ProfessionalプランまたはPremiumプランでないと「利用不可」のまま
       (信用口座開設が無料適用の条件になるため、信用口座申込を先に済ませる)

  **ステップ2: kabuステーション本体の「APIシステム設定」**
  1. kabuステーションを起動し、画面右上の「</>」アイコンを**右クリック** →「APIシステム設定」
  2. ①「APIを利用する」にチェック ②**APIパスワードを設定** (英数字6〜16桁)
     ③「ソフトリミット (ワンショット上限)」を設定 → **40万円を推奨**
       (1銘柄予算37.5万を超える誤発注をブローカー側でも遮断する二重の安全装置)
  3. 「OK」→ kabuステーション再起動 → 右上アイコンが**緑**になれば利用可能
     (本番ポート18080 / 検証ポート18081)

## Windows PCでの疎通確認手順 (API設定完了後・発注なし)

1. **Pythonを導入** (未導入なら): https://www.python.org/downloads/ から3.11以降を
   インストール (「Add python.exe to PATH」にチェック)
2. PowerShellでリポジトリを取得:
   ```powershell
   git clone -b claude/stock-auto-trading-system-neb2u1 https://github.com/yonomotozumi-spec/-.git stock-system
   cd stock-system\stock-trading
   pip install -r requirements.txt
   ```
3. **kabuステーションを起動した状態で**疎通テスト (読み取りのみ・発注しない):
   ```powershell
   python tools\kabu_connect_test.py           # 本番ポート18080
   python tools\kabu_connect_test.py --verify  # 検証ポート18081 (検証用パスワード)
   ```
   APIパスワードは実行時に非表示入力 (どこにも保存されない)。
   4/4 OKが出れば技術的準備は完了。
4. 実弾移行が承認されたら環境変数を永続設定 (PowerShell):
   ```powershell
   setx KABU_API_PASSWORD "本番用APIパスワード"
   setx KABU_ORDER_PASSWORD "注文パスワード"
   # KABU_CONFIRM_LIVE は移行判断が出るまで設定しない (安全装置)
   ```

### 私 (Claude) の作業

- [x] 単元株モードのペーパー計測 (planLive, 8/26開始・並行実行中)
- [x] **KabuBrokerアダプタ実装** (`autotrader/execution/kabu.py`, 8/28)
      SOR発注対応・成行/約定照会・単元株。モック済みユニットテスト付き
- [x] 疎通確認スクリプト `tools/kabu_connect_test.py` を用意 (8/30)
- [ ] 検証: 照会系APIのみで疎通確認 → 1単元のテスト発注 → 本稼働

## 実弾運用のアーキテクチャ (重要な制約)

kabuステーションAPIは**あなたのWindows PC上で起動しているkabuステーションへの
localhost接続**でのみ使えます。クラウド(GitHub Actions)からは発注できません。

```
[毎営業日 16:20 JST]
  あなたのWindows PC (タスクスケジューラ)
    └ kabuステーション起動状態で
      python main.py run --config config/planLive.yaml   (mode: kabu)
        ├ データ取得・シグナル・リスク判定 (従来どおり)
        ├ KabuBroker → localhost:18080 へ発注 (単元株・SOR成行)
        └ state/live/ を commit & push → ダッシュボードに反映
  クラウド側 (現行のCI) はペーパー計測とダッシュボード更新を継続
```

## 安全装置

- `execution.mode: kabu` への切替は設定ファイルの明示変更が必要 (既定はpaper)
- さらに環境変数 `KABU_CONFIRM_LIVE=yes` がないと実発注を拒否
- APIパスワード・注文パスワードは環境変数のみ (リポジトリには絶対に置かない)
- 移行初週は「1日1銘柄・1単元まで」の発注上限で試運転

## 判断ゲート (GOALS.md と同じ)

実弾移行の可否は単元株トラックのペーパー実測で判断:
15営業日以上・実測Sharpe 0.5以上でプランA実弾開始を提案。
信用(動的レバレッジ・上限2倍)は実測Sharpe 0.8以上が条件。
