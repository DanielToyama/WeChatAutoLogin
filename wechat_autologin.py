#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat_autologin.py — 微信（Weixin/WeChat）自动登录辅助程序

流程：
  1. 开机自启后等待微信进程出现（Weixin.exe / WeChat.exe）。
  2. 检测到登录窗口后，用 PrintWindow 抓取窗口画面，
     用模板匹配（greenButton.jpg）定位绿色「登录」按钮。
  3. 点击前：记录/核对微信窗口位置（rect），检查微信是否在最前方；
     不在最前方则尝试置顶（restore + SetForegroundWindow + 附加线程输入）。
  4. 点击前重新抓图核对按钮位置，然后模拟鼠标点击按钮中心。
  5. 点击后轮询检测窗口大小变化（登录成功后窗口通常会显著变大，
     或登录窗口关闭、出现更大的主窗口），确认登录成功。

用法：
  python wechat_autologin.py            # 正常运行一次
  python wechat_autologin.py --dry-run  # 只检测不点击（安全测试）
  python wechat_autologin.py --watch    # 失败后循环重试（配合开机自启）
  参数均可通过 config.json 调整。

依赖：pip install pywin32 opencv-python numpy psutil pillow
"""

import argparse
import ctypes
import json
import logging
import os
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler

import cv2
import numpy as np
import psutil
import win32api
import win32con
import win32event
import winerror
import win32gui
import win32process
import win32ui

if getattr(sys, "frozen", False):
    # PyInstaller 单文件 exe：APP_DIR = exe 所在目录（配置/模板/日志放这里，
    # 用户可自行替换 greenButton.jpg 或放一个 config.json 覆盖默认值）；
    # BUNDLE_DIR = PyInstaller 解包出的内嵌资源目录（绿色按钮模板的兜底来源）。
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    # 正常的 python 脚本运行
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR

DEFAULT_CONFIG = {
    # 微信进程名（新版 4.x 是 Weixin.exe，旧版是 WeChat.exe）
    "process_names": ["Weixin.exe", "WeChat.exe"],
    # 窗口标题关键字（用于过滤归属微信的顶层窗口）
    "title_keywords": ["微信", "Weixin", "WeChat"],
    # 绿色登录按钮模板图片（与脚本同目录）
    "template_file": "greenButton.jpg",
    # 模板匹配阈值（1.0 = 完全一致）
    "match_threshold": 0.85,
    # 多尺度匹配（应对不同 DPI 缩放；1.0 为截图时的缩放）
    "match_scales": [0.75, 0.8, 0.9, 1.0, 1.1, 1.2, 1.25, 1.33, 1.5],
    # 等待微信进程出现的最大秒数
    "process_wait_timeout": 300,
    # 进程出现后等待登录窗口的最大秒数
    "window_wait_timeout": 120,
    # 一直看不到任何微信窗口时提前放弃的秒数（已登录/最小化到托盘的情况）
    "no_window_grace": 8,
    # 轮询间隔（秒）
    "poll_interval": 1.0,
    # 最大点击尝试次数
    "max_click_attempts": 4,
    # 点击前置顶后的等待秒数（让窗口重绘，避免点到旧位置）
    "pre_click_delay": 0.6,
    # 点击后检测登录结果的超时秒数
    "post_click_timeout": 15,
    # 验证轮询间隔（秒）
    "verify_poll_interval": 0.5,
    # 窗口面积增长多少比例视为“登录成功变大”（1.2 = 增长 20%）
    "growth_ratio": 1.2,
    # 忽略面积小于该像素值的窗口（避免匹配到无关小窗口）
    "min_window_area": 20000,
    # 发现比登录页大得多的微信窗口即认为已登录，立即退出（避免误点主窗口）
    "login_max_area": 350000,
    # 失败后循环重试（--watch），间隔秒数
    "watch": False,
    "watch_interval": 30,
    # 日志
    "log_file": "wechat_autologin.log",
    "log_max_bytes": 262144,
}


def load_config():
    """读取 exe/脚本 旁边的 config.json（覆盖默认值），没有则用默认。"""
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(APP_DIR, "config.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except Exception as e:
            logging.warning("config.json 读取失败，使用默认配置: %s", e)
    return cfg


def setup_logging(cfg):
    log_path = os.path.join(APP_DIR, cfg["log_file"])
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        fh = RotatingFileHandler(log_path, maxBytes=cfg.get("log_max_bytes", 262144),
                                 backupCount=1, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as e:
        print("日志文件初始化失败: %s", e)
    # pythonw 下没有控制台，跳过
    if sys.stderr is not None and hasattr(sys.stderr, "write"):
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)


def set_dpi_awareness():
    """让本进程按物理像素工作，保证坐标/截图/点击一致。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def acquire_single_instance():
    """防止多个实例同时点击。返回 True 表示本实例拥有锁。"""
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = "default"
    name = "WeChatAutoLogin_%s" % user
    try:
        mutex = win32event.CreateMutex(None, False, name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            logging.info("已有另一个实例在运行，本实例退出。")
            return False
        return True
    except Exception as e:
        logging.warning("单实例锁创建失败（继续运行）: %s", e)
        return True


# ---------------------------------------------------------------- 进程/窗口

def find_wechat_processes(cfg):
    names = {n.lower() for n in cfg.get("process_names", [])}
    found = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = p.info.get("name") or ""
            if name.lower() in names:
                found.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(set(found))


def process_alive(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running()
    except psutil.NoSuchProcess:
        return False


def wait_for_process(cfg):
    deadline = time.time() + cfg["process_wait_timeout"]
    while True:
        pids = find_wechat_processes(cfg)
        if pids:
            return pids
        if time.time() >= deadline:
            return None
        time.sleep(cfg["poll_interval"])


def wechat_windows(pids, cfg):
    """枚举 pid 集合中、标题匹配的可见顶层窗口。"""
    kw = [k.lower() for k in cfg.get("title_keywords", [])]
    out = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return True
        if pids and pid not in pids:
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if kw and not (title and any(k in title.lower() for k in kw)):
            return True
        try:
            r = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True
        if r[2] - r[0] <= 0 or r[3] - r[1] <= 0:
            return True
        out.append({"hwnd": hwnd, "pid": pid, "title": title, "rect": r,
                    "w": r[2] - r[0], "h": r[3] - r[1]})
        return True

    win32gui.EnumWindows(cb, None)
    return out


# ---------------------------------------------------------------- 截图/匹配

def capture_window(hwnd):
    """用 PrintWindow(PW_RENDERFULLCONTENT) 抓取窗口内容（含被遮挡/其他显示器）。"""
    try:
        r = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None, None
    w, h = r[2] - r[0], r[3] - r[1]
    if w <= 0 or h <= 0 or w > 8000 or h > 8000:
        return None, None
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = save_dc = bmp = None
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)
        ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        buf = bmp.GetBitmapBits(True)
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(info["bmHeight"], info["bmWidth"], 4)
        arr = np.ascontiguousarray(arr[:, :, :3])  # BGRA -> BGR
        return arr, r
    except Exception as e:
        logging.error("窗口截图失败 hwnd=%d: %s", hwnd, e)
        return None, None
    finally:
        for obj in (save_dc, mfc_dc):
            try:
                obj.DeleteDC()
            except Exception:
                pass
        try:
            win32gui.DeleteObject(bmp.GetHandle())
        except Exception:
            pass
        try:
            win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass


def match_template(img, tpl, scales, threshold):
    """多尺度模板匹配，返回 (左上角坐标, 得分, 缩放比) 或 (None, 最高分, 1.0)。"""
    if img is None or tpl is None or img.size == 0 or tpl.size == 0:
        return None, -1.0, 1.0
    img_g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl_g = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    ih, iw = img_g.shape[:2]
    th, tw = tpl_g.shape[:2]
    best_pos, best_score, best_scale = None, -1.0, 1.0
    for s in scales:
        w2 = max(1, int(round(tw * s)))
        h2 = max(1, int(round(th * s)))
        if h2 > ih or w2 > iw:
            continue
        t = cv2.resize(tpl_g, (w2, h2), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        res = cv2.matchTemplate(img_g, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, mx_loc = cv2.minMaxLoc(res)
        if mx > best_score:
            best_score, best_pos, best_scale = mx, mx_loc, s
    if best_score >= threshold:
        return best_pos, best_score, best_scale
    return None, best_score, best_scale


def find_login_window(cfg, pids, tpl):
    """轮询查找显示绿色登录按钮的窗口。返回窗口信息 dict 或 None。"""
    deadline = time.time() + cfg["window_wait_timeout"]
    no_win_since = None
    while True:
        wins = wechat_windows(pids, cfg)
        if wins:
            no_win_since = None
            # 已登录时主窗口通常远大于登录页；发现即视为无需操作，立即退出
            if cfg.get("login_max_area", 350000) > 0:
                big = [w for w in wins
                       if w["w"] * w["h"] >= cfg.get("login_max_area", 350000)]
                if big:
                    w = big[0]
                    logging.info("发现较大的微信窗口 %dx%d（可能已登录），无需操作。", w["w"], w["h"])
                    return None
            for w in wins:
                if w["w"] * w["h"] < cfg["min_window_area"]:
                    continue
                img, rect = capture_window(w["hwnd"])
                if img is None:
                    continue
                pos, score, scale = match_template(img, tpl, cfg["match_scales"], cfg["match_threshold"])
                if pos is not None:
                    w.update(img=img, match=pos, score=score, scale=scale)
                    return w
        else:
            if no_win_since is None:
                no_win_since = time.time()
            if time.time() - no_win_since >= cfg["no_window_grace"]:
                logging.info("连续 %.0f 秒没有任何可见微信窗口，认为已登录或未显示登录页。", cfg["no_window_grace"])
                return None
        if time.time() >= deadline:
            logging.info("超过 %.0f 秒未找到登录页（可能已登录或登录页样式已变化）。", cfg["window_wait_timeout"])
            return None
        time.sleep(cfg["poll_interval"])


# ---------------------------------------------------------------- 置顶/点击

def foreground_info():
    hwnd = win32gui.GetForegroundWindow()
    try:
        title = win32gui.GetWindowText(hwnd) or ""
    except Exception:
        title = ""
    return hwnd, title


def raise_window(hwnd):
    """把微信窗口带到最前方。返回是否成功。"""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:
        pass
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    # 附加线程输入技巧（绕过 Windows 前台锁）
    try:
        cur_tid = win32api.GetCurrentThreadId()
        fg_hwnd = win32gui.GetForegroundWindow()
        attached = []
        if fg_hwnd:
            fg_tid = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
            wx_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
            if fg_tid and fg_tid != cur_tid:
                win32process.AttachThreadInput(cur_tid, fg_tid, True)
                attached.append(fg_tid)
            if wx_tid and wx_tid != cur_tid:
                win32process.AttachThreadInput(cur_tid, wx_tid, True)
                attached.append(wx_tid)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        except Exception:
            pass
        win32gui.SetForegroundWindow(hwnd)
        for t in attached:
            try:
                win32process.AttachThreadInput(cur_tid, t, False)
            except Exception:
                pass
    except Exception as e:
        logging.warning("置顶过程异常: %s", e)
    return win32gui.GetForegroundWindow() == hwnd


def sendinput_click(x, y):
    """用 SendInput 一次性原子投递 MOVE+LEFTDOWN+LEFTUP（同一次调用内完成，
    消除鼠标晃动/时序竞争导致的丢点击）。仍需移动光标，但点击不会丢。
    坐标支持多显示器（VIRTUALDESK）。"""
    u = ctypes.windll.user32
    u.SendInput.restype = ctypes.c_uint
    u.GetSystemMetrics.restype = ctypes.c_int
    u.GetSystemMetrics.argtypes = [ctypes.c_int]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    # 虚拟桌面范围（含多显示器负坐标）
    vx = u.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
    vy = u.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
    vw = u.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
    vh = u.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
    xs = int((int(x) - vx) * 65535.0 / vw)
    ys = int((int(y) - vy) * 65535.0 / vh)

    n = 3
    arr = (INPUT * n)()
    base = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_MOVE
    for i, extra in enumerate((0, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)):
        arr[i].type = 0
        arr[i].mi.dx = xs
        arr[i].mi.dy = ys
        arr[i].mi.dwFlags = base | extra
    sent = u.SendInput(n, arr, ctypes.sizeof(INPUT))
    time.sleep(0.05)
    return sent == n


# ---------------------------------------------------------------- 触屏注入

# 触屏注入不移动鼠标光标，鼠标晃动也不会丢点击。Win10 1607+ 可用。
POINTER_FLAG_INRANGE = 0x0002
POINTER_FLAG_INCONTACT = 0x0004
POINTER_FLAG_DOWN = 0x0100
POINTER_FLAG_UPDATE = 0x0400
POINTER_FLAG_UP = 0x0200
PT_TOUCH = 2
TOUCH_FEEDBACK_DEFAULT = 1
TOUCH_MASK_CONTACTAREA = 0x0001


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", ctypes.c_uint32),
        ("pointerId", ctypes.c_uint32),
        ("frameId", ctypes.c_uint32),
        ("pointerFlags", ctypes.c_uint32),
        ("sourceDevice", ctypes.c_void_p),
        ("hwndTarget", ctypes.c_void_p),
        ("ptPixelLocation", _POINT),
        ("ptHimetricLocation", _POINT),
        ("ptPixelLocationRaw", _POINT),
        ("ptHimetricLocationRaw", _POINT),
        ("dwTime", ctypes.c_ulong),
        ("historyCount", ctypes.c_uint32),
        ("InputData", ctypes.c_int32),
        ("dwKeyStates", ctypes.c_ulong),
        ("PerformanceCount", ctypes.c_ulonglong),
        ("ButtonChangeType", ctypes.c_int32),
    ]


class _POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", _POINTER_INFO),
        ("touchFlags", ctypes.c_uint32),
        ("touchMask", ctypes.c_uint32),
        ("rcContact", _RECT),
        ("rcContactRaw", _RECT),
        ("orientation", ctypes.c_uint32),
        ("pressure", ctypes.c_uint32),
    ]


def touch_click(x, y, hold_ms=80):
    """用触屏注入在屏幕坐标 (x, y) 处点一下，不移动鼠标光标。成功返回 True。"""
    user32 = ctypes.windll.user32
    user32.InitializeTouchInjection.restype = ctypes.c_bool
    user32.InitializeTouchInjection.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    user32.InjectTouchInput.restype = ctypes.c_bool
    user32.InjectTouchInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(_POINTER_TOUCH_INFO)]

    if not user32.InitializeTouchInjection(1, TOUCH_FEEDBACK_DEFAULT):
        logging.error("InitializeTouchInjection 失败 (error=%d)", ctypes.get_last_error() or 0)
        return False

    info = _POINTER_TOUCH_INFO()
    pi = info.pointerInfo
    pi.pointerType = PT_TOUCH
    pi.pointerId = 0
    pi.frameId = 0
    pi.ptPixelLocation.x = int(x)
    pi.ptPixelLocation.y = int(y)
    pi.hwndTarget = None  # 0 = 由系统按坐标命中测试决定目标窗口
    info.touchMask = TOUCH_MASK_CONTACTAREA
    info.rcContact = _RECT(int(x) - 2, int(y) - 2, int(x) + 2, int(y) + 2)

    # 按下
    pi.pointerFlags = POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_DOWN
    if not user32.InjectTouchInput(1, ctypes.byref(info)):
        logging.error("InjectTouchInput(DOWN) 失败 (error=%d)", ctypes.get_last_error() or 0)
        return False
    time.sleep(hold_ms / 1000.0)
    # 更新帧（部分 UI 需要才会触发点击）
    pi.pointerFlags = POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_UPDATE
    user32.InjectTouchInput(1, ctypes.byref(info))
    time.sleep(0.02)
    # 抬起（失败则重试几次，避免触摸卡住）
    pi.pointerFlags = POINTER_FLAG_INRANGE | POINTER_FLAG_UP
    for _ in range(3):
        if user32.InjectTouchInput(1, ctypes.byref(info)):
            return True
        time.sleep(0.05)
    logging.error("InjectTouchInput(UP) 失败 (error=%d)", ctypes.get_last_error() or 0)
    return False


