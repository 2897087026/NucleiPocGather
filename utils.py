import hashlib
import subprocess
import time
from functools import wraps


def streaming_md5(file_path, chunk_size=65536):
    """流式计算文件 MD5 哈希值，避免大文件全量读内存."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def retry(max_retries=3, delay=2, backoff=2, exceptions=(Exception,)):
    """简单的指数退避重试装饰器."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"[!] 重试 {func.__name__} ({attempt + 1}/{max_retries}): {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"[x] {func.__name__} 重试 {max_retries} 次后仍失败: {e}")
            raise last_exception
        return wrapper
    return decorator


def git_run(args, timeout=300):
    """使用列表形式安全执行 git 命令."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            print(f"[x] git 命令失败: git {' '.join(args)}")
            print(f"    stderr: {result.stderr.strip()}")
            raise subprocess.CalledProcessError(
                result.returncode, ["git"] + args, result.stdout, result.stderr
            )
        return result.stdout
    except subprocess.TimeoutExpired:
        print(f"[x] git 命令超时 ({timeout}s): git {' '.join(args)}")
        raise


def shell_run(cmd, timeout=300, check=True):
    """安全执行 shell 命令（仅用于已知安全的固定命令）. """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            print(f"[x] 命令失败 (code={result.returncode}): {cmd[:120]}")
            if result.stderr.strip():
                print(f"    stderr: {result.stderr.strip()}")
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return result
    except subprocess.TimeoutExpired:
        print(f"[x] 命令超时 ({timeout}s): {cmd[:120]}")
        raise
