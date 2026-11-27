# 株式自動取引システム (Claude Trading Manager)

Claude が **取引の全体管理者** として動作する株式自動売買システムです。

- **マーケット情報の収集**: 株価データ（日足）とテクニカル指標を自動取得・計算
- **リスク・リターンの計算**: シャープレシオ / ソルティノレシオ / 最大ドローダウン / VaR / CVaR / ボラティリティ
- **売買指示の生成**: 複数戦略のシグナルを統合し、リスク管理ルールを通過した注文だけを発注
- **ポジション管理**: 資金配分・損切り・利確・エクスポージャー制限を自動執行
- **バックテスト**: 過去データで戦略の期待リターンとリスクを事前検証

> ⚠️ **重要（免責事項）**
> 本システムはデフォルトで **ペーパートレード（仮想売買）** で動作します。
> 実際の証券口座への発注は行いません。実弾運用するには証券会社APIのアダプタを
> `autotrader/execution/` に実装し、明示的に設定で有効化する必要があります。
> 投資判断は自己責任です。本システムは利益を保証するものではありません。

---

## アーキテクチャ

```
main.py                     CLI エントリポイント
autotrader/
  manager.py                ★ 全体管理者 (TradingManager)
                              収集 → 分析 → リスク判定 → 指示 → 執行 を統括
  data/market_data.py       マーケットデータ収集 (yfinance) + テクニカル指標
  strategy/
    momentum.py             モメンタム戦略 (SMAクロス + トレンド)
    mean_reversion.py       平均回帰戦略 (RSI + ボリンジャーバンド)
    ensemble.py             複数戦略のシグナル統合
  risk/
    metrics.py              リスク・リターン指標の計算
    manager.py              リスク管理 (ポジションサイズ / 損切り / 上限チェック)
  portfolio/portfolio.py    ポートフォリオ状態 (現金・保有・損益・取引履歴)
  execution/
    broker.py               ブローカー抽象インターフェース
    paper.py                ペーパートレード執行 (手数料・スリッページ込み)
  backtest/engine.py        バックテストエンジン
config/config.yaml          運用設定 (銘柄・資金・リスク許容度)
state/                      ポートフォリオ状態の永続化 (JSON)
tests/                      ユニットテスト (ネットワーク不要)
```

## セットアップ

```bash
cd stock-trading
pip install -r requirements.txt
```

## 使い方

### 1. マーケット状況の確認と売買指示の取得（発注なし）

```bash
python main.py advise
```

各銘柄のシグナル・リスク指標・推奨アクション（BUY / SELL / HOLD と株数）を表示します。

### 2. 自動売買サイクルの実行（ペーパートレード）

```bash
python main.py run
```

データ収集 → シグナル計算 → リスク判定 → 注文執行（仮想）→ 状態保存 を1サイクル実行します。
cron 等で毎営業日の引け後に実行する運用を想定しています。

### 3. バックテスト

```bash
python main.py backtest --start 2023-01-01
```

### 4. ポートフォリオ・リスクレポート

```bash
python main.py report
```

### 5. ペーパートレード実測パフォーマンスの評価

```bash
python main.py measure
```

`state/equity_log.csv`（`run` 実行時に自動追記）から実測の年率リターン・シャープレシオを計算し、
リスク設定プラン（`config/planA.yaml` / `planB.yaml`）の判定目安を表示します。

## CI による自動運用（GitHub Actions）

| ワークフロー | 起動方法 | 内容 |
|---|---|---|
| `Paper Trade Daily` | 平日16:15 JST自動（デフォルトブランチ）/ `.trigger-paper-trade` 更新push | 日次売買サイクルを実行し `state/` をコミット |
| `Backtest Real Data` | 手動 / `.trigger-backtest` 更新push | 実データでバックテストし `reports/backtest-latest.md` を更新 |

売買単位は既定で1株（`execution.lot_size: 1`）です。資金50万円では東証の100株単元が
配分上限内に収まらないため、単元未満株（SBIのS株・楽天のかぶミニ等）での運用を前提にしています。

## 設定 (`config/config.yaml`)

| キー | 説明 |
|------|------|
| `universe` | 監視・売買対象の銘柄リスト（東証は `7203.T` 形式） |
| `initial_capital` | 初期資金（円） |
| `risk.max_position_weight` | 1銘柄あたりの最大配分比率 |
| `risk.max_gross_exposure` | 株式全体の最大エクスポージャー |
| `risk.stop_loss_pct` | 取得価格からの損切りライン |
| `risk.take_profit_pct` | 固定利確ライン（既定 `0.0` = 無効。上値を切らない） |
| `risk.trailing_stop_pct` | トレーリング利確：保有中の高値からの下落率で利食う（既定 `0.12`） |
| `risk.max_daily_var_pct` | 日次VaR(95%)の許容上限 |
| `execution.mode` | `paper`（既定）。実運用アダプタ実装時のみ変更 |

## テスト

```bash
python -m pytest tests/ -v
```

すべてのテストは合成データで動作し、ネットワーク接続は不要です。