def postmessage_click(hwnd, x, y):
    """把鼠标按下/抬起消息直接投递给指定窗口（PostMessage 异步）。
    优点：完全不移动鼠标光标、不依赖前台/遮挡（消息直接发给 hwnd）。
    注意：坐标会换算成窗口客户区坐标；部分 UI（如 Chromium）需要先收到 WM_MOUSEMOVE。"""
    try:
        pt = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
    except Exception:
        return False
    lparam = win32api.MAKELONG(pt[0], pt[1])
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.06)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
    time.sleep(0.03)
    return True


def perform_click(hwnd, cx, cy, cfg):
    """按配置选择点击方式：
    message = 直接向窗口投递点击消息（不动鼠标、不抢前台，推荐）
    touch   = 触屏注入（不动鼠标；部分环境不支持会自动回退）
    mouse   = 鼠标模拟（SetCursorPos + mouse_event，最通用）
    """
    method = cfg.get("click_method", "message")
    if method == "message":
        if postmessage_click(hwnd, cx, cy):
            logging.info("已通过窗口消息投递点击 (%d, %d)（鼠标光标未移动）", int(cx), int(cy))
            return True
        logging.warning("窗口消息投递失败，回退为 SendInput 鼠标点击。")
    elif method == "touch":
        if touch_click(cx, cy):
            logging.info("已通过触屏注入点击 (%d, %d)（鼠标光标未移动）", int(cx), int(cy))
            return True
        logging.warning("触屏注入失败，回退为 SendInput 鼠标点击。")
    if sendinput_click(cx, cy):
        logging.info("已通过 SendInput 原子鼠标点击 (%d, %d)", int(cx), int(cy))
        return True
    logging.error("SendInput 点击也失败了。")
    return False


