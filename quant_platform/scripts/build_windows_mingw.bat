@echo off
echo ============================================
echo  Building Quant Platform (MinGW-w64)
echo ============================================

cd /d "%~dp0.."

if not exist build mkdir build
cd build

cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo CMake configuration failed.
    exit /b 1
)

cmake --build .
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build succeeded. Output: build\quant_platform.exe
echo.

if not exist config mkdir config
xcopy /Y /E ..\config config\

if not exist data mkdir data
xcopy /Y /E ..\data data\

echo Files copied to build directory.
pause
