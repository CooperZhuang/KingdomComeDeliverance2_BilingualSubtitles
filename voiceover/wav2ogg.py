import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import pathlib
import threading
import time

# --- 配置区 ---
# 自动获取当前脚本的目录
BASE_DIR = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))

# 1. 指定输入和输出目录（相对于脚本的当前目录）
INPUT_ROOT_DIR = BASE_DIR / "中文配音输出"
OUTPUT_ROOT_DIR = BASE_DIR / "中文配音ogg"

# 2. FFmpeg 路径：已更新为您指定的值
# 4. ffmpeg 位置：优先环境变量 FFMPEG，其次 PATH，最后回落原来的硬编码路径
FFMPEG_EXECUTABLE = (
    os.environ.get("FFMPEG")
    or shutil.which("ffmpeg")
    or r"C:\Program Files (x86)\ffmpeg-8.0-full_build\bin\ffmpeg.exe"
)

# 3. 设置并行进程数：根据您的 9700X 核心数设置。
MAX_WORKERS = 7 
# --- 结束配置区 ---

# 线程安全的计数器和锁
PROGRESS_LOCK = threading.Lock()
TOTAL_FILES = 0
COMPLETED_COUNT = 0
STATUS_MESSAGE = ""

def update_progress_display(total, current, status):
    """动态更新单行进度显示"""
    # 使用 \r 回到行首，并使用 :<100 确保行尾被空格填充，清除历史信息
    display_line = f"进度: ({current}/{total}) | {status:<100}"
    sys.stdout.write(f"\r{display_line}")
    sys.stdout.flush()

# 统一的转换函数
def convert_single_file(input_file_path_str, output_root_dir_str, input_root_dir_str, ffmpeg_path):
    """单个文件的转换逻辑，用于多线程调用。"""
    global COMPLETED_COUNT, STATUS_MESSAGE
    
    input_file_path = pathlib.Path(input_file_path_str)
    
    # 1. 计算文件在输入根目录中的相对路径 (用于保持目录结构)
    relative_path = input_file_path.relative_to(input_root_dir_str)
    
    # 2. 构造输出文件名
    output_relative_path = relative_path.with_suffix('.ogg')
    
    # 3. 构造输出文件的完整路径
    output_file_path = pathlib.Path(output_root_dir_str) / output_relative_path
    
    # 确保输出文件的父目录存在
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 构造当前正在处理的状态信息
    current_status = f"正在处理: {relative_path}"
    with PROGRESS_LOCK:
        STATUS_MESSAGE = current_status
        update_progress_display(TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE)
    
    # 【断点续传/跳过】检查输出文件是否已经存在
    if output_file_path.exists():
        # 更新状态为跳过
        with PROGRESS_LOCK:
            COMPLETED_COUNT += 1
            STATUS_MESSAGE = f"已跳过: {output_relative_path}"
            update_progress_display(TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE)
        return "skipped" # 标记为已跳过
    
    # 构建 ffmpeg 命令
    command = [
        ffmpeg_path, 
        '-i', str(input_file_path),
        '-q:a', '4', 
        '-y', 
        str(output_file_path)
    ]
    
    try:
        # 运行命令
        subprocess.run(command, check=True, 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE, 
                       text=True, 
                       encoding='utf-8')
        
        # 【日志更新 - 完成处理】
        with PROGRESS_LOCK:
            COMPLETED_COUNT += 1
            STATUS_MESSAGE = f"成功完成: {output_relative_path}"
            update_progress_display(TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE)
        return "success" # 标记为成功
        
    except subprocess.CalledProcessError as e:
        # 【日志更新 - 错误处理】
        with PROGRESS_LOCK:
            COMPLETED_COUNT += 1
            STATUS_MESSAGE = f"转换失败: {input_file_path.name}"
            update_progress_display(TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE)
        return "error" # 标记为错误
    except FileNotFoundError:
        return "fatal_error" # 致命错误

