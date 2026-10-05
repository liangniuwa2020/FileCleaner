@echo off
chcp 65001 >nul
title 冗余与重复文件智能自动处理工具
python main.py
if errorlevel 1 (
    echo 程序运行遇到错误，请检查 Python 及依赖是否正常安装。
    pause
)
