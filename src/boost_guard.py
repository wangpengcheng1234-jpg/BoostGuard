# -*- coding: utf-8 -*-
"""BoostGuard — 常驻托盘的 CPU Boost 开关

运行期间关闭处理器性能提升（Boost）并把散热方式设为主动，用于降低轻载温度。
- 绿色箭头 = Boost 已恢复（正常）
- 红色箭头 = Boost 已关闭（降温）
退出时弹确认框；关闭/恢复都会弹出 Windows 系统通知。
无主窗口，仅托盘图标；配置与日志都写在 exe 同目录。
"""
import ctypes
import json
import os
import subprocess
import sys
import time
import winreg
from ctypes import wintypes

APP_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, 'frozen', False) else __file__))
STATE_FILE = os.path.join(APP_DIR, 'state.json')
LOG_FILE = os.path.join(APP_DIR, 'boost_guard.log')
ICON_GREEN = os.path.join(APP_DIR, 'boostguard.ico')
ICON_RED = os.path.join(APP_DIR, 'boostguard_red.ico')
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'BoostGuard'

SUB_PROCESSOR = '54533251-82be-4824-96c1-47b60b740d00'
PERFBOOSTMODE = 'be337238-0d82-4146-a960-4f3749d470c7'   # 0=关闭 1=启用 2=主动 3=高效主动
SYSCOOLPOL = '94d3a615-a899-4ac5-ae2b-e4d8f634367f'      # 0=被动 1=主动

si = subprocess.STARTUPINFO()
si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
FLAGS = subprocess.CREATE_NO_WINDOW


# ---------------- 基础工具 ----------------
def run(cmd, timeout=25):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout,
                              startupinfo=si, creationflags=FLAGS,
                              encoding='gbk', errors='ignore')
    except Exception:
        return None


def log(msg):
    try:
        line = time.strftime('%Y-%m-%d %H:%M:%S') + '  ' + msg + '\n'
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 256 * 1024:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                keep = f.readlines()[-300:]
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.writelines(keep)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(data):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def unhide():
    for s in (PERFBOOSTMODE, SYSCOOLPOL):
        run(['powercfg', '-attributes', SUB_PROCESSOR, s, '-ATTRIB_HIDE'])


def read_val(setting, dc=False):
    """读取电源设置当前值；OEM 电源方案里部分项被隐藏，需先取消隐藏"""
    unhide()
    r = run(['powercfg', '/q', 'SCHEME_CURRENT', SUB_PROCESSOR, setting])
    key = ('直流', 'DC') if dc else ('交流', 'AC')
    for line in (r.stdout or '').splitlines():
        if (key[0] in line or key[1] in line) and '0x' in line:
            try:
                return int(line.split('0x')[-1].strip(), 16)
            except Exception:
                return None
    return None


def write_val(setting, ac, dc):
    ok1 = run(['powercfg', '/setacvalueindex', 'SCHEME_CURRENT',
               SUB_PROCESSOR, setting, str(ac)])
    ok2 = run(['powercfg', '/setdcvalueindex', 'SCHEME_CURRENT',
               SUB_PROCESSOR, setting, str(dc)])
    run(['powercfg', '/setactive', 'SCHEME_CURRENT'])
    return bool(ok1 and ok2 and ok1.returncode == 0 and ok2.returncode == 0)


def is_boost_off():
    return read_val(PERFBOOSTMODE) == 0


# ---------------- 状态切换 ----------------
def boost_off():
    """关闭 Boost 并把散热方式设为主动；首次调用时保存原值"""
    st = load_state()
    if st.get('original') is None:
        cur = read_val(PERFBOOSTMODE)
        st['original'] = cur if cur not in (None, 0) else 2
        st['original_dc'] = read_val(PERFBOOSTMODE, dc=True) or st['original']
        st['cool'] = read_val(SYSCOOLPOL)
        st['cool_dc'] = read_val(SYSCOOLPOL, dc=True)
        save_state(st)
    write_val(PERFBOOSTMODE, 0, 0)
    write_val(SYSCOOLPOL, 1, 1)
    log('Boost 已关闭（原值 %s），散热方式=主动' % st.get('original'))


def boost_restore():
    st = load_state()
    if st.get('original') is None:
        return False
    write_val(PERFBOOSTMODE, st['original'], st.get('original_dc', st['original']))
    if st.get('cool') is not None:
        write_val(SYSCOOLPOL, st['cool'], st.get('cool_dc', st['cool']))
    log('Boost 已恢复为 %s' % st['original'])
    return True


