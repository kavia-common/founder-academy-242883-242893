@echo off
REM Workspace shim for the backend workspace directory (Windows).
REM Delegates to the frontend wrapper shim.
call "%~dp0..\\founder-academy-242883-242892\\gradlew.bat" %*
