@echo off
rem ============================================================================
rem create_env.bat - Tao (hoac cap nhat) moi truong conda "3d_metric" cho 3DMeph.
rem
rem Cach dung (mo "Anaconda Prompt" o thu muc goc repo 3DMeph):
rem     environment\create_env.bat [--recreate] [--dry-run] [--with-weights]
rem
rem   --recreate      xoa env 3d_metric neu da co roi tao lai tu dau
rem   --dry-run       chi in cac lenh se chay, khong chay that
rem   --with-weights  truyen cho check_env.py: tai trong so VGGT-1B tu Hugging Face (nang)
rem
rem Bien moi truong tuy chon:
rem   VGGT_DIR    thu muc repo vggt (mac dinh: ..\..\vggt so voi thu muc nay)
rem   COLMAP_EXE  duong dan colmap.exe (mac dinh: ..\..\colmap\bin\colmap.exe)
rem
rem Neu env 3d_metric da co va khong co --recreate, script bo qua buoc tao env va chi
rem cai/cap nhat goi (pip se giu lai cac goi da dung dung phien ban).
rem File nay chi dung ky tu ASCII de tranh loi ma hoa cua cmd.exe.
rem ============================================================================
setlocal EnableExtensions

set "ENV_NAME=3d_metric"
set "PY_VER=3.12"
set "HERE=%~dp0"
set "REPO=%HERE%.."
if not defined VGGT_DIR set "VGGT_DIR=%REPO%\..\vggt"
set "RECREATE=0"
set "DRY=0"
set "WEIGHTS="

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="--recreate" set "RECREATE=1"
if /I "%~1"=="--dry-run" set "DRY=1"
if /I "%~1"=="--with-weights" set "WEIGHTS=--with-weights"
shift
goto parse
:parsed

where conda >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong tim thay conda trong PATH. Hay mo "Anaconda Prompt" roi chay lai.
    exit /b 1
)

set "ENV_EXISTS=0"
for /f "delims=" %%L in ('conda env list ^| findstr /B /C:"%ENV_NAME% "') do set "ENV_EXISTS=1"

if "%ENV_EXISTS%"=="1" if "%RECREATE%"=="1" (
    call :run conda env remove -n %ENV_NAME% -y || exit /b 1
    set "ENV_EXISTS=0"
)
if "%ENV_EXISTS%"=="0" (
    call :run conda create -n %ENV_NAME% python=%PY_VER% -y || exit /b 1
) else (
    echo [INFO] Env %ENV_NAME% da co, bo qua buoc tao. Dung --recreate de tao lai.
)

rem --- torch ban CUDA 12.1 (khop driver RTX 4060; xem README environment) ---
call :pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121 || exit /b 1

rem --- goi nen va goi bo sung ---
call :pip install -r "%HERE%baseline-requirements.txt" || exit /b 1
call :pip install -r "%REPO%\requirements.txt" || exit /b 1

rem --- vggt cai editable, KHONG keo torch==2.3.1 trong vggt\requirements.txt ---
if exist "%VGGT_DIR%\pyproject.toml" (
    call :pip install -e "%VGGT_DIR%" --no-deps || exit /b 1
) else (
    echo [CANH BAO] Khong thay "%VGGT_DIR%\pyproject.toml". Dat bien VGGT_DIR roi chay lai de cai vggt.
)

rem --- kiem tra cuoi ---
call :run conda run -n %ENV_NAME% --no-capture-output python "%HERE%check_env.py" %WEIGHTS%
exit /b %errorlevel%

:pip
call :run conda run -n %ENV_NAME% --no-capture-output python -m pip %*
exit /b %errorlevel%

:run
echo ^> %*
if "%DRY%"=="1" exit /b 0
call %*
exit /b %errorlevel%