def batch_convert_wav_to_ogg(input_root_dir, output_root_dir, ffmpeg_path, max_workers):
    """主函数：收集所有待处理文件，并使用多线程进行并行转换。"""
    global TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE
    input_root_dir_str = str(input_root_dir)
    output_root_dir_str = str(output_root_dir)

    print(f"开始在目录 '{input_root_dir_str}' 中搜索文件...")
    
    all_wav_files = []
    
    # 遍历输入目录及其所有子目录，收集文件路径
    for foldername, subfolders, filenames in os.walk(input_root_dir_str):
        for filename in filenames:
            if filename.lower().endswith('.wav'):
                all_wav_files.append(os.path.join(foldername, filename))

    TOTAL_FILES = len(all_wav_files)

    if not all_wav_files:
        print("未找到任何 .wav 文件，任务结束。")
        return

    print(f"已找到 {TOTAL_FILES} 个 .wav 文件，准备使用 {max_workers} 个工作线程并行转换。")
    print(f"输出结果将保存到目录: {output_root_dir}")
    print("-" * 50)
    
    # 初始化进度显示
    STATUS_MESSAGE = "任务已启动..."
    update_progress_display(TOTAL_FILES, COMPLETED_COUNT, STATUS_MESSAGE)


    # 使用 ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务到线程池
        future_to_file = {
            executor.submit(
                convert_single_file, 
                wav_file, 
                output_root_dir_str, 
                input_root_dir_str, 
                ffmpeg_path
            ): wav_file 
            for wav_file in all_wav_files
        }
        
        # 实时统计
        result_counts = {"success": 0, "skipped": 0, "error": 0, "fatal_error": 0}
        
        # 使用 as_completed 等待所有任务完成
        for future in as_completed(future_to_file):
            result = future.result()
            if result in result_counts:
                result_counts[result] += 1
            
            # 这里的进度显示依赖于 convert_single_file 内部的更新
            
        # 任务循环结束后，确保进度条是 100%
        with PROGRESS_LOCK:
            STATUS_MESSAGE = "所有任务已完成。"
            update_progress_display(TOTAL_FILES, TOTAL_FILES, STATUS_MESSAGE)


    # 任务完成后，打印最终结果
    sys.stdout.write("\r" + " " * 120 + "\r") # 再次清除单行进度条
    print("\n" + "=" * 50)
    print("转换任务完成统计：")
    print(f"  成功转换的文件数: {result_counts['success']}")
    print(f"  已跳过（OGG已存在）的文件数: {result_counts['skipped']}")
    print(f"  转换失败的文件数: {result_counts['error']}")
    print(f"  致命错误的文件数: {result_counts['fatal_error']}")
    print("=" * 50)


if __name__ == '__main__':
    # 1. 检查 FFmpeg 配置
    if not pathlib.Path(FFMPEG_EXECUTABLE).is_file():
        print(f"【致命错误】找不到指定的 FFmpeg 可执行文件：\n{FFMPEG_EXECUTABLE}")
        sys.exit(1)
    
    # 2. 检查输入目录
    if not INPUT_ROOT_DIR.is_dir():
        print(f"指定的输入目录不存在: {INPUT_ROOT_DIR}")
        sys.exit(1)
    
    # 3. 主程序运行和优雅中断处理
    try:
        batch_convert_wav_to_ogg(INPUT_ROOT_DIR, OUTPUT_ROOT_DIR, FFMPEG_EXECUTABLE, MAX_WORKERS)
        
    except KeyboardInterrupt:
        # 捕获 Ctrl+C (SIGINT 信号)
        sys.stdout.write("\r" + " " * 120 + "\r") # 清除进度条
        print("\n\n" + "-" * 50)
        print("🚨 **程序被用户中断 (Ctrl+C)。**")
        print("当前正在运行的 FFmpeg 任务将**继续完成当前文件**，但**不会再启动新任务**。")
        print("请等待所有已启动的任务结束。")
        print("-" * 50)