# ---------------------------------------------------------------- 结果验证

def verify_login(cfg, login_pid, login_hwnd, before_rect):
    """点击后轮询，按窗口大小变化判断登录是否成功。返回 (bool, 说明)。"""
    bw = before_rect[2] - before_rect[0]
    bh = before_rect[3] - before_rect[1]
    before_area = bw * bh
    deadline = time.time() + cfg["post_click_timeout"]
    while time.time() < deadline:
        wins = wechat_windows({login_pid}, cfg)
        visible = [w for w in wins]
        login_still = any(w["hwnd"] == login_hwnd for w in visible)
        big = [w for w in visible if (w["w"] * w["h"]) >= before_area * cfg["growth_ratio"]]
        if big:
            w = big[0]
            msg = "窗口变大: %dx%d -> %dx%d（登录成功）" % (bw, bh, w["w"], w["h"])
            logging.info(msg)
            return True, msg
        if not login_still:
            if process_alive(login_pid):
                msg = "登录窗口已关闭，微信进程仍在（登录成功或转入主窗口/托盘）"
                logging.info(msg)
                return True, msg
            logging.warning("登录窗口关闭且进程已退出。")
            return False, "登录窗口关闭且进程退出"
        time.sleep(cfg["verify_poll_interval"])
    return False, "超时未观察到窗口大小变化"


