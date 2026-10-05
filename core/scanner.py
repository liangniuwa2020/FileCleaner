import os
import re
import hashlib
from typing import List, Dict, Any, Callable, Optional, Set, Tuple

def get_file_hash(filepath: str, block_size: int = 65536, max_blocks: Optional[int] = None) -> str:
    """计算文件 MD5，对于大文件可限制块数做快速校验"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            blocks = 0
            while True:
                data = f.read(block_size)
                if not data:
                    break
                hasher.update(data)
                blocks += 1
                if max_blocks and blocks >= max_blocks:
                    break
        return hasher.hexdigest()
    except Exception:
        return ""

def get_dir_size(dir_path: str, is_cancelled_callback: Optional[Callable[[], bool]] = None, cache: Optional[Dict[str, int]] = None) -> int:
    """快速递归计算文件夹总字节大小，带缓存与中断检查"""
    if cache is not None and dir_path in cache:
        return cache[dir_path]
    total = 0
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if is_cancelled_callback and is_cancelled_callback():
                    break
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += get_dir_size(entry.path, is_cancelled_callback, cache)
                except Exception:
                    pass
    except Exception:
        pass
    if cache is not None:
        cache[dir_path] = total
    return total

def format_file_size(size_bytes: int) -> str:
    """人类可读的文件大小格式化"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def format_folder_size(size_bytes: int) -> str:
    """文件夹大小格式化：以 GB 为主单位显示"""
    gb = size_bytes / (1024 * 1024 * 1024)
    if gb >= 0.01:
        return f"{gb:.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{gb:.3f} GB ({size_bytes / (1024 * 1024):.1f} MB)"
    elif size_bytes == 0:
        return "0.00 GB (空)"
    else:
        return f"{gb:.4f} GB ({size_bytes / 1024:.1f} KB)"


# 预置的常见冗余文件名称规则与正则
PRESET_RULES = [
    {
        "id": "digits_7",
        "name": "共同包含相同7位数字 (如 张三1234567, 李四 1234567)",
        "pattern": r"(\d{7})",
        "only_duplicates": True,
        "description": "严格筛选出相互包含相同 7 位数字的重复文件夹/文件（排除互不相同的孤立单项）并连续排列"
    },
    {
        "id": "long_digits",
        "name": "包含长串数字/重复数字 (如 1698284729104, 111111)",
        "pattern": r"\d{6,}",
        "description": "匹配包含连续 6 位及以上长串数字或时间戳的文件/文件夹"
    },
    {
        "id": "duplicate_suffix",
        "name": "常见副本/重复命名 (如 (1), (2), - 副本, _copy)",
        "pattern": r"(\s*[\(\（]\d+[\)\）]|\s*[-_]副本|\s*[-_]copy|\s*\(\d+\))$",
        "match_stem": True,  # 只匹配文件名主体部分
        "description": "匹配 Windows 自动生成的 (1)、- 副本 等冗余重复文件"
    },
    {
        "id": "digits_symbols_digits",
        "name": "数字+符号+数字 (如 1024_001, 2023-11-05_01)",
        "pattern": r"\d+[-_#@\.]\d+[-_#@\.]?\d*",
        "description": "匹配类似 多组数字+符号分隔 的冗余编号文件"
    },
    {
        "id": "repeat_digits_sequences",
        "name": "单个数字连续重复3次以上 (如 000, 111, 8888)",
        "pattern": r"(\d)\1{2,}",
        "description": "匹配文件名中出现单个数字连续重复 3 次或更多的模式"
    },
    {
        "id": "list_all",
        "name": "📂 检索/列出所选文件夹内的全部文件 (不过滤规则)",
        "pattern": r".*",
        "description": "不设条件，检索并列出所选文件夹及其子目录内的所有文件与文件夹"
    },
    {
        "id": "temp_and_cache",
        "name": "临时缓存文件 (如 .tmp, .bak, .log, .cache, ~*)",
        "pattern": r"(^~|\.(tmp|bak|old|log|cache|swp|crdownload))$",
        "description": "匹配常见程序产生的临时文件、备份和未完成下载"
    }
]

