# -*- coding: utf-8 -*-
"""部署：把单个自包含安装包 AnTi-Setup.exe 放到桌面。"""
import os
import shutil
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "AnTi-Setup.exe")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
DST = os.path.join(DESKTOP, "AnTi-Setup.exe")


def main():
    if not os.path.exists(SRC):
        print("ERROR: 未找到 %s，打包可能未完成。" % SRC)
        sys.exit(1)
    os.makedirs(DESKTOP, exist_ok=True)
    shutil.copyfile(SRC, DST)
    print("已部署: %s (%d 字节)" % (DST, os.path.getsize(DST)))


if __name__ == "__main__":
    main()
