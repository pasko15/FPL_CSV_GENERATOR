@echo off
cd /d "%~dp0"
echo Refreshing FPL datasets that are due...
py -3 -m fpl_pipeline update
if errorlevel 1 (
  echo.
  echo Update finished with errors. Review the messages above.
) else (
  echo.
  echo Update completed successfully.
)
pause
