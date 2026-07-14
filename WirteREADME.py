import os
import yaml
from collections import Counter
from datetime import datetime


# 用于定位自动生成章节的标记
MARKER_START = "<!-- BEGIN_POC_STATS -->"
MARKER_END = "<!-- END_POC_STATS -->"

# 严重性标准排序
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info", "unknown"]

# 严重性拼写纠错映射
SEVERITY_NORMALIZE = {
    "meduim": "medium",
    "hight": "high",
    "cretical": "critical",
    "criticall": "critical",
    "ciritical": "critical",
    "cirtical": "critical",
    "severe": "critical",
    "informative": "info",
    "none": "unknown",
    "__cve_severity__": "unknown",
    "highx": "high",
}


def _parse_info(data):
    """从 YAML data 中安全提取 info 字典."""
    if not isinstance(data, dict):
        return {}
    info = data.get("info")
    return info if isinstance(info, dict) else {}


def process_yaml_file(file_path):
    """解析单个 YAML 文件，返回 (tags, severity, category)."""
    try:
        with open(file_path, "rb") as f:
            data = yaml.safe_load(f)
        info = _parse_info(data)

        tags_str = info.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",")] if isinstance(tags_str, str) and tags_str.strip() else []

        severity = info.get("severity")
        if severity is not None:
            severity = str(severity).lower().strip()
            # 归一化常见拼写错误
            if severity in SEVERITY_NORMALIZE:
                severity = SEVERITY_NORMALIZE[severity]

        # 从路径提取分类目录名
        norm = file_path.replace("\\", "/")
        parts = norm.split("/")
        category = parts[-2] if len(parts) >= 2 else "other"

        return tags, severity, category
    except Exception:
        return [], None, None


def collect_stats(poc_directory):
    """单次遍历收集所有统计信息."""
    print("[+] 正在收集 POC 统计信息...")

    yaml_files = []
    for root, _, files in os.walk(poc_directory):
        for f in files:
            if f.endswith((".yaml", ".yml")):
                yaml_files.append(os.path.join(root, f))

    total_files = len(yaml_files)
    print(f"    发现 {total_files} 个 YAML 文件")
    print("[+] 正在解析 YAML 文件（多进程并行）...")

    all_tags = []
    severities = []
    category_counts = Counter()

    from multiprocessing import Pool
    with Pool(8) as pool:
        done = 0
        for tags, severity, category in pool.imap_unordered(process_yaml_file, yaml_files, chunksize=200):
            all_tags.extend(tags)
            if severity:
                severities.append(severity)
            if category:
                category_counts[category] += 1
            done += 1
            if done % 5000 == 0:
                print(f"    进度: {done}/{total_files} ({done*100//total_files}%)")

    print(f"    完成: {done}/{total_files}")
    return total_files, all_tags, severities, category_counts


def _fmt(n):
    """千分位格式化数字."""
    return f"{n:,}"


def _severity_sort_key(item):
    """按严重性标准顺序排序."""
    sev, _ = item
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return len(SEVERITY_ORDER)


def generate_stats_section(current_time, total_files, dir_count,
                           top_tags, top_severities, top_categories):
    """生成 Markdown 统计章节."""
    lines = [MARKER_START, ""]

    # === 概览 ===
    lines.append("## :bar_chart: POC 统计概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|:-----|:----:|")
    lines.append(f"| **更新时间** | `{current_time}` |")
    lines.append(f"| **POC 总数** | {_fmt(total_files)} |")
    lines.append(f"| **分类数量** | {dir_count} |")
    lines.append("")

    # === 标签 Top 10 ===
    lines.append("### :label: 标签 Top 10")
    lines.append("")
    lines.append("| # | 标签 | 数量 |")
    lines.append("|:---:|:-----|:----:|")
    for i, (tag, count) in enumerate(top_tags, 1):
        lines.append(f"| {i} | `{tag}` | {_fmt(count)} |")
    lines.append("")

    # === 分类 Top 10 ===
    lines.append("### :open_file_folder: 分类 Top 10")
    lines.append("")
    lines.append("| # | 分类 | 数量 |")
    lines.append("|:---:|:-----|:----:|")
    for i, (cat, count) in enumerate(top_categories, 1):
        lines.append(f"| {i} | `{cat}` | {_fmt(count)} |")
    lines.append("")

    # === 严重性分布 ===
    lines.append("### :warning: 严重性分布")
    lines.append("")
    lines.append("| 严重性 | 数量 |")
    lines.append("|:------|:----:|")
    for severity, count in top_severities:
        label = severity.capitalize()
        lines.append(f"| {label} | {_fmt(count)} |")
    lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def update_readme(stats_section):
    """将统计章节写入 README.md."""
    readme_path = "README.md"

    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("[x] README.md 不存在")
        return False

    start_idx = content.find(MARKER_START)
    end_idx = content.find(MARKER_END)

    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + stats_section + content[end_idx + len(MARKER_END):]
        print("[+] 替换已有统计章节")
    else:
        # 首次插入：在第一组空行后（即简介段落之后）
        insert_pos = content.find("\n\n\n")
        if insert_pos == -1:
            insert_pos = content.find("\n## ")
        if insert_pos == -1:
            insert_pos = len(content.rstrip())
            content += "\n\n"
        new_content = content[:insert_pos] + "\n\n" + stats_section + "\n" + content[insert_pos:]
        print("[+] 首次插入统计章节")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def write_readme():
    """主入口：收集统计数据并更新 README."""
    poc_directory = "poc"

    total_files, all_tags, severities, category_counts = collect_stats(poc_directory)

    dir_count = len(category_counts)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    top_tags = Counter(all_tags).most_common(10)
    top_categories = category_counts.most_common(10)
    sev_counter = Counter(severities)
    top_severities = sorted(sev_counter.items(), key=_severity_sort_key)

    print(f"\n[+] 统计结果:")
    print(f"    POC 总数:    {total_files}")
    print(f"    分类数量:    {dir_count}")
    print(f"    唯一标签数:  {len(Counter(all_tags))}")
    print(f"    前 3 标签:   {', '.join(t for t, _ in top_tags[:3])}")
    print(f"    前 3 分类:   {', '.join(c for c, _ in top_categories[:3])}")

    stats_section = generate_stats_section(
        current_time, total_files, dir_count,
        top_tags, top_severities, top_categories,
    )

    if update_readme(stats_section):
        print(f"[+] README.md 更新完成 ({current_time})")


if __name__ == "__main__":
    write_readme()