# ---------------- 托盘界面 ----------------
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

# 显式声明函数签名，避免 64 位句柄被截断为 32 位（会导致菜单文字异常/渲染错乱）
HMENU = ctypes.c_void_p
LRESULT = ctypes.c_longlong

user32.CreatePopupMenu.restype = HMENU
user32.CreatePopupMenu.argtypes = []
user32.DestroyMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [HMENU]
user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [HMENU, wintypes.UINT, ctypes.c_ulonglong, wintypes.LPCWSTR]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.MessageBoxW.restype = ctypes.c_int
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]

user32.RegisterClassW.restype = ctypes.c_ushort   # ATOM (WORD)
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, HMENU, wintypes.HINSTANCE,
                                   wintypes.LPVOID]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.ExtractIconExW.restype = wintypes.UINT
shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                   ctypes.POINTER(wintypes.HICON),
                                   ctypes.POINTER(wintypes.HICON), wintypes.UINT]

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.GetLastError.argtypes = []

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_QUERYENDSESSION = 0x0011
WM_APP = 0x8000
WM_TRAYMSG = WM_APP + 1
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10

# MessageBox 常量
MB_OK = 0x0000
MB_OKCANCEL = 0x0001
MB_YESNO = 0x0004
MB_ICONWARNING = 0x0030
MB_ICONQUESTION = 0x0020
IDOK = 1
IDYES = 6


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT),
        ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT),
        ('hIcon', wintypes.HICON),
        ('szTip', wintypes.WCHAR * 128),
        ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD),
        ('szInfo', wintypes.WCHAR * 256),
        ('uVersion', wintypes.UINT),
        ('szInfoTitle', wintypes.WCHAR * 64),
        ('dwInfoFlags', wintypes.DWORD),
        ('guidItem', ctypes.c_byte * 16),
        ('hBalloonIcon', wintypes.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ('style', wintypes.UINT),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HANDLE),
        ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR),
    ]


# 依赖结构体的签名，在结构体定义之后再绑定
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]


ID_TOGGLE = 1
ID_QUIT = 2
ID_AUTOSTART = 3

nid = NOTIFYICONDATAW()
hwnd_global = None
nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)


def load_file_icon(path):
    if path and os.path.exists(path):
        h = user32.LoadImageW(None, path, 1, 0, 0, 0x10 | 0x20)   # IMAGE_ICON|LOADFROMFILE|DEFAULTSIZE
        if h:
            return h
    return None


def load_exe_icon():
    if getattr(sys, 'frozen', False):
        large, small = ctypes.c_void_p(), ctypes.c_void_p()
        n = shell32.ExtractIconExW(sys.executable, 0,
                                   ctypes.byref(large), ctypes.byref(small), 1)
        if n and small.value:
            return wintypes.HICON(small.value)
        if n and large.value:
            return wintypes.HICON(large.value)
    return None


def load_icon(boost_off):
    """绿色（向下）= Boost 已关闭（降温）；红色（向上）= Boost 已恢复（正常）"""
    h = load_file_icon(ICON_GREEN if boost_off else ICON_RED)
    if h:
        return h
    h = load_exe_icon()
    if h:
        return h
    return user32.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))


def set_tray_icon(boost_off):
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYMSG
    nid.hIcon = load_icon(boost_off)
    nid.szTip = 'BoostGuard — Boost 已关闭（降温）' if boost_off else 'BoostGuard — Boost 已恢复'
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except Exception:
        return False


def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                exe = os.path.abspath(sys.executable if getattr(sys, 'frozen', False)
                                      else os.path.join(APP_DIR, 'BoostGuard.exe'))
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        log('开机自启 = %s' % ('开' if on else '关'))
        return True
    except Exception:
        return False


def notify(title, text):
    """系统级通知（托盘气泡，Win10/11 会呈现为系统通知卡片）"""
    n = NOTIFYICONDATAW()
    n.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    n.hWnd = hwnd_global
    n.uID = 1
    n.uFlags = NIF_INFO
    n.szInfo = text[:255]
    n.szInfoTitle = title[:63]
    n.dwInfoFlags = 0x1          # NIIF_INFO
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(n))