# ---------------------------------------------------------------- 主流程

def run_once(cfg, tpl, dry_run=False):
    pids = wait_for_process(cfg)
    if not pids:
        logging.warning("超过 %.0f 秒未发现微信进程（%s），退出。",
                        cfg["process_wait_timeout"], "/".join(cfg["process_names"]))
        return 0  # 微信没开，不算错误（开机自启场景下交给 watch 模式）

    login = find_login_window(cfg, pids, tpl)
    if login is None:
        return 0  # 没找到登录页 = 可能已登录，无需操作

    hwnd = login["hwnd"]
    pid = login["pid"]
    fg_hwnd, fg_title = foreground_info()
    logging.info("发现登录窗口 hwnd=%d 标题=%r rect=%s 匹配得分=%.3f 缩放=%.2f",
                 hwnd, login["title"], login["rect"], login["score"], login["scale"])
    logging.info("微信在最前方: %s（当前前台: hwnd=%d 标题=%r）",
                 "是" if fg_hwnd == hwnd else "否", fg_hwnd, fg_title)

    for attempt in range(1, cfg["max_click_attempts"] + 1):
        # 点击前重新抓图核对按钮位置（窗口可能移动/内容变化）
        img, rect = capture_window(hwnd)
        cur_pos, cur_score, cur_scale = None, -1.0, 1.0
        if img is not None:
            cur_pos, cur_score, cur_scale = match_template(img, tpl, cfg["match_scales"], cfg["match_threshold"])
        if cur_pos is None:
            logging.info("第 %d 次尝试：登录按钮已不可见（窗口可能已开始切换）。", attempt)
            ok, why = verify_login(cfg, pid, hwnd, rect if rect else login["rect"])
            if ok:
                return 0
            break
        # 记录点击前窗口位置
        logging.info("第 %d 次尝试：微信窗口位置 rect=%s 大小=%dx%d", attempt, rect, rect[2]-rect[0], rect[3]-rect[1])

        if dry_run:
            fg_hwnd2, fg_title2 = foreground_info()
            tpl_h, tpl_w = tpl.shape[:2]
            cx = rect[0] + cur_pos[0] + (tpl_w * cur_scale) / 2.0
            cy = rect[1] + cur_pos[1] + (tpl_h * cur_scale) / 2.0
            logging.info("[dry-run] 将点击屏幕坐标 (%d, %d)，得分 %.3f；微信最前方=%s；点击后预期窗口 > %dx%d",
                         int(cx), int(cy), cur_score,
                         "是" if fg_hwnd2 == hwnd else "否",
                         int((rect[2]-rect[0]) * cfg["growth_ratio"]), int((rect[3]-rect[1]) * cfg["growth_ratio"]))
            return 0

        # 置顶微信窗口（若不在最前方）——message 模式直接把点击消息投递给窗口句柄，
        # 与前台/z序/遮挡无关，无需置顶、不抢焦点；仅在窗口最小化时静默还原。
        need_front = win32gui.GetForegroundWindow() != hwnd
        if need_front:
            if cfg.get("click_method", "message") == "message":
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                    logging.info("微信窗口处于最小化，已静默还原（不置顶、不抢焦点）")
                logging.info("微信不在最前方（message 模式无需置顶，直接投递点击消息）")
            else:
                ok = raise_window(hwnd)
                logging.info("微信不在最前方，尝试置顶 -> %s", "成功" if ok else "失败（继续尝试点击）")
                time.sleep(cfg["pre_click_delay"])
        else:
            logging.info("微信已在最前方，直接点击。")

        # 置顶后重抓一次，用最新位置点击
        img2, rect2 = capture_window(hwnd)
        pos2, score2, scale2 = None, -1.0, 1.0
        if img2 is not None:
            pos2, score2, scale2 = match_template(img2, tpl, cfg["match_scales"], cfg["match_threshold"])
        if pos2 is None:
            logging.info("点击前按钮消失，先验证是否已登录...")
            ok, why = verify_login(cfg, pid, hwnd, rect2 if rect2 else rect)
            if ok:
                return 0
            continue
        tpl_h, tpl_w = tpl.shape[:2]
        cx = rect2[0] + pos2[0] + (tpl_w * scale2) / 2.0
        cy = rect2[1] + pos2[1] + (tpl_h * scale2) / 2.0
        # 点击前确认按钮位置没有被其他窗口遮挡（仅对需要“真实命中”的 mouse/touch 有效；
        # message 模式直接把消息发给指定窗口，不存在点错窗口的问题）
        method = cfg.get("click_method", "message")
        hwnd_at = 0
        point_ok = True
        if method != "message":
            point_ok = False
            for _ in range(3):
                try:
                    hwnd_at = win32gui.WindowFromPoint((int(cx), int(cy)))
                except Exception:
                    hwnd_at = 0
                if hwnd_at == hwnd or (hwnd_at and win32gui.IsChild(hwnd, hwnd_at)):
                    point_ok = True
                    break
                logging.warning("第 %d 次尝试：按钮位置 (%d,%d) 处是其他窗口 hwnd=%d，再次置顶微信...",
                                attempt, int(cx), int(cy), hwnd_at)
                raise_window(hwnd)
                time.sleep(cfg["pre_click_delay"])
        if not point_ok:
            logging.warning("多次置顶后按钮位置仍被其他窗口(hwnd=%d)占据，本次跳过点击。", hwnd_at)
            continue
        perform_click(hwnd, cx, cy, cfg)
        logging.info("已点击绿色登录按钮: 屏幕 (%d, %d)  窗口 rect=%s", int(cx), int(cy), rect2)

        ok, why = verify_login(cfg, pid, hwnd, rect2)
        if ok:
            logging.info("=== 登录成功（第 %d 次尝试）===", attempt)
            return 0
        logging.warning("第 %d 次尝试未观察到登录变化: %s", attempt, why)
        time.sleep(cfg["poll_interval"])

    logging.error("=== 自动登录失败：%d 次尝试后仍未观察到窗口变化 ===", cfg["max_click_attempts"])
    return 1


