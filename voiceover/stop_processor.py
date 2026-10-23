import os

# 假设主脚本名为 voiceover_processor.py
# 停止标记文件必须与主脚本在同一目录下
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_FLAG_FILENAME = "stop_flag.txt"
STOP_FLAG_PATH = os.path.join(SCRIPT_DIR, STOP_FLAG_FILENAME)

def create_stop_flag():
    """
    创建停止标记文件，触发主脚本优雅退出。
    """
    if os.path.exists(STOP_FLAG_PATH):
        print(f"停止标记文件 '{STOP_FLAG_FILENAME}' 已存在，无需重复创建。")
        print("主脚本应该已经在优雅停止过程中。")
        return

    try:
        # 创建一个空的标记文件
        with open(STOP_FLAG_PATH, 'w') as f:
            f.write("Stop signal received.")
        
        print("-" * 40)
        print(f"成功创建停止标记文件: {STOP_FLAG_PATH}")
        print("主脚本将在完成当前任务后开始优雅停止。")
        print("请等待主脚本打印最终总结信息后关闭其窗口。")
        print("-" * 40)
        
    except Exception as e:
        print(f"创建停止标记文件失败: {e}")

if __name__ == "__main__":
    create_stop_flag()