import os
import shutil
import subprocess
from typing import List, Dict, Any, Tuple
import send2trash

class FileOperator:
    """提供各种文件和文件夹安全处理操作"""

    @staticmethod
    def open_in_explorer(path: str) -> bool:
        """在 Windows 资源管理器中打开并定位高亮文件或进入文件夹"""
        if not os.path.exists(path):
            return False
        try:
            if os.path.isfile(path):
                subprocess.Popen(f'explorer /select,"{path}"')
            else:
                subprocess.Popen(f'explorer "{path}"')
            return True
        except Exception as e:
            print(f"Error opening explorer: {e}")
            return False

    @staticmethod
    def open_file_directly(path: str) -> bool:
        """直接用系统默认程序打开文件"""
        if not os.path.exists(path):
            return False
        try:
            os.startfile(path)
            return True
        except Exception as e:
            print(f"Error opening file: {e}")
            return False

    @staticmethod
    def set_system_clipboard(paths: List[str], is_cut: bool = False) -> bool:
        """将文件/文件夹路径设置到 Windows 系统剪贴板（支持在资源管理器按 Ctrl+V 粘贴/移动）"""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QMimeData, QUrl, QByteArray
            import struct

            clipboard = QApplication.clipboard()
            mime = QMimeData()
            urls = []
            for p in paths:
                norm_p = os.path.normpath(p)
                if os.path.exists(norm_p):
                    urls.append(QUrl.fromLocalFile(norm_p))
            if not urls:
                return False
            mime.setUrls(urls)
            # Preferred DropEffect: 2 = DROPEFFECT_MOVE (剪切), 5 = DROPEFFECT_COPY (复制)
            drop_effect_val = 2 if is_cut else 5
            drop_effect_bytes = QByteArray(struct.pack("<I", drop_effect_val))
            mime.setData("Preferred DropEffect", drop_effect_bytes)
            clipboard.setMimeData(mime)
            return True
        except Exception as e:
            print(f"Failed to set Windows system clipboard: {e}")
            return False

    @staticmethod
    def copy_items(src_paths: List[str], target_dir: str, overwrite: bool = False) -> List[Tuple[str, bool, str]]:
        """批量复制文件/文件夹到目标目录"""
        results = []
        target_dir = os.path.normpath(target_dir)
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                return [(p, False, f"无法创建目标目录: {e}") for p in src_paths]

        for p in src_paths:
            norm_p = os.path.normpath(p)
            if not os.path.exists(norm_p):
                results.append((p, False, "源路径不存在"))
                continue
            name = os.path.basename(norm_p)
            dest = os.path.join(target_dir, name)
            try:
                if os.path.isdir(norm_p) and (target_dir == norm_p or target_dir.startswith(norm_p + os.sep)):
                    results.append((p, False, "无法将文件夹复制到自身或其子目录中"))
                    continue

                if os.path.exists(dest) and not overwrite:
                    # 避免覆盖时自动生成序号
                    stem, ext = os.path.splitext(name)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(target_dir, f"{stem}_copy{counter}{ext}")
                        counter += 1

                if os.path.isdir(norm_p):
                    shutil.copytree(norm_p, dest, dirs_exist_ok=overwrite)
                else:
                    shutil.copy2(norm_p, dest)
                results.append((p, True, dest))
            except Exception as e:
                results.append((p, False, str(e)))
        return results

    @staticmethod
    def move_items(src_paths: List[str], target_dir: str, overwrite: bool = False) -> List[Tuple[str, bool, str]]:
        """批量移动/剪切文件或文件夹到目标目录"""
        results = []
        target_dir = os.path.normpath(target_dir)
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                return [(p, False, f"无法创建目标目录: {e}") for p in src_paths]

        for p in src_paths:
            norm_p = os.path.normpath(p)
            if not os.path.exists(norm_p):
                results.append((p, False, "源路径不存在"))
                continue

            # 防止把目录移动到自身或自身子目录下导致死锁
            if os.path.isdir(norm_p) and (target_dir == norm_p or target_dir.startswith(norm_p + os.sep)):
                results.append((p, False, "无法将文件夹移动到其自身或其子目录中"))
                continue

            # 如果源目录所在父目录与目标目录相同
            if os.path.dirname(norm_p) == target_dir:
                results.append((p, False, "源项目已存在于目标目录中"))
                continue

            name = os.path.basename(norm_p)
            dest = os.path.join(target_dir, name)
            try:
                if os.path.exists(dest):
                    if overwrite:
                        if os.path.isdir(dest):
                            shutil.rmtree(dest)
                        else:
                            os.remove(dest)
                    else:
                        stem, ext = os.path.splitext(name)
                        counter = 1
                        while os.path.exists(dest):
                            dest = os.path.join(target_dir, f"{stem}_moved{counter}{ext}")
                            counter += 1
                shutil.move(norm_p, dest)
                results.append((p, True, dest))
            except Exception as e:
                results.append((p, False, str(e)))
        return results

    @staticmethod
    def trash_items(paths: List[str]) -> List[Tuple[str, bool, str]]:
        """安全删除：移到 Windows 回收站"""
        results = []
        for p in paths:
            if not os.path.exists(p):
                results.append((p, False, "路径不存在"))
                continue
            try:
                send2trash.send2trash(p)
                results.append((p, True, "已移至回收站"))
            except Exception as e:
                results.append((p, False, str(e)))
        return results

    @staticmethod
    def delete_permanently(paths: List[str]) -> List[Tuple[str, bool, str]]:
        """永久硬删除"""
        results = []
        for p in paths:
            if not os.path.exists(p):
                results.append((p, False, "路径不存在"))
                continue
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                results.append((p, True, "已永久删除"))
            except Exception as e:
                results.append((p, False, str(e)))
        return results

    @staticmethod
    def rename_item(old_path: str, new_name: str) -> Tuple[bool, str]:
        """重命名单个文件或文件夹"""
        if not os.path.exists(old_path):
            return False, "原文件不存在"
        parent = os.path.dirname(old_path)
        new_path = os.path.join(parent, new_name)
        if os.path.exists(new_path):
            return False, "目标文件名已存在"
        try:
            os.rename(old_path, new_path)
            return True, new_path
        except Exception as e:
            return False, str(e)
