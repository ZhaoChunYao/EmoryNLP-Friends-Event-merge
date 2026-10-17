import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

INPUT_FILE = "candidates.jsonl"
OUTPUT_ROOT = Path("episode")
LOG_FILE = Path("split_debug.log")

CONTEXT_CHARS = 200  # 报错位置前后打印多少字符


def extract_episode_scene(custom_id: str) -> Tuple[str, str]:
    # custom_id like: s01_e07__scene_008
    if "__" not in custom_id:
        return custom_id, "scene_unknown"
    ep, scene = custom_id.split("__", 1)
    return ep, scene


def extract_output_text(body: Dict[str, Any]) -> Optional[str]:
    """
    response.body.output -> find type=message -> content -> type=output_text -> text
    """
    out = body.get("output")
    if not isinstance(out, list):
        return None

    for block in out:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "message":
            continue
        content = block.get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "output_text":
                t = c.get("text")
                return t if isinstance(t, str) else None
    return None


def strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # 去掉开头 ```json 或 ``` 之类
        t = re.sub(r"^\s*```[a-zA-Z]*\s*", "", t)
        # 去掉结尾 ```
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def trim_to_outermost_object(text: str) -> str:
    """
    截取第一个 { 到最后一个 }，用于处理前后夹杂多余文本的情况。
    """
    l = text.find("{")
    r = text.rfind("}")
    if l != -1 and r != -1 and r > l:
        return text[l : r + 1]
    return text


def loads_maybe_double(text: str) -> Any:
    """
    解析 JSON；如果解析结果是 str，说明是“双重 JSON”，再 loads 一次。
    """
    obj = json.loads(text)
    if isinstance(obj, str):
        obj = json.loads(obj)
    return obj


def try_parse_output_text(output_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    返回 (data_dict_or_none, parse_mode_str_or_error_tag)
    parse_mode 用于记录是怎么解析成功的。
    """
    t = strip_code_fences(output_text)

    # 1) 直接 loads / 双重 loads
    try:
        obj = loads_maybe_double(t)
        if isinstance(obj, dict):
            return obj, "direct_or_double"
    except json.JSONDecodeError:
        pass

    # 2) 截取最外层 { ... } 再 loads
    t2 = trim_to_outermost_object(t)
    if t2 != t:
        try:
            obj = loads_maybe_double(t2)
            if isinstance(obj, dict):
                return obj, "trim_outer_object"
        except json.JSONDecodeError:
            pass

    return None, None


def format_context(text: str, pos: int, radius: int = CONTEXT_CHARS) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    snippet = text[start:end]
    # 用 repr 保留不可见字符、转义等
    return f"pos={pos}, len={len(text)}, slice=[{start}:{end}] => {repr(snippet)}"


def salvage_tuples(output_text: str) -> Optional[Dict[str, Any]]:
    """
    当 JSON 截断导致 Unterminated string 时，尽量抢救 tuples 数组中已完整的元素。
    只支持目标结构包含 "tuples":[ ... ] 的情况。
    返回 {"tuples": [...]} 或 None
    """
    t = strip_code_fences(output_text)

    # 尝试先把双重 JSON 解一层（如果是完整的那种还能成功）
    # 截断场景通常会失败，所以只是尽力。
    try:
        maybe = json.loads(t)
        if isinstance(maybe, str):
            t = maybe
    except Exception:
        pass

    # 找到 "tuples" 数组开始位置
    m = re.search(r'"tuples"\s*:\s*\[', t)
    if not m:
        return None

    i = m.end()  # 指向 '[' 后面
    dec = json.JSONDecoder()
    tuples: List[Any] = []

    # 从数组内部开始，逐个 raw_decode
    while i < len(t):
        # 跳过空白和逗号
        while i < len(t) and t[i] in " \t\r\n,":
            i += 1
        if i >= len(t):
            break
        # 数组结束
        if t[i] == "]":
            break

        # 期望下一个元素是一个 JSON 对象（你的 tuples 元素是 dict）
        try:
            obj, j = dec.raw_decode(t, i)
        except json.JSONDecodeError:
            # 到这里通常就是截断/坏字符，从此处起无法再解析更多元素
            break

        tuples.append(obj)
        i = j

        # 继续循环解析下一个元素

    if not tuples:
        return None
    return {"tuples": tuples}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def log_line(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> None:
    if LOG_FILE.exists():
        # 每次运行从头记录（你想追加也行，把这行删掉）
        LOG_FILE.unlink()

    total = 0
    ok = 0
    salvaged = 0
    failed = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            total += 1

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                failed += 1
                msg = f"[LINE_JSON_ERROR] line_no={line_no} err={e}"
                print(msg)
                log_line(msg)
                continue

            custom_id = item.get("custom_id", f"line_{line_no}")
            resp = (item.get("response") or {})
            status_code = resp.get("status_code")
            if status_code != 200:
                msg = f"[SKIP_NON_200] {custom_id} status_code={status_code}"
                print(msg)
                log_line(msg)
                continue

            body = (resp.get("body") or {})
            output_text = extract_output_text(body)
            if not output_text:
                failed += 1
                msg = f"[NO_OUTPUT_TEXT] {custom_id} line_no={line_no}"
                print(msg)
                log_line(msg)
                continue

            ep, scene = extract_episode_scene(custom_id)
            out_dir = OUTPUT_ROOT / ep
            ensure_dir(out_dir)

            # 先尝试正常解析
            data, mode = try_parse_output_text(output_text)
            if data is not None:
                ok += 1
                out_path = out_dir / f"{scene}.json"
                write_json(out_path, data)
                print(f"[OK] {custom_id} -> {out_path} (mode={mode})")
                continue

            # 到这里说明解析失败：我们要精确 debug
            # 直接做一次 json.loads 来拿到 JSONDecodeError 的 pos
            t = strip_code_fences(output_text)
            try:
                _ = json.loads(t)
                # 如果居然成功但不是 dict，那也记录一下
                msg = f"[PARSED_NON_DICT] {custom_id} type={type(_)}"
                print(msg)
                log_line(msg)
                # 仍然写出来看看
                out_path = out_dir / f"{scene}.nondict.json"
                write_json(out_path, _)
                ok += 1
                continue
            except json.JSONDecodeError as e:
                failed += 1
                ctx = format_context(t, e.pos)
                msg = f"[DECODE_ERROR] {custom_id} line_no={line_no} err={e} | {ctx}"
                print(msg)
                log_line(msg)

            # 尝试截取最外层 { ... } 后再给一次更精确位置
            t2 = trim_to_outermost_object(t)
            if t2 != t:
                try:
                    json.loads(t2)
                except json.JSONDecodeError as e2:
                    ctx2 = format_context(t2, e2.pos)
                    msg2 = f"[DECODE_ERROR_TRIMMED] {custom_id} err={e2} | {ctx2}"
                    print(msg2)
                    log_line(msg2)

            # 尝试抢救 tuples
            salv = salvage_tuples(output_text)
            if salv is not None:
                salvaged += 1
                salv_path = out_dir / f"{scene}.salvaged.json"
                write_json(salv_path, salv)
                msg3 = f"[SALVAGED] {custom_id} tuples={len(salv.get('tuples', []))} -> {salv_path}"
                print(msg3)
                log_line(msg3)

    summary = f"Done. total={total}, ok={ok}, salvaged={salvaged}, failed={failed}. log={LOG_FILE}"
    print(summary)
    log_line(summary)


if __name__ == "__main__":
    main()