# ---------------------------------------------------------------- 交互菜单 / 自启动管理

APP_GITHUB_URL = "https://github.com/danieltoyama/WeChatAutoLogin"
AUTOSTART_TASK = "WeChatAutoLogin"


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_elevated(extra_flags):
    """用 runas 重新启动自己（弹 UAC），执行 extra_flags 指定的管理操作。"""
    exe = sys.executable
    params = []
    if not getattr(sys, "frozen", False):
        params.append('"%s"' % os.path.abspath(__file__))
    params += [a if a.startswith("--") else '"%s"' % a for a in extra_flags]
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe,
                                                  " ".join(params), APP_DIR, 1)
        return ret > 32
    except Exception as e:
        logging.error("提权失败: %s", e)
        return False


def _run_hidden(argv):
    """后台运行命令并捕获输出（不弹黑窗）。返回 CompletedProcess 或 None。"""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        logging.warning("命令执行失败 %s: %s", argv, e)
        return None


def autostart_state():
    """返回 (计划任务是否存在?, 启动文件夹匹配条目列表)。检测失败时任务状态为 None。"""
    r = _run_hidden(["schtasks", "/Query", "/TN", AUTOSTART_TASK])
    task_ok = r.returncode == 0 if r is not None else None
    items = []
    try:
        startup = os.path.join(os.environ.get("APPDATA", ""),
                               r"Microsoft\Windows\Start Menu\Programs\Startup")
        if os.path.isdir(startup):
            items = [n for n in os.listdir(startup)
                     if "wechat" in n.lower() or "autologin" in n.lower()
                     or n.lower().startswith("start.")]
    except Exception:
        pass
    return task_ok, items


