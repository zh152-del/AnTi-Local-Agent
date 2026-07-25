# -*- coding: utf-8 -*-
"""AnTi 安装程序：把同目录的 AnTi.exe 安装到本地程序目录，
并建立桌面 / 开始菜单快捷方式。纯本地，无需联网。"""
import os
import sys
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

BG = "#ffffff"
PANEL = "#f3f5f8"
FG = "#1f2328"
DIM = "#69707d"
ACCENT = "#2563eb"
ACCENT_HI = "#1d4ed8"


def resource_path(rel):
    """打包后从 _MEIPASS 取资源，未打包时从脚本目录取。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def source_exe():
    """优先使用打包进安装程序内部的 AnTi.exe，其次同目录查找。"""
    bundled = resource_path("AnTi.exe")
    if os.path.exists(bundled):
        return bundled
    d = os.path.dirname(os.path.abspath(sys.executable))
    p = os.path.join(d, "AnTi.exe")
    return p if os.path.exists(p) else None


def default_target():
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(base, "AnTi")


def make_shortcut(lnk, target, workdir, desc):
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(lnk)
        sc.TargetPath = target
        sc.WorkingDirectory = workdir
        sc.IconLocation = target + ",0"
        sc.Description = desc
        sc.Save()
        return True
    except Exception as e:
        return "快捷方式创建失败: " + str(e)


class Installer:
    def __init__(self, root):
        self.root = root
        root.title("AnTi 安装程序")
        root.geometry("520x460")
        root.resizable(False, False)
        root.configure(bg=BG)

        # 图标
        try:
            ico = resource_path(os.path.join("assets", "anti_icon.ico"))
            if os.path.exists(ico):
                root.iconbitmap(ico)
        except Exception:
            pass

        # 标题
        tk.Label(root, text="AnTi · 本地 Agent 助手", bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 15, "bold"), anchor="w",
                 padx=18, pady=14).pack(fill="x")
        tk.Label(root, text="纯本地运行的 AI Agent（可操控文件 / 命令 / 鼠标键盘 / 视觉），需本机 Ollama。",
                 bg=BG, fg=DIM, font=("Microsoft YaHei UI", 9), anchor="w",
                 padx=18).pack(fill="x")

        # 安装路径
        f1 = tk.Frame(root, bg=BG)
        f1.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(f1, text="安装位置", bg=BG, fg=DIM, font=("Microsoft YaHei UI", 9),
                 anchor="w").pack(fill="x")
        row = tk.Frame(f1, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.target_var = tk.StringVar(value=default_target())
        self.path_entry = tk.Entry(row, textvariable=self.target_var, bg="white",
                                    fg=FG, relief="solid",
                                    highlightbackground="#d0d7de", highlightthickness=1,
                                    font=("Consolas", 9))
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(row, text="浏览…", command=self._browse, bg=PANEL, fg=FG,
                  relief="flat", font=("Microsoft YaHei UI", 9), padx=10,
                  cursor="hand2").pack(side="right", padx=(6, 0))

        # 选项
        f2 = tk.Frame(root, bg=BG)
        f2.pack(fill="x", padx=18, pady=(10, 4))
        self.desk_var = tk.BooleanVar(value=True)
        self.menu_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f2, text="创建桌面快捷方式", variable=self.desk_var,
                       bg=BG, fg=FG, anchor="w", font=("Microsoft YaHei UI", 9),
                       selectcolor="white").pack(fill="x", pady=2)
        tk.Checkbutton(f2, text="创建开始菜单快捷方式", variable=self.menu_var,
                       bg=BG, fg=FG, anchor="w", font=("Microsoft YaHei UI", 9),
                       selectcolor="white").pack(fill="x", pady=2)

        # 日志
        f3 = tk.Frame(root, bg=BG)
        f3.pack(fill="both", expand=True, padx=18, pady=(6, 4))
        self.log = tk.Text(f3, bg=PANEL, fg=FG, relief="solid",
                            highlightbackground="#d0d7de", highlightthickness=1,
                            wrap="word", font=("Consolas", 9), height=8,
                            state="disabled", padx=8, pady=6)
        self.log.pack(fill="both", expand=True)

        # 按钮
        f4 = tk.Frame(root, bg=BG)
        f4.pack(fill="x", padx=18, pady=(6, 14))
        self.install_btn = tk.Button(f4, text="安装", command=self._install,
                                     bg=ACCENT, fg="white", relief="flat",
                                     font=("Microsoft YaHei UI", 10, "bold"),
                                     padx=22, cursor="hand2",
                                     activebackground=ACCENT_HI, activeforeground="white")
        self.install_btn.pack(side="right", padx=(8, 0))
        tk.Button(f4, text="退出", command=root.destroy, bg=PANEL, fg=FG,
                  relief="flat", font=("Microsoft YaHei UI", 10), padx=18,
                  cursor="hand2").pack(side="right")

        self.src = source_exe()
        if not self.src:
            self._log("⚠ 安装包内未找到 AnTi.exe，安装程序可能已损坏。")
            self.install_btn.config(state="disabled")
        else:
            self._log("就绪：AnTi 已内置，点击「安装」即可释放到本地。")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.target_var.get())
        if d:
            self.target_var.set(d)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.config(state="disabled")
        self.log.see("end")

    def _install(self):
        self.install_btn.config(state="disabled")
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        try:
            target = self.target_var.get().strip()
            if not target:
                self._log("✗ 安装路径为空")
                return
            os.makedirs(target, exist_ok=True)
            dst = os.path.join(target, "AnTi.exe")
            self._log("复制程序到 %s …" % dst)
            shutil.copyfile(self.src, dst)
            self._log("✓ 程序已安装")

            if self.desk_var.get():
                desk = os.path.join(os.path.expanduser("~"), "Desktop")
                lnk = os.path.join(desk, "AnTi.lnk")
                r = make_shortcut(lnk, dst, target, "AnTi 本地 Agent 助手")
                self._log(("✓ 桌面快捷方式: " + lnk) if r is True else "✗ " + str(r))

            if self.menu_var.get():
                menu = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                    "Microsoft", "Windows", "Start Menu", "Programs")
                try:
                    os.makedirs(menu, exist_ok=True)
                    lnk = os.path.join(menu, "AnTi.lnk")
                    r = make_shortcut(lnk, dst, target, "AnTi 本地 Agent 助手")
                    self._log(("✓ 开始菜单快捷方式: " + lnk) if r is True else "✗ " + str(r))
                except Exception as e:
                    self._log("✗ 开始菜单快捷方式失败: " + str(e))

            self._log("安装完成！双击桌面 AnTi 即可使用。")
            self._log("（首次使用请先启动 Ollama：ollama serve）")
        except Exception as e:
            self._log("✗ 安装出错: " + str(e))
        finally:
            self.install_btn.config(state="normal")


def main():
    root = tk.Tk()
    Installer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
