@echo off
REM Safe mode: dashboard only, no browser auto-open. Copy the URL
REM printed in the console into your browser yourself. Press Ctrl+C
REM in this window to stop Sidee.
"%~dp0Sidee.exe" --headless
pause