def install_autostart_task():
    """注册「登录时」计划任务（需管理员；由提权后的子进程调用）。"""
    if getattr(sys, "frozen", False):
        target = '"%s"' % sys.executable
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pyw):
            pyw = "pythonw"
        target = '"%s" "%s"' % (pyw, os.path.abspath(__file__))
    r = _run_hidden(["schtasks", "/Create", "/TN", AUTOSTART_TASK, "/SC", "ONLOGON",
                     "/DELAY", "0000:05", "/TR", target + " --watch", "/F"])
    if r is not None and r.returncode == 0:
        print("[OK] 已安装开机自启动（计划任务 %s，登录后 5 秒运行 --watch）" % AUTOSTART_TASK)
        return 0
    print("[失败] 安装计划任务出错: %s" % (r.stderr.strip() if r is not None else "无法执行 schtasks"))
    return 1


def uninstall_autostart_task():
    """删除计划任务（需管理员；由提权后的子进程调用）。"""
    r = _run_hidden(["schtasks", "/Delete", "/TN", AUTOSTART_TASK, "/F"])
    if r is not None and r.returncode == 0:
        print("[OK] 已取消开机自启动（计划任务 %s）" % AUTOSTART_TASK)
        return 0
    print("[失败] 删除计划任务出错: %s" % (r.stderr.strip() if r is not None else "无法执行 schtasks"))
    return 1


