import re
from typing import Tuple, Optional, Dict, Any

CHINESE_NUM_MAP = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
}

def parse_chinese_number(s: str) -> Optional[int]:
    """将数字字符或中文数字转为整数，如 '7' -> 7, '七' -> 7, '十' -> 10, '12' -> 12, 'N' -> 4"""
    s = s.strip().lower()
    if s in ('n', 'x', '几', '若干', '某'):
        return 4
    if s.isdigit():
        return int(s)
    if s in CHINESE_NUM_MAP:
        return CHINESE_NUM_MAP[s]
    # 处理如 "十二", "二十" 等简单中文数字
    if len(s) == 2:
        if s[0] == '十' and s[1] in CHINESE_NUM_MAP:
            return 10 + CHINESE_NUM_MAP[s[1]]
        if s[1] == '十' and s[0] in CHINESE_NUM_MAP:
            return CHINESE_NUM_MAP[s[0]] * 10
    return None

class NaturalRuleParser:
    """
    中文自然语言规则解析器：
    支持用户用自然中文表达检索要求，并自动转换为等效的正则表达式和可读解释。
    """

    @classmethod
    def parse(cls, prompt: str) -> Tuple[str, str]:
        """
        解析自然语言规则，返回 (regex_pattern, human_explanation)
        """
        raw = prompt.strip()
        if not raw:
            return r".*", "匹配所有文件"

        # 归一化输入：容错常见语音/拼音错别字（如 '货' -> '或'）
        raw = raw.replace('货', '或')
        text = raw.lower()

        # 1. 用户直接输入的是正则表达式 (比如包含 \d 或 .* 等)
        if any(c in raw for c in [r'\d', r'\w', r'\s', r'^\d', r'(?', r'{', r'}']) and not any(zh in raw for zh in ['个', '位', '数字', '相同', '包含', '重复']):
            return raw, f"直接使用正则表达式: {raw}"

        # 1.5 包含具体的 4 位及以上长数字/特定编号（例如 "包含1234567", "共同包含1234567 7个数字", "1234567"）
        long_nums = re.findall(r'[0-9]{4,}', text)
        if long_nums:
            spec_num = long_nums[0]
            return re.escape(spec_num), f"包含特定编号「{spec_num}」并连续排列"

        # 2. 匹配 "连续N位相同单一数字" / "同一个数字连续重复N次" (如 8888888, 111111)
        m1 = re.search(r'(?:连续|同一个)([0-9一二两三四五六七八九十]+)\s*(?:位|个)?\s*(?:相同单一数字|完全相同数字|单数字连续重复)', text)
        if m1:
            n = parse_chinese_number(m1.group(1))
            if n and n >= 2:
                pattern = rf'(\d)\1{{{n - 1}}}'
                return pattern, f"连续 {n} 位完全相同的单一数字 (如 {'8' * n})"

        # 3. 匹配 "相同/共同包含 N 个以上 文字/数字/汉字/字符" 或 "N个相同文字或数字"
        # 例如: "N个相同文字货数字", "4个以上相同文字或数字", "4个相同文字或数字", "7位相同数字", "共同包含4位数字"
        m_common = re.search(
            r'(?:共同|相互|至少|超过|相同)?\s*(?:包含|具有|带有|含有|的)?\s*'
            r'([0-9一二两三四五六七八九十nx几若干]+)\s*(?:位|个|字)?\s*(?:以[上下]|起|多)?\s*(?:个|位|字)?\s*'
            r'(?:相同|重复|共同)?\s*'
            r'(文字或数字|字符或数字|汉字或数字|汉字与数字|文字与数字|汉字|文字|字符|数字|字母)?',
            text
        )
        if m_common and (any(k in text for k in ['相同', '共同', '重复', '查重']) or any(k in text for k in ['文字', '字符', '汉字', '以上', '至少', '多'])):
            num_str = m_common.group(1)
            type_str = m_common.group(2) or "文字或数字"
            n = parse_chinese_number(num_str)
            if n and 2 <= n <= 50:
                if type_str == "数字":
                    return f"__COMMON__:{n}:digit", f"共同包含相同 {n} 位及以上数字 (智能比对提取相同编号/特征并连续排列)"
                elif type_str == "汉字":
                    return f"__COMMON__:{n}:chinese", f"共同包含相同 {n} 个及以上汉字 (智能比对提取相同词组/标题并连续排列)"
                else:
                    return f"__COMMON__:{n}:all", f"共同包含相同 {n} 个及以上文字或数字 (智能比对提取相同特征并连续排列)"

        # 3.5 泛指 "相同文字" / "相同数字"（未明确输入字数时默认4位起查）
        if any(k in text for k in ['相同数字', '共同数字', '重复数字']):
            return "__COMMON__:4:digit", "共同包含相同 4 位及以上数字 (智能比对提取相同编号并连续排列)"
        if any(k in text for k in ['相同文字', '共同文字', '重复文字', '相同字符', '相同汉字']):
            return "__COMMON__:4:all", "共同包含相同 4 个及以上文字或数字 (智能比对提取相同特征并连续排列)"

        # 4. 匹配 "数字+符号+数字" / "多组数字和符号"
        # 例如: "数字+符号+数字", "数字和符号和数字", "数字加符号加数字"
        if re.search(r'数字\s*(?:\+|加|和|带|符号)+\s*数字', text):
            pattern = r'\d+[-_#@\.\+\s]+\d+'
            return pattern, "包含「数字 + 特殊符号(-_#@.等) + 数字」的结构 (如 2023_01, 1024-88)"

        if '长串数字' in text or '长数字' in text or '多位数字' in text:
            return r'\d{6,}', "包含 6 位及以上长串数字 (如 20240928, 1698382910)"

        # 5. 匹配副本 / 重复文件 / 括号数字
        # 例如: "副本文件", "带括号数字", "重复副本"
        if any(k in text for k in ['副本', 'copy', '括号数字', '(1)', '备份文件']):
            pattern = r'(\s*[\(\（]\d+[\)\）]|\s*[-_]副本|\s*[-_]copy)'
            return pattern, "Windows 自动副本标记 (如 '(1)', '- 副本', '_copy')"

        # 6. 匹配特定前缀 / 开头是 / 以...开头
        # 例如: "以IMG开头的", "开头是test", "前缀是photo"
        m_start = re.search(r'(?:以|开头是|前缀是|开头为)\s*([a-zA-Z0-9_\-]+)', text)
        if m_start:
            prefix = m_start.group(1)
            pattern = rf'^{re.escape(prefix)}'
            return pattern, f"以「{prefix}」开头的文件或文件夹"

        # 7. 匹配特定后缀 / 结尾是 / 以...结尾
        # 例如: "以_bak结尾", "结尾是temp"
        m_end = re.search(r'(?:以|结尾是|后缀是|结尾为)\s*([a-zA-Z0-9_\-]+)\s*(?:结尾)?', text)
        if m_end and '开头' not in text:
            suffix = m_end.group(1)
            pattern = rf'{re.escape(suffix)}$'
            return pattern, f"以「{suffix}」结尾的文件或文件夹"

        # 8. 匹配包含纯字母 / 包含中文
        if '包含中文' in text or '有中文' in text or '带汉字' in text:
            return r'[\u4e00-\u9fa5]+', "包含中文字符的文件或文件夹"
        if '纯英文' in text or '全英文' in text:
            return r'^[a-zA-Z0-9_\-\.\s]+$', "不包含中文字符的纯英文字符命名"

        # 9. 匹配包含特定关键词
        # 例如: "包含demo的文件", "名字里有test"
        m_contain = re.search(r'(?:包含|名字里有|含有|带有)\s*([^\s]+)', text)
        if m_contain:
            kw = m_contain.group(1).replace("的文件", "").replace("文件夹", "").strip()
            if kw:
                pattern = re.escape(kw)
                return pattern, f"文件名包含关键词「{kw}」"

        # 10. 默认兜底：如果就是普通文字，转义后做模糊包含
        return re.escape(raw), f"包含文本「{raw}」"
