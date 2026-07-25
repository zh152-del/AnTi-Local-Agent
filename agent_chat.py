# -*- coding: utf-8 -*-
"""
AgentChat Pro - 纯本地自动化 Agent（类 codex），白主题双模式
- 本地 Ollama (http://localhost:11434)，默认模型 deepseek-coder:1.3b
- 运行模式：
    个人聊天模式：纯对话，不开启 Agent 自动化；仍可主协模型回答
    Agent 模式  ：模型可自动执行命令 / 读写文件 / 浏览目录（多步循环）
- 主协模型（多模型协作）：主模型总结+执行，最多 2 个协助模型并行回答（右窗独立显示）
- 文件访问开关：关闭时仅允许访问专属工作目录，打开后可访问全部文件
- 视觉功能（独立开关）：开启后每轮对话自动后台截图并喂给视觉模型（需 qwen3-vl 等视觉模型）；可点「上传图片」手动提供图片，手动上传优先于自动截图
- 外设控制（独立开关）：Agent 模式可操控鼠标/键盘与桌面程序交互（点击/双击/右键/拖拽/滚动/输入/按键/取坐标/取分辨率，危险，默认关）
- Skill 系统：可部署 .md/.txt 技能文件，勾选启用后注入系统提示
仅依赖 Python 标准库 + pyautogui（截图/外设，已打包）
"""
import json
import os
import re
import shutil
import subprocess
import threading
import queue
import base64
import io
import time
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-coder:1.3b"

APP_DIR = os.path.join(os.path.expanduser("~"), ".agentchat")
SKILLS_DIR = os.path.join(APP_DIR, "skills")
WORKSPACE = os.path.join(os.path.expanduser("~"), "AgentChat_Workspace")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

for _d in (APP_DIR, SKILLS_DIR, WORKSPACE):
    os.makedirs(_d, exist_ok=True)

# 首次运行时创建示例 Skill
_sample = os.path.join(SKILLS_DIR, "示例-代码规范.md")
if not os.listdir(SKILLS_DIR):
    try:
        with open(_sample, "w", encoding="utf-8") as f:
            f.write("# 代码规范 Skill\n- 生成代码时必须带注释\n- Python 遵循 PEP8\n- 回答保持简洁\n")
    except Exception:
        pass

# ---- 白色主题 ----
BG        = "#ffffff"   # 主聊天区背景
BG_PANEL  = "#f3f5f8"   # 顶栏 / 状态栏
BG_SIDE   = "#f7f9fb"   # 侧边栏
BG_INPUT  = "#ffffff"   # 输入框 / 控件底
FG        = "#1f2328"   # 主文字
FG_DIM    = "#69707d"   # 次要文字
ACCENT    = "#2563eb"   # 主强调（蓝）
ACCENT_HI = "#1d4ed8"
USER_CLR  = "#2563eb"
AI_CLR    = "#15803d"
TOOL_CLR  = "#c2410c"   # 工具（深橙，白底可读）
PLAN_CLR  = "#7c3aed"   # 规划/协助（紫）
ERR_CLR   = "#dc2626"
BORDER    = "#d0d7de"

MONO = ("Consolas", 10)
UI_F = ("Microsoft YaHei UI", 9)
UI_B = ("Microsoft YaHei UI", 9, "bold")

DANGEROUS = [r"rm\s+-rf\s+/\s*$", r"rm\s+-rf\s+/[a-z]*\s", r"format\s+[a-z]:",
             r"del\s+/[fsq\s]+c:\\\\?\s*$", r"rd\s+/s\s+/q\s+c:\\\\?\s*$",
             r"mkfs", r"shutdown", r"reg\s+delete\s+hklm"]


def tool_protocol(full_access: bool, vision: bool = False, periph: bool = False) -> str:
    scope = "全部磁盘（不受限制）" if full_access else f"仅限工作目录 {WORKSPACE}"
    lines = [
        "你是一个可以操作电脑的 Agent。当需要执行操作时，只输出一个 JSON 对象（不要任何其它文字、不要解释）：\n",
        '{"tool":"run_command","command":"<shell命令>"}  执行系统命令\n',
        '{"tool":"read_file","path":"<文件路径>"}  读取文件\n',
        '{"tool":"write_file","path":"<文件路径>","content":"<内容>"}  写入/创建文件\n',
        '{"tool":"list_dir","path":"<目录路径>"}  列出目录\n',
    ]
    if vision:
        lines.append('{"tool":"screenshot"}  重新截取当前屏幕（视觉功能已自动在每轮附带屏幕截图，通常无需手动调用）\n')
    if periph:
        lines += [
            '{"tool":"mouse_click","x":<整数>,"y":<整数>,"button":"left|right"}  在坐标(x,y)点击；省略x,y则在当前鼠标处点击\n',
            '{"tool":"mouse_double_click","x":<整数>,"y":<整数>}  在坐标处双击\n',
            '{"tool":"mouse_right_click","x":<整数>,"y":<整数>}  在坐标处右键单击\n',
            '{"tool":"mouse_move","x":<整数>,"y":<整数>}  移动鼠标到坐标(x,y)\n',
            '{"tool":"mouse_scroll","x":<整数>,"y":<整数>,"clicks":<整数>}  在坐标处滚动（clicks为正向上、负向下）\n',
            '{"tool":"drag","from_x":<整数>,"from_y":<整数>,"to_x":<整数>,"to_y":<整数>}  从一点拖拽到另一点\n',
            '{"tool":"type_text","text":"<要输入的文字>"}  在当前焦点处输入文字\n',
            '{"tool":"key_press","key":"<按键>"}  按下按键，如 "enter"、"esc"、"ctrl+c"、"alt+f4"\n',
            '{"tool":"get_mouse_position"}  返回当前鼠标坐标(x,y)，便于定位\n',
            '{"tool":"get_screen_size"}  返回屏幕分辨率(width,height)\n',
        ]
    lines += [
        "规则：\n",
        "1. 每次只输出一个 JSON 工具调用；收到 [工具执行结果] 后再决定下一步。\n",
        "2. 任务完成后，用普通文字总结回答，绝对不要再输出 JSON。\n",
        f"3. 文件访问权限：{scope}\n",
        f"4. 当前系统：Windows，命令在 cmd/shell 中执行，工作目录 {WORKSPACE}\n",
    ]
    if vision:
        lines.append("5. 视觉已自动开启：每轮对话都会自动附带当前屏幕截图，你可直接据此判断点击/输入位置；如需最新画面可调用 screenshot 重新截取。\n")
    if periph:
        lines.append("6. 你拥有外设控制权：可直接操控鼠标与键盘与桌面程序交互。\n")
    return "".join(lines)


