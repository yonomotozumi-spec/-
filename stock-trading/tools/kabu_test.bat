@echo off
rem kabuステーションAPI 疎通確認 (ダブルクリックで実行 / 発注はしない)
rem 事前条件: kabuステーションが起動していること
cd /d "%~dp0.."
python tools\kabu_connect_test.py %*
echo.
pause