class FileScanner:
    """多目录多规则的文件与文件夹扫描器"""
    def __init__(self,
                 scan_dirs: List[str],
                 rule_mode: str = "regex",        # "preset", "regex", "hash_duplicate", "name_duplicate"
                 pattern_str: str = "",
                 match_explanation: str = "",
                 match_target: str = "all",       # "files", "dirs", "all"
                 include_subdirs: bool = True,
                 include_dir_contents: bool = True,
                 only_duplicates: bool = False,
                 min_size_bytes: int = 0,
                 max_size_bytes: int = 0,
                 file_extensions: Optional[List[str]] = None,
                 progress_callback: Optional[Callable[[str, int], None]] = None,
                 is_cancelled_callback: Optional[Callable[[], bool]] = None):
        self.scan_dirs = [os.path.abspath(d) for d in scan_dirs if os.path.exists(d)]
        self.rule_mode = rule_mode
        self.pattern_str = pattern_str
        self.match_explanation = match_explanation or f"匹配模式: {pattern_str}"
        self.match_target = match_target
        self.include_subdirs = include_subdirs
        self.include_dir_contents = include_dir_contents
        self.only_duplicates = only_duplicates
        self.min_size_bytes = min_size_bytes
        self.max_size_bytes = max_size_bytes
        self.file_extensions = [ext.lower().strip() for ext in file_extensions] if file_extensions else []
        self.progress_callback = progress_callback
        self.is_cancelled_callback = is_cancelled_callback

        self.dir_size_cache: Dict[str, int] = {}
        self.is_common_rule = False
        self.common_min_len = 4
        self.common_char_type = "all"
        if self.pattern_str and self.pattern_str.startswith("__COMMON__:"):
            parts = self.pattern_str.split(":")
            if len(parts) >= 3:
                self.is_common_rule = True
                try:
                    self.common_min_len = int(parts[1])
                except ValueError:
                    self.common_min_len = 4
                self.common_char_type = parts[2]

        self.compiled_regex = None
        if self.pattern_str and not self.is_common_rule:
            try:
                self.compiled_regex = re.compile(self.pattern_str, re.IGNORECASE)
            except re.error as e:
                print(f"Regex error: {e}")

    @staticmethod
    def _extract_common_features(names: List[str], min_len: int = 4, char_type: str = "all") -> Dict[str, Set[int]]:
        """从候选名称列表中智能提取共同出现>=2次的连续文字/数字特征并完成归类 (毫秒级极速处理)"""
        if char_type == "digit":
            chunk_pattern = r'\d{' + str(min_len) + r',}'
        elif char_type == "chinese":
            chunk_pattern = r'[\u4e00-\u9fa5]{' + str(min_len) + r',}'
        else:
            chunk_pattern = r'[a-zA-Z0-9\u4e00-\u9fa5]{' + str(min_len) + r',}'

        from collections import defaultdict
        sub_map = defaultdict(set)
        for idx, name in enumerate(names):
            chunks = re.findall(chunk_pattern, name)
            seen_subs = set()
            for c in chunks:
                c_len = len(c)
                # 限制最大提取长度至40，防止超长无意义字符串导致组合膨胀
                max_sub_len = min(c_len, 40)
                for l in range(min_len, max_sub_len + 1):
                    for i in range(c_len - l + 1):
                        seen_subs.add(c[i:i+l])
            for sub in seen_subs:
                sub_map[sub].add(idx)

        # 仅保留在 >= 2 个项目中出现的特征
        common = {sub: indices for sub, indices in sub_map.items() if len(indices) >= 2}
        if not common:
            return {}

        # 优化冗余子串剔除：按命中的候选索引集合 (frozenset) 进行快速聚类
        # 在命中相同文件集合的子串中，只保留最长且不被包含的特征串 (O(K) 级毫秒完成)
        groups_by_indices = defaultdict(list)
        for sub, indices in common.items():
            groups_by_indices[frozenset(indices)].append(sub)

        maximal_subs = {}
        for idx_set, subs in groups_by_indices.items():
            subs.sort(key=len, reverse=True)
            kept = []
            for s in subs:
                if not any(s in longer for longer in kept):
                    kept.append(s)
            for s in kept:
                maximal_subs[s] = set(idx_set)

        # 评分排序：优先覆盖项目数多的特征，其次特征长度长的
        sorted_features = sorted(maximal_subs.keys(), key=lambda s: (len(maximal_subs[s]), len(s)), reverse=True)

        assigned_items = set()
        feature_groups = {}
        for feat in sorted_features:
            indices = maximal_subs[feat]
            unassigned = indices - assigned_items
            if len(unassigned) >= 2:
                feature_groups[feat] = indices
                assigned_items.update(indices)
            elif len(unassigned) == 1 and len(indices) >= 2:
                feature_groups[feat] = indices
                assigned_items.update(indices)

        return feature_groups

    def get_match_key(self, name: str, is_dir: bool, full_path: str) -> Tuple[bool, str]:
        if self.match_target == "files" and is_dir:
            return False, ""
        if self.match_target == "dirs" and not is_dir:
            return False, ""

        # 如果指定了扩展名过滤
        if not is_dir and self.file_extensions:
            ext = os.path.splitext(name)[1].lower()
            if ext not in self.file_extensions:
                return False, ""

        # 规则匹配
        if self.is_common_rule:
            if self.common_char_type == "digit":
                pat = rf'\d{{{self.common_min_len},}}'
            elif self.common_char_type == "chinese":
                pat = rf'[\u4e00-\u9fa5]{{{self.common_min_len},}}'
            else:
                pat = rf'[a-zA-Z0-9\u4e00-\u9fa5]{{{self.common_min_len},}}'

            stem, ext = os.path.splitext(name)
            m = re.search(pat, name)
            if not m and not is_dir:
                m = re.search(pat, stem)
            if m:
                # 候选入围，后续统一进行共同特征提取
                return True, ""
            return False, ""

        if self.compiled_regex:
            # 如果是文件，还可以根据需求对 stem 校验
            stem, ext = os.path.splitext(name)
            m = self.compiled_regex.search(name)
            if not m and not is_dir:
                m = self.compiled_regex.search(stem)
            if m:
                matched_key = m.group(1) if m.groups() and m.group(1) else m.group(0)
                return True, matched_key
            return False, ""

        # 若未指定正则或正则为空，默认匹配满足目标类型与扩展名的项
        return True, ""

    def matches_rule(self, name: str, is_dir: bool, full_path: str) -> bool:
        matched, _ = self.get_match_key(name, is_dir, full_path)
        return matched

    def scan(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        visited_paths: Set[str] = set()
        scanned_count = 0

        # 如果是哈希完全重复模式，先收集所有文件按大小分组
        if self.rule_mode == "hash_duplicate":
            return self._scan_hash_duplicates()
        elif self.rule_mode == "name_duplicate":
            return self._scan_name_duplicates()

        for base_dir in self.scan_dirs:
            if self.is_cancelled_callback and self.is_cancelled_callback():
                break

            for root, dirs, files in os.walk(base_dir):
                if self.is_cancelled_callback and self.is_cancelled_callback():
                    break

                scanned_count += len(files) + len(dirs)
                if self.progress_callback and scanned_count % 100 == 0:
                    self.progress_callback(root, scanned_count)

                # 检查文件夹
                if self.match_target in ["dirs", "all"]:
                    for d in dirs:
                        full_dir_path = os.path.join(root, d)
                        if full_dir_path in visited_paths:
                            continue
                        visited_paths.add(full_dir_path)

                        is_matched, match_key = self.get_match_key(d, is_dir=True, full_path=full_dir_path)
                        if is_matched:
                            try:
                                stat = os.stat(full_dir_path)
                                mtime = stat.st_mtime
                            except Exception:
                                mtime = 0
                            results.append({
                                "name": d,
                                "path": full_dir_path,
                                "dir": root,
                                "is_dir": True,
                                "size": 0,
                                "size_str": "",
                                "mtime": mtime,
                                "match_reason": self.match_explanation,
                                "match_key": match_key
                            })

                # 检查文件
                if self.match_target in ["files", "all"]:
                    for f in files:
                        full_file_path = os.path.join(root, f)
                        if full_file_path in visited_paths:
                            continue
                        visited_paths.add(full_file_path)

                        is_matched, match_key = self.get_match_key(f, is_dir=False, full_path=full_file_path)
                        if is_matched:
                            try:
                                stat = os.stat(full_file_path)
                                size = stat.st_size
                                mtime = stat.st_mtime
                            except Exception:
                                size = 0
                                mtime = 0

                            results.append({
                                "name": f,
                                "path": full_file_path,
                                "dir": root,
                                "is_dir": False,
                                "size": size,
                                "size_str": format_file_size(size),
                                "mtime": mtime,
                                "match_reason": self.match_explanation,
                                "match_key": match_key
                            })

                if not self.include_subdirs:
                    break

        # 1. 聚类分析：识别具有共同匹配特征（例如包含相同7位数字 1234567，或相同的4个以上文字/数字）的组
        if self.is_common_rule:
            # 智能提取共同文字/数字特征并归类
            dir_results = [r for r in results if r.get("is_dir")]
            target_list = dir_results if self.match_target == "dirs" else results
            names = [r["name"] for r in target_list]
            feature_groups = self._extract_common_features(names, self.common_min_len, self.common_char_type)

            curr_grp = 1
            for feat, idx_set in feature_groups.items():
                for idx in idx_set:
                    target_list[idx]["group"] = curr_grp
                    target_list[idx]["match_key"] = feat
                    target_list[idx]["match_reason"] = f"[共同包含特征: {feat}] (第{curr_grp}组) {self.match_explanation}"
                curr_grp += 1

            # 共同特征模式下，如勾选“仅筛选相互重复项”或默认，只保留真正成组的项
            if self.only_duplicates:
                results = [r for r in results if r.get("group", 0) > 0]
        else:
            key_counts: Dict[str, int] = {}
            for r in results:
                k = r.get("match_key", "").strip()
                if k and k != ".*":
                    key_counts[k] = key_counts.get(k, 0) + 1

            group_map: Dict[str, int] = {}
            curr_grp = 1
            for r in results:
                k = r.get("match_key", "").strip()
                if k and key_counts.get(k, 0) > 1 and k not in group_map:
                    group_map[k] = curr_grp
                    curr_grp += 1

            # 如果开启了“仅筛选相互重复项 / 共同包含”：
            # 只有在 group_map 中的项（出现次数 >= 2）才保留，彻底排除互不相同的孤立单项！
            if self.only_duplicates:
                results = [r for r in results if r.get("match_key", "").strip() in group_map]

            for r in results:
                k = r.get("match_key", "").strip()
                if k in group_map:
                    grp = group_map[k]
                    r["group"] = grp
                    orig_reason = r.get("match_reason", "")
                    r["match_reason"] = f"[共同包含特征: {k}] (第{grp}组) {orig_reason}"

        # 1.5 如果开启了“文件夹内文件也纳入处理”，仅对最终匹配成功的文件夹展开内部所有子项（绝不盲目扫描全盘）
        if self.include_dir_contents:
            sub_items = []
            for r in results:
                if r.get("is_dir"):
                    parent_path = r["path"]
                    parent_grp = r.get("group", 0)
                    parent_key = r.get("match_key", "")
                    parent_name = r.get("name", "")

                    if self.only_duplicates and parent_grp == 0:
                        continue

                    for sub_root, sub_dirs, sub_files in os.walk(parent_path):
                        if self.is_cancelled_callback and self.is_cancelled_callback():
                            break
                        for sd in sub_dirs:
                            s_dir_path = os.path.join(sub_root, sd)
                            if s_dir_path in visited_paths:
                                continue
                            visited_paths.add(s_dir_path)
                            try:
                                s_mtime = os.stat(s_dir_path).st_mtime
                            except Exception:
                                s_mtime = 0
                            sub_items.append({
                                "name": sd,
                                "path": s_dir_path,
                                "dir": sub_root,
                                "is_dir": True,
                                "size": 0,
                                "size_str": "",
                                "mtime": s_mtime,
                                "group": parent_grp,
                                "match_key": parent_key,
                                "match_reason": f"[所属文件夹包含特征: {parent_key or parent_name}] (第{parent_grp}组)" if parent_grp > 0 else f"所属文件夹匹配: {parent_name}"
                            })

                        for sf in sub_files:
                            s_file_path = os.path.join(sub_root, sf)
                            if s_file_path in visited_paths:
                                continue
                            visited_paths.add(s_file_path)
                            if self.file_extensions:
                                ext = os.path.splitext(sf)[1].lower()
                                if ext not in self.file_extensions:
                                    continue
                            try:
                                s_stat = os.stat(s_file_path)
                                s_size = s_stat.st_size
                                s_mtime = s_stat.st_mtime
                            except Exception:
                                s_size = 0
                                s_mtime = 0
                            sub_items.append({
                                "name": sf,
                                "path": s_file_path,
                                "dir": sub_root,
                                "is_dir": False,
                                "size": s_size,
                                "size_str": format_file_size(s_size),
                                "mtime": s_mtime,
                                "group": parent_grp,
                                "match_key": parent_key,
                                "match_reason": f"[所属文件夹包含特征: {parent_key or parent_name}] (第{parent_grp}组)" if parent_grp > 0 else f"所属文件夹匹配: {parent_name}"
                            })
            results.extend(sub_items)

        # 2. 仅对最终真正符合条件的条目统计实际文件夹大小与应用大小过滤（毫秒级极速完成，不再遍历无关文件夹）
        final_results = []
        for r in results:
            if self.is_cancelled_callback and self.is_cancelled_callback():
                return []
            p = r["path"]
            is_d = r.get("is_dir", False)
            if is_d:
                sz = get_dir_size(p, self.is_cancelled_callback, self.dir_size_cache)
            else:
                sz = r.get("size", 0)

            # 大小过滤
            if self.min_size_bytes > 0 and sz < self.min_size_bytes:
                continue
            if self.max_size_bytes > 0 and sz > self.max_size_bytes:
                continue

            r["size"] = sz
            r["size_str"] = format_folder_size(sz) if is_d else format_file_size(sz)
            final_results.append(r)

        # 3. 排列顺序：
        def sort_key(x):
            grp = x.get("group", 0)
            has_grp = 0 if grp > 0 else 1
            is_d_sort = not x.get("is_dir", False) if self.match_target == "dirs" else x.get("is_dir", False)
            m_key = x.get("match_key", "")
            name_lower = x.get("name", "").lower()
            return (has_grp, grp, m_key, is_d_sort, name_lower)

        final_results.sort(key=sort_key)
        return final_results

    def _scan_hash_duplicates(self) -> List[Dict[str, Any]]:
        """扫描内容完全一致（MD5重复）的文件"""
        size_map: Dict[int, List[str]] = {}
        scanned_count = 0

        # Step 1: 按文件大小分组
        for base_dir in self.scan_dirs:
            for root, dirs, files in os.walk(base_dir):
                if self.is_cancelled_callback and self.is_cancelled_callback():
                    return []
                for f in files:
                    scanned_count += 1
                    if self.progress_callback and scanned_count % 100 == 0:
                        self.progress_callback(root, scanned_count)
                    full_path = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(full_path)
                        if sz > 0:
                            size_map.setdefault(sz, []).append(full_path)
                    except Exception:
                        pass
                if not self.include_subdirs:
                    break

        # Step 2: 对相同大小的文件计算 MD5
        hash_map: Dict[str, List[str]] = {}
        candidates = [paths for sz, paths in size_map.items() if len(paths) > 1]
        for paths in candidates:
            if self.is_cancelled_callback and self.is_cancelled_callback():
                return []
            for p in paths:
                h = get_file_hash(p)
                if h:
                    hash_map.setdefault(h, []).append(p)

        results: List[Dict[str, Any]] = []
        group_idx = 1
        for h, paths in hash_map.items():
            if len(paths) > 1:
                for idx, p in enumerate(paths):
                    try:
                        stat = os.stat(p)
                        sz = stat.st_size
                        mtime = stat.st_mtime
                    except Exception:
                        sz = 0
                        mtime = 0
                    results.append({
                        "name": os.path.basename(p),
                        "path": p,
                        "dir": os.path.dirname(p),
                        "is_dir": False,
                        "size": sz,
                        "size_str": format_file_size(sz),
                        "mtime": mtime,
                        "match_reason": f"内容完全相同 (第{group_idx}组 MD5: {h[:8]})",
                        "group": group_idx,
                        "is_original": (idx == 0)
                    })
                group_idx += 1
        return results

    def _scan_name_duplicates(self) -> List[Dict[str, Any]]:
        """
        同名查重模式：
        1. 若指定了规则/关键字（self.compiled_regex），仅检索符合该规则/关键字的条目进行同名比对（例如搜包含7位数字的同名文件）。
        2. 文件与文件夹分别查重（文件只与同名文件匹配，文件夹只与同名文件夹匹配）。
        3. 多个大文件夹时：仅在不同大文件夹之间进行同名查重（同一个大文件夹内部不查同名，排除同一个大目录内的重复项）。
        4. 仅单个大文件夹时：在该大文件夹内部的不同子目录之间进行同名查重。
        """
        is_multi_base = len(self.scan_dirs) > 1
        # key: (is_dir: bool, lower_name: str) -> 确保文件和文件夹独立查重，不发生混杂
        name_map: Dict[Tuple[bool, str], List[Dict[str, Any]]] = {}

        for base_idx, base_dir in enumerate(self.scan_dirs):
            norm_base = os.path.normpath(base_dir).lower()
            for root, dirs, files in os.walk(base_dir):
                if self.is_cancelled_callback and self.is_cancelled_callback():
                    return []

                # 如果检索对象包含文件夹
                if self.match_target in ["dirs", "all"]:
                    for d in dirs:
                        full_dir_path = os.path.join(root, d)
                        # 忽略根搜寻目录本身
                        if os.path.normpath(full_dir_path).lower() == norm_base:
                            continue

                        # 若指定了规则模式（如包含7位数字），不符合规则的文件夹不参与同名查重
                        if self.compiled_regex and not self.matches_rule(d, is_dir=True, full_path=full_dir_path):
                            continue

                        name_map.setdefault((True, d.lower()), []).append({
                            "name": d,
                            "path": full_dir_path,
                            "dir": root,
                            "is_dir": True,
                            "base_idx": base_idx,
                            "base_dir": base_dir
                        })

                # 如果检索对象包含文件
                if self.match_target in ["files", "all"]:
                    for f in files:
                        full_file_path = os.path.join(root, f)
                        # 如果有扩展名过滤
                        if self.file_extensions:
                            ext = os.path.splitext(f)[1].lower()
                            if ext not in self.file_extensions:
                                continue

                        # 若指定了规则模式，不符合规则的文件不参与同名查重
                        if self.compiled_regex and not self.matches_rule(f, is_dir=False, full_path=full_file_path):
                            continue

                        name_map.setdefault((False, f.lower()), []).append({
                            "name": f,
                            "path": full_file_path,
                            "dir": root,
                            "is_dir": False,
                            "base_idx": base_idx,
                            "base_dir": base_dir
                        })

                if not self.include_subdirs:
                    break

        results: List[Dict[str, Any]] = []
        group_idx = 1

        # 排序 keys，使得同名文件先分组，同名文件夹后分组，组内按名称排序
        sorted_keys = sorted(name_map.keys(), key=lambda k: (k[0], k[1]))

        for (is_d, lower_name) in sorted_keys:
            items = name_map[(is_d, lower_name)]
            if len(items) <= 1:
                continue

            # 多个大文件夹时刻：必须来自不同的大文件夹（base_idx 不同），且同一个大文件夹内部不重复列出
            if is_multi_base:
                bases = set(it["base_idx"] for it in items)
                if len(bases) <= 1:
                    # 全部来自同一个大文件夹内部，跳过！
                    continue
                # 针对不同的大文件夹，每个大文件夹仅取最先扫描到的1个，严格做到“大文件夹之间比对，不对同一个大文件夹内部进行匹配”
                unique_base_items = []
                seen_bases = set()
                for it in items:
                    b_id = it["base_idx"]
                    if b_id not in seen_bases:
                        seen_bases.add(b_id)
                        unique_base_items.append(it)
                if len(unique_base_items) <= 1:
                    continue
                effective_items = unique_base_items
            else:
                effective_items = items

            # 检查是否有大小过滤并进行初筛
            valid_items = []
            for it in effective_items:
                p = it["path"]
                sz = get_dir_size(p, self.is_cancelled_callback, self.dir_size_cache) if is_d else 0
                if not is_d:
                    try:
                        sz = stat.st_size
                    except Exception:
                        sz = 0

                # 大小过滤
                if self.min_size_bytes > 0 and sz < self.min_size_bytes:
                    continue
                if self.max_size_bytes > 0 and sz > self.max_size_bytes:
                    continue

                valid_items.append({
                    **it,
                    "size": sz,
                    "mtime": mtime
                })

            if len(valid_items) <= 1:
                continue

            type_label = "同名文件夹" if is_d else "同名文件"
            for idx, it in enumerate(valid_items):
                p = it["path"]
                sz = it["size"]
                mtime = it["mtime"]

                if is_multi_base:
                    base_name = os.path.basename(it["base_dir"])
                    reason_desc = f"[第{group_idx}组 {type_label}] 跨目录重复 (来自: {base_name})"
                else:
                    reason_desc = f"[第{group_idx}组 {type_label}] 路径内重复"

                results.append({
                    "name": it["name"],
                    "path": p,
                    "dir": it["dir"],
                    "is_dir": is_d,
                    "size": sz,
                    "size_str": format_folder_size(sz) if is_d else format_file_size(sz),
                    "mtime": mtime,
                    "match_reason": reason_desc,
                    "match_key": it.get("match_key", it["name"]),
                    "group": group_idx,
                    "is_original": (idx == 0)
                })
            group_idx += 1

        # 排列顺序：把同名文件优先列出在前（is_dir == False），同名文件夹列在后，同组文件相邻
        results.sort(key=lambda x: (x.get("is_dir", False), x.get("group", 0), x.get("path", "").lower()))
        return results