def show_menu(hwnd):
    menu = user32.CreatePopupMenu()
    off = is_boost_off()
    user32.AppendMenuW(menu, 0x0000, 0,
                       '当前状态：Boost 已关闭（降温）' if off else '当前状态：Boost 已恢复')
    user32.AppendMenuW(menu, 0x0000, 0, '单击图标即可切换')
    user32.AppendMenuW(menu, 0x0000, 0, '')
    user32.AppendMenuW(menu, 0x0000, ID_TOGGLE, '恢复 Boost' if off else '关闭 Boost')
    user32.AppendMenuW(menu, 0x0008 if autostart_enabled() else 0x0000,
                       ID_AUTOSTART, '开机自启')
    user32.AppendMenuW(menu, 0x0000, 0, '')
    user32.AppendMenuW(menu, 0x0000, ID_QUIT, '退出')

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, hwnd, None)
    user32.PostMessageW(hwnd, 0, 0, 0)
    user32.DestroyMenu(menu)
    return cmd


def do_toggle():
    if is_boost_off():
        boost_restore()
        set_tray_icon(boost_off=False)   # 恢复 Boost → 红色向上
        notify('CPU Boost 已恢复', '处理器性能提升已重新启用，温度会回到原来的水平。')
    else:
        boost_off()
        set_tray_icon(boost_off=True)    # 关闭 Boost → 绿色向下
        notify('CPU Boost 已关闭', '处理器性能提升已关闭，散热方式切换为主动降温。')


def do_autostart():
    on = not autostart_enabled()
    if set_autostart(on):
        notify('开机自启已开启' if on else '开机自启已关闭',
               'BoostGuard 会在登录后自动运行。' if on else '下次登录不再自动启动。')


def confirm_exit(hwnd):
    """退出确认框：确定退出 / 取消"""
    r = user32.MessageBoxW(hwnd,
                           '确定要退出 BoostGuard 吗？\n退出后将恢复 CPU Boost 设置。',
                           'BoostGuard', MB_YESNO | MB_ICONQUESTION)
    return r == IDYES


def quit_app(hwnd):
    boost_restore()
    notify('CPU Boost 已恢复', '程序退出，已还原处理器加速设置。')
    time.sleep(0.6)
    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    user32.DestroyWindow(hwnd)


def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAYMSG:
        if lparam == WM_RBUTTONUP:
            cmd = show_menu(hwnd)
            if cmd == ID_TOGGLE:
                do_toggle()
            elif cmd == ID_AUTOSTART:
                do_autostart()
            elif cmd == ID_QUIT:
                if confirm_exit(hwnd):
                    quit_app(hwnd)
        elif lparam == WM_LBUTTONUP:          # 单击图标即可切换模式
            do_toggle()
        return 0
    if msg == WM_QUERYENDSESSION:
        boost_restore()          # 关机/重启前先还原，避免设置残留
        return 1
    if msg == WM_CLOSE:
        if confirm_exit(hwnd):
            quit_app(hwnd)
        return 0
    if msg == WM_COMMAND:
        cmd = wparam & 0xFFFF
        if cmd == ID_TOGGLE:
            do_toggle()
        elif cmd == ID_AUTOSTART:
            do_autostart()
        elif cmd == ID_QUIT:
            if confirm_exit(hwnd):
                quit_app(hwnd)
        return 0
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def single_instance():
    h = kernel32.CreateMutexW(None, False, 'Local\\BoostGuard_SingleInstance')
    if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
        return None
    return h


def main():
    if '--selftest' in sys.argv:
        boost_off()
        time.sleep(3)
        boost_restore()
        log('自检完成')
        return

    if not single_instance():
        return

    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = WNDPROC(wnd_proc)
    wc.hInstance = hinst
    wc.lpszClassName = 'BoostGuardWnd'
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, 'BoostGuardWnd', 'BoostGuard', 0,
                                  0, 0, 0, 0, None, None, hinst, None)
    global hwnd_global
    hwnd_global = hwnd

    # 启动即关闭 Boost → 绿色向下图标
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYMSG
    nid.hIcon = load_icon(boost_off=True)
    nid.szTip = 'BoostGuard — Boost 已关闭（降温）'
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    boost_off()
    notify('CPU Boost 已关闭', '已关闭处理器性能提升，散热方式设为主动。右键托盘可恢复或退出。')

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))


if __name__ == '__main__':
    main()
