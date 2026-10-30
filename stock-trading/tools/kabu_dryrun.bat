@echo off
rem 発注ドライラン (検証ポート18081) — 実際の発注は行われません
rem 事前条件: kabuステーションが起動していること
cd /d "%~dp0.."
python tools\kabu_dryrun_order.py
echo.
pause
