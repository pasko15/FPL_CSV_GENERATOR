@echo off
cd /d "%~dp0"
echo Refreshing all configured FPL datasets...
py -3 -m fpl_pipeline refresh
if errorlevel 1 (
  echo.
  echo Refresh finished with errors. Review the messages above.
) else (
  echo.
  echo Refresh completed successfully.
)
pause
