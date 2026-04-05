@echo off
echo ============================================
echo  Building Quant Platform (MSVC)
echo ============================================

cd /d "%~dp0.."

if not exist build mkdir build
cd build

cmake .. -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (
    echo CMake configuration failed.
    exit /b 1
)

cmake --build . --config Release
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build succeeded. Output: build\Release\quant_platform.exe
echo.

if not exist Release\config mkdir Release\config
xcopy /Y /E ..\config Release\config\

if not exist Release\data mkdir Release\data
xcopy /Y /E ..\data Release\data\

echo Files copied to Release directory.
pause
