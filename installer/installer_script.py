# -*- coding: utf-8 -*-
"""
웹 리서치 어시스턴트 — 설치 프로그램
Python이 없어도 자동으로 설치합니다.
"""

import os, sys, shutil, subprocess, threading, glob
import tkinter as tk
from tkinter import ttk, messagebox

INSTALL_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'WebResearcher'
)

APP_FILES = ['app.py', 'web_researcher.py', '_local_keys.py', 'requirements.txt']

PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
PYTHON_INSTALL_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', ''),
    'Programs', 'Python', 'Python311'
)

# ── 리소스 경로 ────────────────────────────────
def _resource(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'app_data', name)

# ── Python 찾기 / 설치 ─────────────────────────
def _find_python():
    candidates = [
        os.path.join(PYTHON_INSTALL_DIR, 'python.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA',''), 'Programs','Python','Python312','python.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA',''), 'Programs','Python','Python313','python.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA',''), 'Programs','Python','Python310','python.exe'),
    ]
    # PATH 탐색
    for cmd in ('python', 'python3', 'py'):
        try:
            r = subprocess.run([cmd, '--version'], capture_output=True, timeout=5)
            if r.returncode == 0:
                import shutil as _sh
                found = _sh.which(cmd)
                if found:
                    return found
        except Exception:
            pass
    # 고정 경로 탐색
    for p in candidates:
        if os.path.exists(p):
            return p
    # glob
    for pattern in [
        os.path.join(os.environ.get('LOCALAPPDATA',''), 'Programs','Python','Python*','python.exe'),
        r'C:\Python*\python.exe',
    ]:
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[-1]
    return None

def _install_python(log):
    """Python 3.11 다운로드 후 조용히 설치"""
    import urllib.request
    tmp = os.path.join(os.environ.get('TEMP', os.getcwd()), 'python_installer.exe')
    log("⬇️  Python 다운로드 중... (약 30MB, 1~2분 소요)")

    def reporthook(count, block, total):
        if total > 0:
            pct = int(count * block * 100 / total)
            if count % 50 == 0:
                log(f"    다운로드 {min(pct,100)}%...")

    urllib.request.urlretrieve(PYTHON_INSTALLER_URL, tmp, reporthook)
    log("🔧 Python 3.11 설치 중... (1~2분)")
    r = subprocess.run([
        tmp,
        '/quiet',
        'InstallAllUsers=0',
        'PrependPath=1',
        'Include_test=0',
        'Include_launcher=1',
        f'TargetDir={PYTHON_INSTALL_DIR}',
    ], capture_output=True, timeout=300)
    try:
        os.remove(tmp)
    except Exception:
        pass
    if r.returncode not in (0, 3010):
        raise RuntimeError(f"Python 설치 실패 (코드 {r.returncode})")
    log("✅ Python 설치 완료")
    return _find_python() or os.path.join(PYTHON_INSTALL_DIR, 'python.exe')

# ── launcher.bat 생성 (Python 절대경로 사용) ────
def _write_launcher(python_exe: str):
    content = (
        '@echo off\r\n'
        'chcp 65001 > nul\r\n'
        'cd /d "%~dp0"\r\n'
        'echo.\r\n'
        'echo  웹 리서치 어시스턴트 시작 중...\r\n'
        'echo  브라우저가 자동으로 열립니다. (5-10초)\r\n'
        'echo  이 창을 닫으면 앱이 종료됩니다.\r\n'
        'echo.\r\n'
        f'"{python_exe}" -m streamlit run app.py '
        '--server.headless false --server.port 8501 '
        '--browser.gatherUsageStats false\r\n'
        'pause\r\n'
    )
    bat_path = os.path.join(INSTALL_DIR, 'launcher.bat')
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return bat_path

# ── 바탕화면 바로가기 ────────────────────────────
def _create_shortcut(target: str):
    shortcut_path = os.path.join(
        os.environ.get('USERPROFILE', os.path.expanduser('~')),
        'Desktop', '웹 리서치 어시스턴트.lnk'
    )
    working_dir = INSTALL_DIR
    ps = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut($env:USERPROFILE + "\\Desktop\\웹 리서치 어시스턴트.lnk"); '
        f'$s.TargetPath = "{target}"; '
        f'$s.WorkingDirectory = "{working_dir}"; '
        f'$s.Save()'
    )
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True)
    # 폴백: bat 직접 복사
    if r.returncode != 0 or not os.path.exists(shortcut_path):
        shutil.copy2(target, os.path.join(
            os.environ.get('USERPROFILE', os.path.expanduser('~')),
            'Desktop', '웹 리서치 어시스턴트.bat'
        ))