def _img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _is_vision(model: str) -> bool:
    m = (model or "").lower()
    keys = ("vl", "vision", "llava", "minicpm", "glm-v", "qwen-vl",
            "qwen3-vl", "moondream", "bakllava", "internvl")
    return any(k in m for k in keys)


def parse_tool_call(text: str):
    """从模型输出中提取工具调用 JSON"""
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    idx = 0
    while True:
        i = text.find('{"tool"', idx)
        if i == -1:
            break
        depth, j = 0, i
        in_str, esc = False, False
        for j in range(i, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[i:j + 1])
                        break
        idx = j + 1
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and obj.get("tool"):
                return obj
        except Exception:
            continue
    return None


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", errors="replace")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("AnTi · 本地 Agent 助手")
        root.geometry("1240x740")
        root.minsize(1000, 600)
        root.configure(bg=BG)

        # 应用图标（窗口标题栏 / 任务栏 / Alt-Tab）
        try:
            from PIL import Image, ImageTk
            import sys, os
            if getattr(sys, "frozen", False):
                # PyInstaller 解包目录
                _base = os.path.dirname(sys.executable)
            else:
                _base = os.path.dirname(os.path.abspath(__file__))
            _ico = os.path.join(_base, "assets", "anti_icon.png")
            if not os.path.exists(_ico):
                _ico = os.path.join(_base, "assets", "anti_icon.ico")
            if os.path.exists(_ico):
                _img = Image.open(_ico)
                self._icon_imgs = []
                for sz in (16, 24, 32, 48, 64, 128, 256):
                    self._icon_imgs.append(ImageTk.PhotoImage(_img.resize((sz, sz), Image.LANCZOS)))
                root.iconphoto(True, *self._icon_imgs)
                try:
                    root.iconbitmap(os.path.join(_base, "assets", "anti_icon.ico"))
                except Exception:
                    pass
        except Exception as e:
            print("icon load failed:", e)

        self.messages = []
        self.streaming = False
        self.stop_flag = threading.Event()
        self.q = queue.Queue()
        self.skill_vars = {}        # name -> BooleanVar
        self.assistant_vars = {}    # model name -> BooleanVar
        self.assistant_cbs = []     # 协助模型勾选框控件
        self.known_models = []      # 本地模型列表
        self._pending_assistants = set()

        # 运行模式："personal" 个人聊天 / "agent" Agent 模式
        self.mode_var = tk.StringVar(value="personal")
        # 开关
        self.full_access = tk.BooleanVar(value=False)
        self.multi_on = tk.BooleanVar(value=False)
        self.vision_on = tk.BooleanVar(value=False)   # 视觉功能（截图喂视觉模型）
        self.periph_on = tk.BooleanVar(value=False)   # 外设控制（鼠标/键盘）
        self.pending_uploads = []                     # 手动上传图片（base64），下次发送生效

        self._build_style()
        self._build_sidebar()
        self._build_main()
        self._load_config()
        self._refresh_skills()
        self._refresh_mode_ui()
        self._refresh_multi_ui()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(80, self._poll_queue)
        threading.Thread(target=self._load_models, daemon=True).start()
        self._sys_msg("AgentChat Pro 已就绪 —— 纯本地运行。\n"
                      "· 当前为「个人聊天模式」：仅对话，不自动执行\n"
                      "· 开启「主协模型」后，右侧出现协助模型独立窗口\n"
                      "· 切到「Agent 模式」后可开启：\n"
                      "   - 视觉功能：开启后每轮自动后台截图并喂给视觉模型；也可点「上传图片」手动提供（手动优先）。需用 qwen3-vl 等视觉模型\n"
                      "   - 外设控制：Agent 操控鼠标/键盘（点击/双击/右键/拖拽/滚动/输入/按键/取坐标，危险，仅可信任务开启）\n"
                      "· Enter 发送 · Shift+Enter 换行\n")

    # ================= UI =================
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                     foreground=FG, arrowcolor=FG, bordercolor=BORDER)
        st.map("TCombobox", fieldbackground=[("readonly", BG_INPUT)],
               foreground=[("readonly", FG)], background=[("readonly", BG_INPUT)])
        st.configure("Horizontal.TScale", background=BG_SIDE, troughcolor="#e5e7eb")

    def is_agent(self):
        return self.mode_var.get() == "agent"

    def _set_mode(self, mode):
        self.mode_var.set(mode)
        self._refresh_mode_ui()

    def _refresh_mode_ui(self):
        agent = self.is_agent()
        if agent:
            self.agent_btn.config(bg=ACCENT, fg="white", activebackground=ACCENT,
                                  activeforeground="white")
            self.personal_btn.config(bg="white", fg=FG, activebackground="#e8edf3",
                                     activeforeground=FG)
            self.full_access_cb.config(state="normal", fg=FG,
                                       activeforeground=FG, selectcolor=BG_INPUT)
            self.vision_cb.config(state="normal", fg=FG,
                                  activeforeground=FG, selectcolor=BG_INPUT)
            self.periph_cb.config(state="normal", fg=FG,
                                  activeforeground=FG, selectcolor=BG_INPUT)
            self.max_steps_spin.config(state="normal", bg=BG_INPUT, fg=FG,
                                       buttonbackground=BG_INPUT, insertbackground=FG)
        else:
            self.personal_btn.config(bg=ACCENT, fg="white", activebackground=ACCENT,
                                     activeforeground="white")
            self.agent_btn.config(bg="white", fg=FG, activebackground="#e8edf3",
                                  activeforeground=FG)
            self.full_access_cb.config(state="disabled", fg=FG_DIM,
                                       activeforeground=FG_DIM, selectcolor=BG_INPUT)
            self.vision_cb.config(state="disabled", fg=FG_DIM,
                                  activeforeground=FG_DIM, selectcolor=BG_INPUT)
            self.periph_cb.config(state="disabled", fg=FG_DIM,
                                  activeforeground=FG_DIM, selectcolor=BG_INPUT)
            self.max_steps_spin.config(state="disabled", bg=BG_INPUT, fg=FG_DIM,
                                       buttonbackground=BG_INPUT, insertbackground=FG_DIM)

    def _refresh_multi_ui(self):
        multi = self.multi_on.get()
        if multi:
            self.right_frame.pack(side="right", fill="y")
        else:
            self.right_frame.pack_forget()
        state = "normal" if multi else "disabled"
        try:
            self.main_model_box.config(state=state)
        except Exception:
            pass
        for cb in self.assistant_cbs:
            try:
                cb.config(state=state)
            except Exception:
                pass

    def _switch(self, parent, text, var, desc="", cmd=None):
        f = tk.Frame(parent, bg=BG_SIDE)
        f.pack(fill="x", padx=10, pady=(4, 0))
        cb = tk.Checkbutton(f, text=text, variable=var, bg=BG_SIDE, fg=FG,
                            selectcolor=BG_INPUT, activebackground=BG_SIDE,
                            activeforeground=FG, font=UI_B, anchor="w",
                            highlightthickness=0, bd=0, command=cmd)
        cb.pack(fill="x")
        if desc:
            tk.Label(f, text=desc, bg=BG_SIDE, fg=FG_DIM, font=("Microsoft YaHei UI", 8),
                     anchor="w", justify="left", wraplength=200).pack(fill="x", padx=(22, 0))
        return cb

    def _side_btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, bg=BG_INPUT, fg=FG,
                      relief="flat", font=UI_F, cursor="hand2", padx=6, pady=2,
                      activebackground="#e8edf3", activeforeground=FG)
        return b

    def _build_sidebar(self):
        side = tk.Frame(self.root, bg=BG_SIDE, width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="⚡ AgentChat Pro", bg=BG_SIDE, fg=FG,
                 font=("Microsoft YaHei UI", 12, "bold"), anchor="w",
                 padx=12, pady=10).pack(fill="x")

        # ---- 运行模式切换 ----
        mf = tk.Frame(side, bg=BG_SIDE)
        mf.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(mf, text="运行模式", bg=BG_SIDE, fg=FG_DIM, font=UI_B,
                 anchor="w").pack(fill="x")
        seg = tk.Frame(mf, bg=BORDER)
        seg.pack(fill="x", pady=(4, 2))
        self.personal_btn = tk.Button(seg, text="🗨 个人聊天", font=UI_B,
                                      relief="flat", cursor="hand2", bd=0,
                                      command=lambda: self._set_mode("personal"))
        self.agent_btn = tk.Button(seg, text="🤖 Agent 模式", font=UI_B,
                                   relief="flat", cursor="hand2", bd=0,
                                   command=lambda: self._set_mode("agent"))
        self.personal_btn.pack(side="left", fill="x", expand=True, ipady=4)
        self.agent_btn.pack(side="left", fill="x", expand=True, ipady=4)

        # ---- 开关区 ----
        tk.Label(side, text="控制开关", bg=BG_SIDE, fg=FG_DIM, font=UI_B,
                 anchor="w", padx=12).pack(fill="x", pady=(6, 0))
        self.full_access_cb = self._switch(side, "访问全部文件", self.full_access,
                     "关闭=仅限工作目录（安全）；打开=可访问全盘（仅 Agent 模式生效）")
        self._switch(side, "主协模型", self.multi_on,
                     "主模型总结+执行；勾选≤2个协助模型并行回答（右侧独立窗口）；开启即展开窗口",
                     cmd=self._refresh_multi_ui)
        self.vision_cb = self._switch(side, "视觉功能", self.vision_on,
                     "开启后 Agent 可截图并把屏幕图像喂给视觉模型（需选 qwen3-vl 等视觉模型）；仅 Agent 模式生效")
        self.periph_cb = self._switch(side, "外设控制", self.periph_on,
                     "开启后 Agent 可操控鼠标/键盘与桌面程序交互；危险，请仅在可信任务下开启；仅 Agent 模式生效")

        # ---- 上传图片 ----
        btns_img = tk.Frame(side, bg=BG_SIDE)
        btns_img.pack(fill="x", padx=12, pady=(4, 0))
        self._side_btn(btns_img, "📷 上传图片", self._upload_image).pack(side="left")
        self.img_status = tk.Label(side, text="", bg=BG_SIDE, fg=FG_DIM, font=UI_F,
                                   anchor="w")
        self.img_status.pack(fill="x", padx=12, pady=(2, 0))

        # ---- 主协模型配置 ----
        self.multi_frame = tk.Frame(side, bg=BG_SIDE)
        self.multi_frame.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(self.multi_frame, text="主模型（总结 + 执行）", bg=BG_SIDE, fg=FG_DIM,
                 font=UI_F, anchor="w").pack(fill="x")
        self.main_model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.main_model_box = ttk.Combobox(self.multi_frame, textvariable=self.main_model_var,
                                           font=MONO, state="normal")
        self.main_model_box.pack(fill="x", pady=(2, 0))
        tk.Label(self.multi_frame, text="协助模型（勾选，最多 2 个）", bg=BG_SIDE, fg=FG_DIM,
                 font=UI_F, anchor="w").pack(fill="x", pady=(6, 0))
        self.assistant_frame = tk.Frame(self.multi_frame, bg=BG_SIDE)
        self.assistant_frame.pack(fill="x", pady=(2, 0))
        tk.Label(self.assistant_frame, text="（等待模型列表…）", bg=BG_SIDE, fg=FG_DIM,
                 font=UI_F, anchor="w").pack(fill="x")

        # ---- 最大步数 ----
        sf = tk.Frame(side, bg=BG_SIDE)
        sf.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(sf, text="最大自动步数", bg=BG_SIDE, fg=FG_DIM, font=UI_F,
                 anchor="w").pack(side="left")
        self.max_steps_var = tk.IntVar(value=8)
        self.max_steps_spin = tk.Spinbox(sf, from_=1, to=30, textvariable=self.max_steps_var,
                                         width=5, bg=BG_INPUT, fg=FG, relief="flat", font=MONO,
                                         buttonbackground=BG_INPUT, insertbackground=FG)
        self.max_steps_spin.pack(side="right")

        # ---- Skill 区 ----
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)
        head = tk.Frame(side, bg=BG_SIDE)
        head.pack(fill="x", padx=12)
        tk.Label(head, text="Skills（勾选启用）", bg=BG_SIDE, fg=FG_DIM,
                 font=UI_B, anchor="w").pack(side="left")

        btns = tk.Frame(side, bg=BG_SIDE)
        btns.pack(fill="x", padx=12, pady=(4, 2))
        self._side_btn(btns, "＋部署 Skill", self._deploy_skill).pack(side="left")
        self._side_btn(btns, "刷新", self._refresh_skills).pack(side="left", padx=4)
        self._side_btn(btns, "打开目录", lambda: os.startfile(SKILLS_DIR)).pack(side="left")

        self.skill_frame = tk.Frame(side, bg=BG_SIDE)
        self.skill_frame.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        # ---- 工作目录 ----
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=4)
        wf = tk.Frame(side, bg=BG_SIDE)
        wf.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(wf, text="Agent 工作目录", bg=BG_SIDE, fg=FG_DIM, font=UI_F,
                 anchor="w").pack(fill="x")
        self._side_btn(wf, "📂 打开工作目录", lambda: os.startfile(WORKSPACE)).pack(fill="x", pady=(2, 0))

    def _build_main(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        # ---- 顶栏 ----
        bar = tk.Frame(main, bg=BG_PANEL, padx=10, pady=8)
        bar.pack(fill="x")

        def lbl(parent, text):
            return tk.Label(parent, text=text, bg=BG_PANEL, fg=FG_DIM, font=UI_F)

        r1 = tk.Frame(bar, bg=BG_PANEL); r1.pack(fill="x")
        lbl(r1, "服务地址").pack(side="left")
        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        tk.Entry(r1, textvariable=self.host_var, bg=BG_INPUT, fg=FG, relief="solid",
                 highlightbackground=BORDER, highlightthickness=1,
                 insertbackground=FG, font=MONO, width=24).pack(side="left", padx=(6, 14), ipady=3)
        lbl(r1, "对话模型").pack(side="left")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_box = ttk.Combobox(r1, textvariable=self.model_var, width=22,
                                      font=MONO, state="normal")
        self.model_box.pack(side="left", padx=(6, 10))
        tk.Button(r1, text="刷新模型", command=lambda: threading.Thread(
            target=self._load_models, daemon=True).start(),
            bg=BG_INPUT, fg=FG, relief="flat", font=UI_F, padx=8, cursor="hand2",
            activebackground="#e8edf3", activeforeground=FG).pack(side="left")
        tk.Button(r1, text="清空对话", command=self._clear_chat,
                  bg=BG_INPUT, fg=FG, relief="flat", font=UI_F, padx=8, cursor="hand2",
                  activebackground="#e8edf3", activeforeground=FG).pack(side="right")

        r2 = tk.Frame(bar, bg=BG_PANEL); r2.pack(fill="x", pady=(8, 0))
        self.temp_var = tk.DoubleVar(value=0.7)
        self.topp_var = tk.DoubleVar(value=0.9)
        self.maxtok_var = tk.IntVar(value=1024)
        self.ctx_var = tk.IntVar(value=8192)
        self._param_slider(r2, "Temperature", self.temp_var, 0.0, 2.0, 0.05, "{:.2f}")
        self._param_slider(r2, "Top-P", self.topp_var, 0.05, 1.0, 0.05, "{:.2f}")
        self._param_slider(r2, "最大输出", self.maxtok_var, 64, 8192, 64, "{:.0f}")
        self._param_slider(r2, "上下文", self.ctx_var, 512, 16384, 512, "{:.0f}")

        r3 = tk.Frame(bar, bg=BG_PANEL); r3.pack(fill="x", pady=(8, 0))
        lbl(r3, "System").pack(side="left")
        self.sys_var = tk.StringVar(value="你是一个高效的本地编程助手，请用中文回答。")
        tk.Entry(r3, textvariable=self.sys_var, bg=BG_INPUT, fg=FG, relief="solid",
                 highlightbackground=BORDER, highlightthickness=1,
                 insertbackground=FG, font=MONO).pack(side="left", fill="x",
                                                      expand=True, padx=(6, 0), ipady=3)

        # ---- 主体：左聊天 + 右协助窗 ----
        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        # 聊天区
        wrap = tk.Frame(left, bg=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.chat = tk.Text(wrap, bg=BG, fg=FG, relief="solid",
                            highlightbackground=BORDER, highlightthickness=1,
                            wrap="word", font=MONO, insertbackground=FG,
                            padx=12, pady=10, state="disabled", spacing1=2, spacing3=2)
        sb = tk.Scrollbar(wrap, command=self.chat.yview, bg=BG_PANEL,
                          troughcolor=BG, relief="flat")
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("user_tag", foreground=USER_CLR, font=("Consolas", 10, "bold"))
        self.chat.tag_configure("ai_tag", foreground=AI_CLR, font=("Consolas", 10, "bold"))
        self.chat.tag_configure("plan_tag", foreground=PLAN_CLR, font=("Consolas", 10, "bold"))
        self.chat.tag_configure("tool", foreground=TOOL_CLR)
        self.chat.tag_configure("sys", foreground=FG_DIM)
        self.chat.tag_configure("err", foreground=ERR_CLR)
        self.chat.tag_configure("body", foreground=FG)

        # 输入区
        area = tk.Frame(left, bg=BG, padx=10, pady=10)
        area.pack(fill="x")
        box = tk.Frame(area, bg=BORDER, padx=1, pady=1)
        box.pack(fill="x")
        inner = tk.Frame(box, bg=BG_INPUT)
        inner.pack(fill="x")
        self.entry = tk.Text(inner, height=3, bg=BG_INPUT, fg=FG, relief="flat",
                             font=MONO, insertbackground=FG, padx=10, pady=8, wrap="word")
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)
        self.entry.focus_set()
        self.send_btn = tk.Button(inner, text="发送 ▶", command=self._send,
                                  bg=ACCENT, fg="white", relief="flat",
                                  font=("Microsoft YaHei UI", 10, "bold"),
                                  padx=16, cursor="hand2",
                                  activebackground=ACCENT_HI, activeforeground="white")
        self.send_btn.pack(side="right", fill="y")

        # 右窗：协助模型回答（默认隐藏）
        self.right_frame = tk.Frame(body, bg=BG_SIDE, width=350)
        tk.Label(self.right_frame, text="🤝 协助模型回答", bg=BG_SIDE, fg=FG,
                 font=UI_B, anchor="w", padx=10, pady=8).pack(fill="x")
        rwrap = tk.Frame(self.right_frame, bg=BG_SIDE)
        rwrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.right_chat = tk.Text(rwrap, bg=BG_SIDE, fg=FG, relief="solid",
                                  highlightbackground=BORDER, highlightthickness=1,
                                  wrap="word", font=MONO, insertbackground=FG,
                                  padx=10, pady=8, state="disabled", spacing1=2, spacing3=2)
        rsb = tk.Scrollbar(rwrap, command=self.right_chat.yview, bg=BG_PANEL,
                           troughcolor=BG_SIDE, relief="flat")
        self.right_chat.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        self.right_chat.pack(side="left", fill="both", expand=True)
        self.right_chat.tag_configure("rname", foreground=PLAN_CLR, font=("Consolas", 10, "bold"))
        self.right_chat.tag_configure("rbody", foreground=FG)

        # ---- 状态栏 ----
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(main, textvariable=self.status_var, bg=BG_PANEL, fg=FG_DIM,
                 font=UI_F, anchor="w", padx=10, pady=3).pack(fill="x", side="bottom")

    def _param_slider(self, parent, name, var, lo, hi, step, fmt):
        f = tk.Frame(parent, bg=BG_PANEL)
        f.pack(side="left", padx=(0, 16))
        val_lbl = tk.Label(f, text=fmt.format(var.get()), bg=BG_PANEL, fg=ACCENT,
                           font=("Consolas", 9, "bold"), width=6, anchor="w")
        tk.Label(f, text=name, bg=BG_PANEL, fg=FG_DIM, font=UI_F).pack(side="left")

        def on_change(v):
            x = float(v)
            x = round(x / step) * step
            if isinstance(var, tk.IntVar):
                var.set(int(x))
            else:
                var.set(round(x, 3))
            val_lbl.config(text=fmt.format(x))

        s = ttk.Scale(f, from_=lo, to=hi, orient="horizontal", length=100, command=on_change)
        s.set(var.get())
        s.pack(side="left", padx=(6, 4))
        val_lbl.pack(side="left")

    # ================= Skill =================
    def _refresh_skills(self):
        for w in self.skill_frame.winfo_children():
            w.destroy()
        old = {k: v.get() for k, v in self.skill_vars.items()}
        self.skill_vars.clear()
        try:
            files = sorted(f for f in os.listdir(SKILLS_DIR)
                           if f.lower().endswith((".md", ".txt")))
        except Exception:
            files = []
        if not files:
            tk.Label(self.skill_frame, text="（暂无 Skill，点击上方部署）",
                     bg=BG_SIDE, fg=FG_DIM, font=UI_F, anchor="w").pack(fill="x")
            return
        for f in files:
            name = os.path.splitext(f)[0]
            var = tk.BooleanVar(value=old.get(name, False))
            self.skill_vars[name] = var
            tk.Checkbutton(self.skill_frame, text=name, variable=var, bg=BG_SIDE,
                           fg=FG, selectcolor=BG_INPUT, activebackground=BG_SIDE,
                           activeforeground=FG, font=UI_F, anchor="w",
                           highlightthickness=0, bd=0).pack(fill="x")

    def _deploy_skill(self):
        paths = filedialog.askopenfilenames(
            title="选择 Skill 文件（.md / .txt）",
            filetypes=[("Skill 文件", "*.md *.txt"), ("所有文件", "*.*")])
        n = 0
        for p in paths:
            try:
                shutil.copy(p, os.path.join(SKILLS_DIR, os.path.basename(p)))
                n += 1
            except Exception as e:
                messagebox.showerror("部署失败", f"{p}\n{e}")
        if n:
            self._refresh_skills()
            self._sys_msg(f"已部署 {n} 个 Skill，勾选左侧列表即可启用。")

    def _upload_image(self):
        """手动上传图片：作为下一次发送时附带给模型的视觉输入（优先于自动截图）"""
        paths = filedialog.askopenfilenames(
            title="选择图片（可多选）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("所有文件", "*.*")])
        added = 0
        for p in paths:
            try:
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                self.pending_uploads.append(b64)
                added += 1
            except Exception as e:
                messagebox.showerror("上传失败", f"{p}\n{e}")
        if added:
            self.img_status.config(text=f"📎 已附加 {len(self.pending_uploads)} 张图片（下次发送生效）")
            self._sys_msg(f"已上传 {added} 张图片，将在下一次发送时一并提供给模型（优先于自动截图）。")

    def _skill_texts(self):
        parts = []
        for name, var in self.skill_vars.items():
            if not var.get():
                continue
            for ext in (".md", ".txt"):
                fp = os.path.join(SKILLS_DIR, name + ext)
                if os.path.exists(fp):
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            parts.append(f"## Skill: {name}\n{f.read()[:4000]}")
                    except Exception:
                        pass
                    break
        return parts

    # ================= 主协模型 =================
    def _on_assistant_toggle(self, name):
        checked = [n for n, v in self.assistant_vars.items() if v.get()]
        if len(checked) > 2:
            self.assistant_vars[name].set(False)
            messagebox.showwarning("最多两个", "协助模型最多选择 2 个。")

    def _refresh_assistants(self):
        for w in self.assistant_frame.winfo_children():
            w.destroy()
        self.assistant_cbs = []
        old = {k: v.get() for k, v in self.assistant_vars.items()}
        self.assistant_vars.clear()
        models = list(self.known_models)
        if not models:
            tk.Label(self.assistant_frame, text="（等待模型列表…）", bg=BG_SIDE,
                     fg=FG_DIM, font=UI_F, anchor="w").pack(fill="x")
            return
        for m in models:
            var = tk.BooleanVar(value=old.get(m, False) or (m in self._pending_assistants))
            self.assistant_vars[m] = var
            cb = tk.Checkbutton(self.assistant_frame, text=m, variable=var, bg=BG_SIDE,
                                fg=FG, selectcolor=BG_INPUT, activebackground=BG_SIDE,
                                activeforeground=FG, font=("Consolas", 9), anchor="w",
                                highlightthickness=0, bd=0,
                                command=lambda n=m: self._on_assistant_toggle(n))
            cb.pack(fill="x")
            self.assistant_cbs.append(cb)
        self._pending_assistants.clear()
        # 应用当前开关状态
        self._refresh_multi_ui()

    # ================= 工具执行 =================
    def _safe_path(self, p: str) -> str:
        p = os.path.expanduser(str(p))
        if not os.path.isabs(p):
            p = os.path.join(WORKSPACE, p)
        p = os.path.abspath(p)
        if not self.full_access.get():
            ws = os.path.abspath(WORKSPACE)
            if not (p == ws or p.startswith(ws + os.sep)):
                raise PermissionError(
                    f"拒绝访问 {p}：未开启「访问全部文件」，只能访问 {ws}")
        return p

    def _exec_tool(self, call: dict) -> str:
        tool = call.get("tool", "")
        try:
            if tool == "run_command":
                cmd = str(call.get("command", "")).strip()
                if not cmd:
                    return "错误：命令为空"
                low = cmd.lower()
                for pat in DANGEROUS:
                    if re.search(pat, low):
                        return f"已拦截危险命令：{cmd}"
                cwd = WORKSPACE if not self.full_access.get() else None
                r = subprocess.run(cmd, shell=True, capture_output=True,
                                   timeout=120, cwd=cwd,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                out = _decode(r.stdout).strip()
                err = _decode(r.stderr).strip()
                res = f"exit={r.returncode}"
                if out:
                    res += f"\nstdout:\n{out[:6000]}"
                if err:
                    res += f"\nstderr:\n{err[:2000]}"
                return res
            elif tool == "read_file":
                p = self._safe_path(call.get("path", ""))
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = f.read()
                return f"文件 {p}（{len(data)} 字符）:\n{data[:8000]}"
            elif tool == "write_file":
                p = self._safe_path(call.get("path", ""))
                os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
                content = str(call.get("content", ""))
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"已写入 {p}（{len(content)} 字符）"
            elif tool == "list_dir":
                p = self._safe_path(call.get("path", ".") or ".")
                items = os.listdir(p)
                lines = []
                for it in items[:200]:
                    fp = os.path.join(p, it)
                    tag = "<DIR> " if os.path.isdir(fp) else "      "
                    lines.append(tag + it)
                return f"目录 {p}（{len(items)} 项）:\n" + "\n".join(lines)
            elif tool == "screenshot":
                if not self.vision_on.get():
                    return "未开启「视觉功能」，无法截图"
                try:
                    import pyautogui
                except Exception as e:
                    return f"截图模块未安装：{e}（请重新打包以包含 pyautogui）"
                path = os.path.join(WORKSPACE, f"screenshot_{int(time.time())}.png")
                try:
                    pyautogui.screenshot(path)
                except Exception as e:
                    return f"截图失败：{e}"
                return f"已截图：{path}"
            elif tool in ("mouse_click", "mouse_move", "mouse_double_click", "mouse_right_click",
                          "mouse_scroll", "drag", "type_text", "key_press",
                          "get_mouse_position", "get_screen_size"):
                if not self.periph_on.get():
                    return "未开启「外设控制」，无法操作鼠标/键盘"
                try:
                    import pyautogui
                except Exception as e:
                    return f"外设模块未安装：{e}（请重新打包以包含 pyautogui）"
                try:
                    pyautogui.PAUSE = 0.15
                    sw, sh = pyautogui.size()
                    def _clamp(v):
                        return max(0, min(int(v), sw)), max(0, min(int(v), sh))
                    if tool == "mouse_click":
                        x = int(float(call.get("x", 0))) if call.get("x") is not None else None
                        y = int(float(call.get("y", 0))) if call.get("y") is not None else None
                        btn = str(call.get("button", "left"))
                        if x is None or y is None:
                            pyautogui.click(button=btn)
                            return f"已点击（当前鼠标位置）按钮={btn}"
                        else:
                            x, y = _clamp(x), _clamp(y)
                            pyautogui.click(x, y, button=btn)
                            return f"已点击 ({x},{y}) 按钮={btn}"
                    elif tool == "mouse_double_click":
                        x, y = _clamp(call.get("x")), _clamp(call.get("y"))
                        pyautogui.doubleClick(x, y)
                        return f"已双击 ({x},{y})"
                    elif tool == "mouse_right_click":
                        x, y = _clamp(call.get("x")), _clamp(call.get("y"))
                        pyautogui.rightClick(x, y)
                        return f"已右键单击 ({x},{y})"
                    elif tool == "mouse_move":
                        x, y = _clamp(call.get("x")), _clamp(call.get("y"))
                        pyautogui.moveTo(x, y)
                        return f"已移动鼠标到 ({x},{y})"
                    elif tool == "mouse_scroll":
                        x, y = _clamp(call.get("x")), _clamp(call.get("y"))
                        clicks = int(float(call.get("clicks", 0)))
                        pyautogui.moveTo(x, y)
                        pyautogui.scroll(clicks)
                        return f"已在 ({x},{y}) 滚动 {clicks}（正=上/负=下）"
                    elif tool == "drag":
                        fx, fy = _clamp(call.get("from_x")), _clamp(call.get("from_y"))
                        tx, ty = _clamp(call.get("to_x")), _clamp(call.get("to_y"))
                        pyautogui.moveTo(fx, fy)
                        pyautogui.dragTo(tx, ty, duration=0.4)
                        return f"已从 ({fx},{fy}) 拖拽到 ({tx},{ty})"
                    elif tool == "type_text":
                        text = str(call.get("text", ""))
                        pyautogui.write(text, interval=0.02)
                        return f"已输入 {len(text)} 个字符"
                    elif tool == "key_press":
                        key = str(call.get("key", "")).strip()
                        if not key:
                            return "错误：按键为空"
                        if "+" in key:
                            pyautogui.hotkey(*[k.strip() for k in key.split("+")])
                        else:
                            pyautogui.press(key)
                        return f"已按键 {key}"
                    elif tool == "get_mouse_position":
                        pos = pyautogui.position()
                        return f"当前鼠标坐标：x={pos.x}, y={pos.y}"
                    elif tool == "get_screen_size":
                        return f"屏幕分辨率：width={sw}, height={sh}"
                except Exception as e:
                    return f"外设操作失败：{e}"
            else:
                return f"未知工具：{tool}"
        except subprocess.TimeoutExpired:
            return "错误：命令执行超时（120s）"
        except PermissionError as e:
            return f"权限错误：{e}"
        except Exception as e:
            return f"执行出错：{e}"

    # ================= Ollama =================
    def _load_models(self):
        try:
            with urllib.request.urlopen(self.host_var.get().rstrip("/") + "/api/tags",
                                        timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            names = [m["name"] for m in data.get("models", [])]
            self.q.put(("models", names))
        except Exception as e:
            self.q.put(("status", f"获取模型列表失败: {e}"))

    def _options(self):
        return {
            "temperature": round(float(self.temp_var.get()), 2),
            "top_p": round(float(self.topp_var.get()), 2),
            "num_predict": int(self.maxtok_var.get()),
            "num_ctx": int(self.ctx_var.get()),
        }

    def _screenshot_b64(self):
        """截取当前屏幕并返回 base64（自动缩放到宽度≤1280 以节省 token）；失败返回 None"""
        try:
            import pyautogui
            from PIL import Image
            img = pyautogui.screenshot()
            w, h = img.size
            maxw = 1280
            if w > maxw:
                img = img.resize((maxw, int(h * maxw / w)))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            self.q.put(("status", f"[视觉截图失败] {e}"))
            return None

    def _turn_images(self, model: str, first_step: bool = True):
        """返回本次应附带给模型的图片 base64 列表；无则 None。
        - 手动上传的图片优先（仅首步消费一次）
        - 否则若开启「视觉功能」且当前为视觉模型，自动后台截图"""
        if first_step and self.pending_uploads:
            imgs = self.pending_uploads[:]
            self.pending_uploads = []
            try:
                self.img_status.config(text="")
            except Exception:
                pass
            return imgs
        if self.vision_on.get():
            if not _is_vision(model):
                if first_step:
                    self.q.put(("status",
                        f"⚠ 当前模型 {model} 非视觉模型，自动截图不可见，请改用 qwen3-vl 等视觉模型"))
                return None
            s = self._screenshot_b64()
            if s:
                return [s]
        return None

    def _stream_chat(self, model: str, msgs: list, target: str = "left",
                     images: list = None) -> str:
        """流式请求，chunk 推入队列，返回完整文本。
        target='left' → 推入主聊天框；target='right' → 推入协助回答右窗。
        images 不为空时，把 base64 图片附到请求中最后一条 user 消息，
        供视觉模型查看（自动截图或手动上传）。"""
        req_msgs = [dict(m) for m in msgs]
        if images:
            for i in range(len(req_msgs) - 1, -1, -1):
                if req_msgs[i].get("role") == "user":
                    req_msgs[i].setdefault("images", []).extend(images)
                    break
        payload = {"model": model, "messages": req_msgs, "stream": True,
                   "options": self._options()}
        req = urllib.request.Request(
            self.host_var.get().rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        full = []
        with urllib.request.urlopen(req, timeout=600) as resp:
            for line in resp:
                if self.stop_flag.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                if "error" in obj:
                    raise RuntimeError(obj["error"])
                piece = obj.get("message", {}).get("content", "")
                if piece:
                    full.append(piece)
                    if target == "right":
                        self.q.put(("rchunk", piece))
                    else:
                        self.q.put(("chunk", piece))
                if obj.get("done"):
                    break
        return "".join(full)

    # ================= 发送 / Agent 循环 =================
    def _on_enter(self, event):
        if event.state & 0x0001:
            return None
        self._send()
        return "break"

    def _send(self):
        if self.streaming:
            self.stop_flag.set()
            self.status_var.set("正在停止…")
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self._append_block("你", text, "user_tag")
        self.messages.append({"role": "user", "content": text})
        self.streaming = True
        self.stop_flag.clear()
        self.send_btn.config(text="停止 ■", bg=ERR_CLR)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _build_system(self):
        parts = [self.sys_var.get().strip() or "你是一个高效的助手。"]
        if self.is_agent():
            parts.append(tool_protocol(self.full_access.get(),
                                       self.vision_on.get(), self.periph_on.get()))
        parts.extend(self._skill_texts())
        return "\n\n".join(parts)

    def _worker(self, user_text: str):
        transcript = []
        try:
            agent = self.is_agent()
            multi = self.multi_on.get()

            if multi:
                # ---- 主协模型流程 ----
                main_model = (self.main_model_var.get().strip()
                              or self.model_var.get().strip())
                assistants = [n for n, v in self.assistant_vars.items() if v.get()][:2]
                turn_imgs = self._turn_images(main_model, first_step=True)
                self.q.put(("rclear", None))
                answers = []
                if assistants:
                    for m in assistants:
                        if self.stop_flag.is_set():
                            break
                        self.q.put(("rhead", m))
                        self.q.put(("status", f"[协助 {m}] 精简回答中…"))
                        try:
                            ans = self._stream_chat(m, [
                                {"role": "system",
                                 "content": ("你是协助回答的模型。"
                                              "请用 1-3 句话直接、简洁、清晰地回答用户的问题，"
                                              "不要寒暄、不要重复问题、不要执行任何操作、不要输出 JSON 工具调用。")},
                                {"role": "user", "content": user_text}],
                                target="right", images=turn_imgs)
                        except Exception as e:
                            ans = f"（{m} 回答失败：{e}）"
                            self.q.put(("rchunk", ans + "\n"))
                        answers.append((m, ans))
                # 主模型：综合协助回答 + 完成任务/执行
                last = user_text
                if answers:
                    blk = "\n\n".join(f"【协助模型 {m} 的回答】\n{a}" for m, a in answers)
                    last += (f"\n\n以下是协助模型给出的回答，请综合它们、给出最终结论，"
                             f"并完成用户的任务：\n{blk}")
                msgs = [{"role": "system", "content": self._build_system()}]
                msgs += self.messages[:-1]
                msgs.append({"role": "user", "content": last})
                max_steps = max(1, int(self.max_steps_var.get())) if agent else 1
                self.q.put(("head", (f"主模型 · {main_model}", "ai_tag")))
                self.q.put(("status", "主模型生成中…"))
                for step in range(max_steps):
                    if self.stop_flag.is_set():
                        break
                    head = f"主模型 · {main_model}"
                    if agent and max_steps > 1:
                        head += f" · 第{step + 1}步"
                    self.q.put(("head", (head, "ai_tag")))
                    self.q.put(("status", "生成中…"))
                    imgs = turn_imgs if step == 0 else self._turn_images(main_model, first_step=False)
                    reply = self._stream_chat(main_model, msgs, images=imgs)
                    transcript.append(reply)
                    msgs.append({"role": "assistant", "content": reply})
                    if self.stop_flag.is_set():
                        break
                    call = parse_tool_call(reply) if agent else None
                    if not call:
                        break
                    self.q.put(("status", f"执行工具 {call.get('tool')}…"))
                    result = self._exec_tool(call)
                    self.q.put(("tool", f"⚙ [{call.get('tool')}] {json.dumps({k: v for k, v in call.items() if k != 'tool' and k != 'content'}, ensure_ascii=False)[:300]}\n{result[:3000]}"))
                    transcript.append(f"[工具 {call.get('tool')} 结果] {result[:500]}")
                    if step == max_steps - 1:
                        break
                    msgs.append({"role": "user", "content":
                                 f"[工具执行结果]\n{result[:6000]}\n\n"
                                 "请根据结果继续。若任务已完成，用普通文字总结，不要再输出 JSON。"})
            else:
                # ---- 单模型流程 ----
                exec_model = self.model_var.get().strip()
                msgs = [{"role": "system", "content": self._build_system()}]
                msgs += self.messages[:-1]
                msgs.append({"role": "user", "content": user_text})
                max_steps = max(1, int(self.max_steps_var.get())) if agent else 1
                turn_imgs = self._turn_images(exec_model, first_step=True)
                for step in range(max_steps):
                    if self.stop_flag.is_set():
                        break
                    head = f"回答 · {exec_model}" if not agent else f"AI · {exec_model}"
                    if agent and max_steps > 1:
                        head += f" · 第{step + 1}步"
                    self.q.put(("head", (head, "ai_tag")))
                    self.q.put(("status", "生成中…"))
                    imgs = turn_imgs if step == 0 else self._turn_images(exec_model, first_step=False)
                    reply = self._stream_chat(exec_model, msgs, images=imgs)
                    transcript.append(reply)
                    msgs.append({"role": "assistant", "content": reply})
                    if self.stop_flag.is_set():
                        break
                    call = parse_tool_call(reply) if agent else None
                    if not call:
                        break
                    self.q.put(("status", f"执行工具 {call.get('tool')}…"))
                    result = self._exec_tool(call)
                    self.q.put(("tool", f"⚙ [{call.get('tool')}] {json.dumps({k: v for k, v in call.items() if k != 'tool' and k != 'content'}, ensure_ascii=False)[:300]}\n{result[:3000]}"))
                    transcript.append(f"[工具 {call.get('tool')} 结果] {result[:500]}")
                    if step == max_steps - 1:
                        break
                    msgs.append({"role": "user", "content":
                                 f"[工具执行结果]\n{result[:6000]}\n\n"
                                 "请根据结果继续。若任务已完成，用普通文字总结，不要再输出 JSON。"})
        except urllib.error.URLError as e:
            self.q.put(("chunk_err", f"无法连接 Ollama（{e.reason}）。请先启动：ollama serve"))
        except Exception as e:
            self.q.put(("chunk_err", str(e)))
        finally:
            content = "\n".join(transcript)
            if content:
                self.messages.append({"role": "assistant", "content": content[-8000:]})
            self.q.put(("done", None))

    # ================= 队列 / 渲染 =================
    def _poll_queue(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "chunk":
                    self._insert(data, "body")
                elif kind == "head":
                    text, tag = data
                    self._insert(f"\n{text}\n", tag)
                elif kind == "tool":
                    self._insert("\n" + data + "\n", "tool")
                elif kind == "chunk_err":
                    self._insert("\n[错误] " + str(data) + "\n", "err")
                elif kind == "rhead":
                    self._right_insert(f"\n🤝 {data}\n", "rname")
                elif kind == "rchunk":
                    self._right_insert(data, "rbody")
                elif kind == "rclear":
                    self.right_chat.config(state="normal")
                    self.right_chat.delete("1.0", "end")
                    self.right_chat.config(state="disabled")
                elif kind == "done":
                    self._insert("\n", "body")
                    self.streaming = False
                    self.send_btn.config(text="发送 ▶", bg=ACCENT)
                    self.status_var.set("就绪")
                elif kind == "models":
                    if data:
                        self.known_models = data
                        self.model_box["values"] = data
                        self.main_model_box["values"] = data
                        if self.model_var.get() not in data:
                            self.model_var.set(data[0])
                        if self.main_model_var.get() not in data:
                            self.main_model_var.set(data[0])
                        self._refresh_assistants()
                        self.status_var.set(f"已连接 · 本地共 {len(data)} 个模型")
                elif kind == "status":
                    self.status_var.set(str(data))
        except queue.Empty:
            pass
        self.root.after(60, self._poll_queue)

    def _append_block(self, who, text, tag):
        self.chat.config(state="normal")
        self.chat.insert("end", f"\n{who}\n", tag)
        self.chat.insert("end", text + "\n", "body")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _insert(self, text, tag):
        self.chat.config(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _right_insert(self, text, tag):
        self.right_chat.config(state="normal")
        self.right_chat.insert("end", text, tag)
        self.right_chat.config(state="disabled")
        self.right_chat.see("end")

    def _sys_msg(self, text):
        self.chat.config(state="normal")
        self.chat.insert("end", text + "\n", "sys")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _clear_chat(self):
        if self.streaming:
            self.stop_flag.set()
        self.messages.clear()
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self.right_chat.config(state="normal")
        self.right_chat.delete("1.0", "end")
        self.right_chat.config(state="disabled")
        self._sys_msg("对话已清空。")
        self.status_var.set("就绪")

    # ================= 配置 =================
    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            self.host_var.set(c.get("host", DEFAULT_HOST))
            self.model_var.set(c.get("model", DEFAULT_MODEL))
            self.main_model_var.set(c.get("main_model", self.model_var.get()))
            self.mode_var.set(c.get("mode", "personal"))
            self.full_access.set(c.get("full_access", False))
            self.multi_on.set(c.get("multi_on", False))
            self.vision_on.set(c.get("vision_on", False))
            self.periph_on.set(c.get("periph_on", False))
            self.max_steps_var.set(c.get("max_steps", 8))
            self.sys_var.set(c.get("system", self.sys_var.get()))
            for name in c.get("skills_on", []):
                if name in self.skill_vars:
                    self.skill_vars[name].set(True)
            self._pending_assistants = set(c.get("assistants_on", []))
        except Exception:
            pass

    def _on_close(self):
        try:
            cfg = {
                "host": self.host_var.get(),
                "model": self.model_var.get(),
                "main_model": self.main_model_var.get(),
                "mode": self.mode_var.get(),
                "full_access": self.full_access.get(),
                "multi_on": self.multi_on.get(),
                "vision_on": self.vision_on.get(),
                "periph_on": self.periph_on.get(),
                "max_steps": int(self.max_steps_var.get()),
                "system": self.sys_var.get(),
                "skills_on": [k for k, v in self.skill_vars.items() if v.get()],
                "assistants_on": [k for k, v in self.assistant_vars.items() if v.get()],
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.stop_flag.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
