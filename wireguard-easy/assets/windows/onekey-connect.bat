@echo off
rem ============================================================
rem wireguard-easy :: Windows 一键连接（双击运行，自动提权）
rem 把本文件和 client 的 .conf 放在同一目录即可
rem ============================================================
chcp 65001 >nul
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0onekey-connect.ps1" -ConfigPath "%~dp0wireguard-client.conf"