# ── 설치 메인 ────────────────────────────────────
def _do_install(log, done):
    try:
        log("📁  설치 폴더 생성 중...")
        os.makedirs(INSTALL_DIR, exist_ok=True)

        # 파일 복사
        for fname in APP_FILES:
            log(f"📄  복사 중: {fname}")
            shutil.copy2(_resource(fname), os.path.join(INSTALL_DIR, fname))

        # Python 확인 / 설치
        log("🐍  Python 확인 중...")
        python_exe = _find_python()
        if not python_exe:
            python_exe = _install_python(log)
        else:
            log(f"✅  Python 발견: {python_exe}")

        # 패키지 설치
        log("📦  패키지 설치 중... (1~3분)")
        req = os.path.join(INSTALL_DIR, 'requirements.txt')
        r = subprocess.run(
            [python_exe, '-m', 'pip', 'install', '-r', req, '-q'],
            capture_output=True, text=True, timeout=600
        )
        if r.returncode != 0:
            log(f"⚠️  경고: {r.stderr[:200]}")

        # launcher.bat 생성
        log("🔧  런처 생성 중...")
        launcher = _write_launcher(python_exe)

        # 바탕화면 바로가기
        log("🔗  바탕화면 바로가기 생성 중...")
        _create_shortcut(launcher)

        log("\n✅  설치 완료!")
        log("바탕화면 '웹 리서치 어시스턴트' 아이콘을 더블클릭하세요.")
        done(True)
    except Exception as e:
        import traceback
        log(f"\n❌  오류: {e}\n{traceback.format_exc()[:300]}")
        done(False)

# ── GUI ──────────────────────────────────────────
class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("웹 리서치 어시스턴트 설치")
        self.resizable(False, False)
        self.geometry("500x400")
        self.configure(bg="#1E1E2E")
        self._build_ui()
        self.after(300, self._start_install)

    def _build_ui(self):
        bg, fg, accent = "#1E1E2E", "#CDD6F4", "#89DCEB"
        tk.Label(self, text="웹 리서치 어시스턴트", font=("Segoe UI",16,"bold"),
                 bg=bg, fg=accent).pack(pady=(24,4))
        tk.Label(self, text=f"설치 경로:  {INSTALL_DIR}", font=("Segoe UI",9),
                 bg=bg, fg="#6C7086").pack(pady=(0,12))
        self.bar = ttk.Progressbar(self, mode='indeterminate', length=420)
        self.bar.pack(pady=(0,10))
        self.bar.start(12)
        frm = tk.Frame(self, bg=bg)
        frm.pack(fill='both', expand=True, padx=20, pady=(0,6))
        self.log_box = tk.Text(frm, height=12, font=("Consolas",8),
                               bg="#181825", fg=fg, relief='flat',
                               state='disabled', wrap='word')
        self.log_box.pack(fill='both', expand=True)
        self.btn = tk.Button(self, text="설치 중...", font=("Segoe UI",10),
                             bg="#313244", fg=fg, relief='flat',
                             padx=20, pady=6, command=self.destroy, state='disabled')
        self.btn.pack(pady=10)

    def _log(self, msg):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', msg+"\n")
        self.log_box.see('end')
        self.log_box.configure(state='disabled')
        self.update_idletasks()

    def _start_install(self):
        threading.Thread(
            target=_do_install,
            args=(lambda m: self.after(0, lambda: self._log(m)),
                  lambda ok: self.after(0, self._on_done if ok else self._on_fail)),
            daemon=True
        ).start()

    def _on_done(self):
        self.bar.stop(); self.bar.configure(mode='determinate', value=100)
        self.btn.configure(state='normal', text="닫기")

    def _on_fail(self):
        self.bar.stop()
        self.btn.configure(state='normal', text="닫기")
        messagebox.showerror("설치 실패", "오류가 발생했습니다.\n로그를 확인하세요.")


if __name__ == '__main__':
    app = InstallerApp()
    app.mainloop()