def _read_key(prompt):
    """读单个按键（无需回车）；无控制台时退回 input()。回车返回 ''。"""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        import msvcrt
        while True:
            raw = msvcrt.getch()
            if isinstance(raw, bytes):
                key = raw.decode("ascii", "ignore")
            else:
                key = chr(raw)
            if key in ("\r", "\n"):
                return ""
            key = key.strip()
            if key:
                return key.lower()
    except Exception:
        try:
            return input().strip().lower()
        except EOFError:
            return ""


def _wait_autostart_task_state(expect, timeout=10.0):
    """轮询计划任务状态直到等于 expect（True=已安装，False=未安装）。
    提权子进程完成后由父进程调用，用于向用户确认结果。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task, _ = autostart_state()
        if task is expect:
            return True
        time.sleep(1.0)
    return False


def autostart_menu(cfg):
    print()
    print("[3] 开机自启动设置")
    task, items = autostart_state()
    if task:
        task_desc = "已安装"
    elif task is None:
        task_desc = "检测失败"
    else:
        task_desc = "未安装"
    print("  计划任务 %-18s: %s" % (AUTOSTART_TASK, task_desc))
    print("  启动文件夹条目           : %s" % (", ".join(items) if items else "无"))
    op = None
    if task or items:
        print("  按 [a] 取消自启动，[回车] 返回主菜单")
        k = _read_key("  >> ")
        if k == "a":
            op = "uninstall"
    else:
        print("  按 [i] 安装自启动（计划任务，登录后 5 秒运行），[回车] 返回主菜单")
        k = _read_key("  >> ")
        if k == "i":
            op = "install"
    if op:
        if not _is_admin():
            print("  需要管理员权限，正在请求提权（UAC）...")
            _relaunch_elevated(["--install-autostart" if op == "install" else "--uninstall-autostart"])
            expect = (op == "install")
            print("  提权子进程运行中，正在核对结果...")
            if _wait_autostart_task_state(expect):
                print("  [OK] 已%s自启动（计划任务 %s）" % ("安装" if expect else "取消", AUTOSTART_TASK))
            else:
                print("  [提示] 未检测到%s结果——若你刚才取消了 UAC 授权则属正常，可重新操作。"
                      % ("安装" if expect else "取消"))
        else:
            if op == "install":
                install_autostart_task()
            else:
                uninstall_autostart_task()
    time.sleep(1.2)


def interactive_menu(cfg, tpl):
    banner = (
        "\n"
        "==================================================\n"
        "  WeChatAutoLogin — 微信自动登录辅助\n"
        "  作者: Daniel_兔兔\n"
        "  项目: " + APP_GITHUB_URL + "\n"
        "--------------------------------------------------\n"
        "  功能: 等待微信登录窗口 -> 模板匹配绿色按钮\n"
        "        -> 窗口消息点击(不抢鼠标) -> 验证登录成功\n"
        "--------------------------------------------------\n"
        "  1. 测试微信点击（只检测，不实际点击）\n"
        "  2. 实操：微信点击登录\n"
        "  3. 开机自启动设置（检测/安装/取消）\n"
        "  4. 退出\n"
        "  5. 打开 GitHub 页面\n"
        "--------------------------------------------------\n"
    )
    sys.stdout.write(banner)
    sys.stdout.flush()
    while True:
        k = _read_key("  按数字键选择: ")
        if k == "1":
            print("\n[1] 测试微信点击（只检测不点击，微信未开时会等待最多 %d 秒）..."
                  % cfg["process_wait_timeout"])
            rc = run_once(cfg, tpl, dry_run=True)
            print("  完毕，返回码 %d。\n" % rc)
        elif k == "2":
            print("\n[2] 实操：微信点击登录（微信未开时会等待最多 %d 秒）..."
                  % cfg["process_wait_timeout"])
            rc = run_once(cfg, tpl, dry_run=False)
            print("  完毕，返回码 %d。\n" % rc)
        elif k == "3":
            autostart_menu(cfg)
        elif k == "4":
            print("再见，欢迎再来。\n")
            return 0
        elif k == "5":
            print("\n[5] 打开 GitHub 页面...")
            try:
                os.startfile(APP_GITHUB_URL)
                print("  已调用默认浏览器打开。\n")
            except Exception as e:
                print("  打开失败: %s\n" % e)
        else:
            sys.stdout.write("  无效按键，请输入 1-5: ")
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="微信自动登录辅助程序")
    parser.add_argument("--dry-run", action="store_true", help="只检测，不点击（安全测试）")
    parser.add_argument("--watch", action="store_true", help="失败后循环重试")
    parser.add_argument("--install-autostart", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--uninstall-autostart", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = load_config()
    # 提权子进程：只做计划任务的安装/卸载，不进入锁与主流程
    if args.install_autostart:
        return install_autostart_task()
    if args.uninstall_autostart:
        return uninstall_autostart_task()
    if args.watch:
        cfg["watch"] = True
    if args.dry_run:
        cfg["watch"] = False

    setup_logging(cfg)

    tpl_path = os.path.join(APP_DIR, cfg["template_file"])
    if not os.path.isfile(tpl_path):
        # exe 旁边没有模板图时，用内嵌在 exe 里的那份（PyInstaller _MEIPASS）
        tpl_path = os.path.join(BUNDLE_DIR, cfg["template_file"])
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        logging.error("无法读取模板图片: %s", tpl_path)
        print("[错误] 找不到绿色按钮模板 greenButton.jpg")
        return 2

    if not acquire_single_instance():
        return 0
    set_dpi_awareness()

    if not (args.dry_run or args.watch):
        # 无参数：交互菜单（exe 双击即用）
        return interactive_menu(cfg, tpl)

    logging.info("===== WeChatAutoLogin 启动 （dry-run=%s, watch=%s）=====",
                 args.dry_run, cfg["watch"])

    rc = run_once(cfg, tpl, dry_run=args.dry_run)
    while rc != 0 and cfg["watch"]:
        logging.info("watch 模式：%.0f 秒后重试...", cfg["watch_interval"])
        time.sleep(cfg["watch_interval"])
        rc = run_once(cfg, tpl, dry_run=args.dry_run)
    logging.info("===== 结束，退出码 %d =====", rc)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 兜底：不让程序裸崩，打印可读信息
        import traceback
        traceback.print_exc()
        print("\n[错误] 程序发生异常: %s\n请把以上信息带到项目 Issues 反馈。" % e)
        sys.exit(1)