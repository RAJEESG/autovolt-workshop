"""
AutoVolt Cloud - SaaS Master Admin HQ Launcher
Launches the SaaS Master Admin HQ interface in standalone app window (Port 8500).
"""
import os
import sys
import time
import socket
import subprocess
import webbrowser

PORT = 8500
APP_URL = f"http://localhost:{PORT}"
APP_TITLE = "AutoVolt Cloud Master HQ"

CANDIDATE_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
    r"C:\Users\Administrator\Desktop\Project_20260720_120758_194\auto_electric_workshop_manager",
]

def find_project_dir():
    for d in CANDIDATE_DIRS:
        if os.path.exists(os.path.join(d, "saas_admin_app.py")):
            return os.path.abspath(d)
    return CANDIDATE_DIRS[-1]

def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.8)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def start_server_if_needed(project_dir: str):
    if is_port_listening(PORT):
        return True

    py_exec = sys.executable
    if "python.exe" not in py_exec.lower() and "pythonw.exe" not in py_exec.lower():
        fallback_py = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\pythonw.exe"
        if not os.path.exists(fallback_py):
            fallback_py = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
        py_exec = fallback_py

    cmd = [py_exec, "-m", "uvicorn", "saas_admin_app:app", "--host", "0.0.0.0", "--port", str(PORT)]

    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000

    subprocess.Popen(
        cmd,
        cwd=project_dir,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True
    )

    for _ in range(25):
        time.sleep(0.4)
        if is_port_listening(PORT):
            return True
    return False

def main():
    proj_dir = find_project_dir()
    start_server_if_needed(proj_dir)

    browser = find_browser()
    if browser:
        app_arg = f"--app={APP_URL}"
        subprocess.Popen([browser, app_arg, "--window-size=1280,820"])
    else:
        webbrowser.open(APP_URL)

if __name__ == "__main__":
    main()
