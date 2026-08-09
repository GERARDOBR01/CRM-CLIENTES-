@echo off
REM ---------------------------------------------------------------------------
REM Levanta el CRM y lo deja corriendo. Cierra esta ventana para apagarlo.
REM Para que arranque solo al iniciar sesion en Windows:
REM   Win+R  ->  shell:startup  ->  pega aqui un acceso directo a este .bat
REM ---------------------------------------------------------------------------
cd /d "%~dp0"
title CRM Leads - no cierres esta ventana

REM headless: no vuelve a abrir el navegador en cada reinicio del servidor
REM address 0.0.0.0: tambien responde a otros equipos de tu red local (mismo WiFi)
python -m streamlit run app.py ^
  --server.headless true ^
  --server.address 0.0.0.0 ^
  --server.port 8501 ^
  --browser.gatherUsageStats false

echo.
echo El servidor se detuvo. Revisa el error de arriba.
pause
