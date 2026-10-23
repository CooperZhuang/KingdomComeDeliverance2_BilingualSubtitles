import os
import xml.etree.ElementTree as ET
import re
import shutil
import concurrent.futures
import threading
import time
import logging  # 引入日志模块
from gradio_client import Client, file

# --- 全局配置 (可根据需要修改) ---

# 替换为你的 Gradio TTS 服务 URLs 列表 (推荐运行多个实例)
TTS_CLIENT_URLS = [
    "http://127.0.0.1:7860/",
    "http://localhost:8080/",
    "http://localhost:8081/",
    # TODO: 请在这里添加更多已启动的客户端 URL，以充分利用并发
]

API_NAME = "/gen_single"
XML_FILE = "text_ui_dialog.xml"
# 优化性能：增加最大并发线程数，以应对超快的 TTS 服务
MAX_WORKERS = 12

try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.path.abspath(os.path.dirname(os.sys.argv[0]))

FULL_XML_PATH = os.path.join(SCRIPT_DIR, XML_FILE)
ENGLISH_VOICEOVER_DIR = os.path.join(SCRIPT_DIR, "英文原始配音")
CHINESE_VOICEOVER_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "中文配音输出")
STOP_FLAG_PATH = os.path.join(SCRIPT_DIR, "stop_flag.txt")
LOG_FILE_PATH = os.path.join(SCRIPT_DIR, "tts_generation.log")  # 日志文件路径

# --- TTS 调用参数模板 (保持不变) ---
TTS_PARAMS_TEMPLATE = {
    "emo_control_method": "与音色参考音频相同",
    "prompt": None,
    "text": None,
    "emo_ref_path": None,
    "emo_weight": 0.8,
    "vec1": 0,
    "vec2": 0,
    "vec3": 0,
    "vec4": 0,
    "vec5": 0,
    "vec6": 0,
    "vec7": 0,
    "vec8": 0,
    "emo_text": "",
    "emo_random": False,
    "max_text_tokens_per_segment": 120,
    "param_16": True,
    "param_17": 0.8,
    "param_18": 30,
    "param_19": 0.8,
    "param_20": 0,
    "param_21": 3,
    "param_22": 10,
    "param_23": 1500,
    "api_name": API_NAME,
}

# ----------------------------------------
# 初始化日志系统 (根据用户要求修改 StreamHandler 级别)
# ----------------------------------------


def setup_logging(log_file):
    """配置日志记录器，输出到文件（INFO+）和控制台（WARNING+）。"""
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers = []

    # 根记录器级别设置为最低的 INFO
    root_logger.setLevel(logging.INFO)

    # 文件 Handler (详细日志 - INFO 级别)
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 控制台 Handler (只输出 WARNING/ERROR/CRITICAL，屏蔽 INFO 级别的详细任务和进度)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(
        logging.WARNING
    )  # 核心修改：提高级别，只在终端输出警告和错误
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    return root_logger


# ----------------------------------------


class VoiceoverProcessor:
    """
    用于协调 XML 解析、文件查找和 TTS 服务调用的类。
    支持多客户端并发调度和异步进度监控。
    """

    def __init__(
        self,
        tts_client_urls,
        xml_path,
        en_dir,
        cn_dir,
        tts_template,
        max_workers,
        stop_flag_path,
        logger,
    ):
        self.tts_client_urls = tts_client_urls
        self.full_xml_path = xml_path
        self.english_dir = en_dir
        self.chinese_output_dir = cn_dir
        self.tts_template = tts_template
        self.max_workers = max_workers
        self.stop_flag_path = stop_flag_path

        self.logger = logger

        self.id_to_full_text = {}
        self.stop_requested = False

        self.tts_clients = []
        self.client_index = 0
        self.client_lock = threading.Lock()

        self.total_processed = 0
        self.total_skipped_precheck = 0
        self.total_skipped_runtime = 0
        self.total_submitted_effective = 0

        self.start_time = None
        self.effective_tasks_to_run = 0
        self.total_effective_bytes = 0
        self.processed_effective_bytes = 0

        self.is_running = threading.Event()
        self.total_tasks_for_monitor = 0

    def parse_xml_to_dict(self):
        """解析 XML 文件，将 ID 映射到完整的双语文本。"""
        self.logger.info("-" * 50)
        self.logger.info(f"开始解析 XML 文件: {self.full_xml_path}")
        try:
            tree = ET.parse(self.full_xml_path)
            root = tree.getroot()

            for row in root.findall(".//Row"):
                cells = row.findall("./Cell")
                if len(cells) >= 3:
                    file_id = cells[0].text
                    full_text = cells[2].text

                    if file_id and full_text:
                        self.id_to_full_text[str(file_id).strip()] = str(
                            full_text
                        ).strip()

            self.logger.info(
                f"XML 解析完成，共找到 {len(self.id_to_full_text)} 条配音 ID 记录。"
            )
            return bool(self.id_to_full_text)
        except (FileNotFoundError, ET.ParseError) as e:
            self.logger.error(f"解析 XML 时发生错误: {e}")
            return False
        except Exception as e:
            self.logger.error(f"解析 XML 时发生未知错误: {e}")
            return False

    def find_full_text(self, filename_id):
        """根据文件名 ID 在映射中查找对应的完整的原始文本。"""
        if filename_id in self.id_to_full_text:
            return self.id_to_full_text[filename_id]

        if "_" in filename_id:
            first_underscore_index = filename_id.find("_")
            stripped_id = filename_id[first_underscore_index + 1 :]
            if stripped_id in self.id_to_full_text:
                return self.id_to_full_text[stripped_id]
        return None

    def extract_chinese_text(self, full_text):
        """
        精确地从双语文本中提取中文部分，并进行清理。
        返回 (清理后的文本, 原始的中文文本)。
        """
        if full_text is None:
            return None, None

        chinese_text_with_paren = full_text.split("\\n")[0].strip()

        if not chinese_text_with_paren:
            return None, None

        if not re.search(r"[\u4e00-\u9fa5]", chinese_text_with_paren):
            return None, chinese_text_with_paren

        cleaned_text = re.sub(r"[\(（].*?[\)）]", "", chinese_text_with_paren).strip()

        if not cleaned_text:
            return chinese_text_with_paren, chinese_text_with_paren

        return cleaned_text, chinese_text_with_paren

    def initialize_clients(self):
        """初始化 Gradio 客户端列表。"""
        self.logger.info("-" * 50)
        self.logger.info(f"尝试连接 {len(self.tts_client_urls)} 个 TTS 服务...")

        successful_connections = 0
        for url in self.tts_client_urls:
            try:
                client = Client(url)
                self.tts_clients.append(client)
                successful_connections += 1
                self.logger.info(f"  - 成功连接到: {url}")
            except Exception as e:
                # 使用 logger.warning，这个信息会同时输出到终端和日志文件
                self.logger.warning(f"  - 警告: 无法连接到服务 {url}。错误信息: {e}")

        if successful_connections == 0:
            self.logger.critical(
                "错误: 未能连接到任何 Gradio TTS 服务。程序退出。"
            )  # 使用 critical 确保在终端显示
            return False

        self.logger.info(f"共成功连接 {successful_connections} 个客户端。")
        return True

    def _get_next_client(self):
        """线程安全地获取下一个 Gradio Client 实例，采用循环调度 (Round-Robin)。"""
        with self.client_lock:
            client = self.tts_clients[self.client_index]
            client_url = self.tts_client_urls[self.client_index]
            self.client_index = (self.client_index + 1) % len(self.tts_clients)
        return client, client_url

    def _pre_check_task(self, full_audio_path, relative_path, filename):
        """
        在任务提交到线程池之前进行预检查。
        返回 (是否需要实际调用 TTS, cleaned_text, file_size_bytes)
        """
        filename_id = os.path.splitext(filename)[0]
        output_subdir = os.path.join(self.chinese_output_dir, relative_path)

        full_text_match = self.find_full_text(filename_id)
        chinese_text, _ = self.extract_chinese_text(full_text_match)

        file_size = 0
        try:
            file_size = os.path.getsize(full_audio_path)
        except OSError:
            self.logger.error(f"文件大小获取失败: {full_audio_path}")
            return False, None, 0

        if not chinese_text:
            self.logger.debug(f"跳过 (无中文文本): {filename}")
            return False, None, 0

        # 检查输出文件是否已存在
        base_name = os.path.splitext(filename)[0]
        output_exists = False
        if os.path.exists(output_subdir):
            if any(
                f.startswith(base_name) and f.lower().endswith((".ogg", ".wav", ".mp3"))
                for f in os.listdir(output_subdir)
            ):
                output_exists = True

        if output_exists:
            self.logger.debug(f"跳过 (已存在): {filename}")
            return False, chinese_text, 0

        return True, chinese_text, file_size

    def _process_single_file(self, full_audio_path, relative_path, filename, file_size):
        """
        单个文件的处理逻辑，将在线程池中执行。
        返回 (结果状态, file_size_if_successful)
        """
        if self.stop_requested:
            return "interrupted", 0

        tts_client, client_url = self._get_next_client()

        filename_id = os.path.splitext(filename)[0]
        output_subdir = os.path.join(self.chinese_output_dir, relative_path)
        os.makedirs(output_subdir, exist_ok=True)

        client_tag = (
            client_url.split("//")[-1]
            .split(":")[0]
            .replace("127.0.0.1", "Local")
            .replace("localhost", "Local")
        )
        log_prefix = f"[CLT:{client_tag} - {filename}] "

        full_text_match = self.find_full_text(filename_id)
        chinese_text, _ = self.extract_chinese_text(full_text_match)

        if not chinese_text:
            self.logger.warning(f"{log_prefix}运行时跳过：找不到或中文文本为空。")
            return "skipped_fail", 0

        # INFO 级别，只写入日志文件
        self.logger.info(f"{log_prefix}开始调用 TTS: [TTS输入: {chinese_text[:20]}...]")

        params = self.tts_template.copy()
        params["prompt"] = file(full_audio_path)
        params["text"] = chinese_text

        try:
            if self.stop_requested:
                return "interrupted", 0

            # 实际调用 Gradio 服务
            raw_result = tts_client.predict(**params)

            # 解析结果和文件移动
            result_filepath = None
            if isinstance(raw_result, str):
                result_filepath = raw_result
            elif isinstance(raw_result, dict) and "value" in raw_result:
                result_filepath = raw_result["value"]
            elif isinstance(raw_result, list) and raw_result:
                first_element = raw_result[0]
                if isinstance(first_element, str):
                    result_filepath = first_element
                elif isinstance(first_element, dict) and "value" in first_element:
                    result_filepath = first_element["value"]

            if (
                result_filepath
                and isinstance(result_filepath, str)
                and result_filepath.lower() != "none"
                and os.path.exists(result_filepath)
            ):
                output_ext = os.path.splitext(result_filepath)[1]
                output_filename = os.path.splitext(filename)[0] + output_ext
                final_output_path = os.path.join(output_subdir, output_filename)

                shutil.move(result_filepath, final_output_path)

                # INFO 级别，只写入日志文件
                self.logger.info(
                    f"{log_prefix}**成功保存**: -> 输出文件 '{os.path.join(relative_path, output_filename)}'"
                )
                return "processed", file_size
            else:
                self.logger.error(
                    f"{log_prefix}**错误**：TTS 调用成功，但无法提取有效文件路径。原始结果: {raw_result}"
                )
                return "skipped_runtime", 0

        except Exception as e:
            self.logger.error(
                f"{log_prefix}**严重错误**: 调用 TTS 服务失败，文件跳过。错误信息: {e}. TTS 输入文本: '{chinese_text[:20]}...'"
            )
            return "skipped_runtime", 0

    # --- 进度和 ETA 计算方法 (保持不变) ---
    def _format_time(self, seconds):
        if seconds is None or seconds <= 0:
            return "N/A"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{int(h)}h {int(m)}m {int(s)}s"
        elif m > 0:
            return f"{int(m)}m {int(s)}s"
        else:
            return f"{int(s)}s"

    def _format_bytes(self, bytes):
        if bytes is None or bytes == 0:
            return "0 B"
        sizes = ["B", "KB", "MB", "GB"]
        i = 0
        while bytes >= 1024 and i < len(sizes) - 1:
            bytes /= 1024.0
            i += 1
        return f"{bytes:.2f} {sizes[i]}"

    def _calculate_eta_tps(self, total_tasks):
        if self.start_time is None:
            return "N/A"
        elapsed_time = time.time() - self.start_time
        completed_effective_tasks = self.total_processed + self.total_skipped_runtime
        if completed_effective_tasks == 0 or elapsed_time < 5:
            return "N/A"
        tps = completed_effective_tasks / elapsed_time
        tasks_remaining = self.effective_tasks_to_run - completed_effective_tasks
        if tps <= 0 or tasks_remaining <= 0:
            return "0s"
        return self._format_time(tasks_remaining / tps)

    def _calculate_eta_bps(self):
        if self.start_time is None:
            return "N/A", "0 B/s"
        elapsed_time = time.time() - self.start_time
        if self.processed_effective_bytes == 0 or elapsed_time < 5:
            return "N/A", "0 B/s"
        bps = self.processed_effective_bytes / elapsed_time
        bytes_remaining = self.total_effective_bytes - self.processed_effective_bytes
        if bps <= 0 or bytes_remaining <= 0:
            return "0s", self._format_bytes(bps) + "/s"
        eta_seconds = bytes_remaining / bps
        return self._format_time(eta_seconds), self._format_bytes(bps) + "/s"

    # --- 监控线程 ---
    def _monitor_progress(self):
        """
        独立的监控线程，负责每隔 X 秒打印进度和 ETA，并检查停止标记文件。
        注意：使用 logger.info()，它现在只会写入日志文件。
        """
        MONITOR_INTERVAL = 3
        total_tasks = self.total_tasks_for_monitor

        while self.is_running.is_set():
            time.sleep(MONITOR_INTERVAL)

            # 检查停止标记文件
            if os.path.exists(self.stop_flag_path):
                self.stop_requested = True
                self.is_running.clear()
                self.logger.critical(
                    "\n\n*** 检测到停止标记文件！正在准备优雅停止。***\n"
                )
                return

            if self.start_time and self.total_submitted_effective > 0:

                with self.client_lock:
                    current_processed = self.total_processed
                    current_skipped_runtime = self.total_skipped_runtime
                    current_skipped_precheck = self.total_skipped_precheck
                    current_effective_tasks = self.effective_tasks_to_run

                eta_tps = self._calculate_eta_tps(total_tasks)
                eta_bps, throughput_bps = self._calculate_eta_bps()

                total_done_all_files = (
                    current_processed
                    + current_skipped_runtime
                    + current_skipped_precheck
                )

                # INFO 级别，只会出现在日志文件中
                self.logger.info(
                    f"\n--- [MONITOR] 总进度: {total_done_all_files}/{total_tasks} (TTS: {current_processed}/{current_effective_tasks}) | **ETA(任务): {eta_tps} | ETA(大小): {eta_bps} ({throughput_bps})** ---"
                )

    def run(self):
        """主处理逻辑，使用线程池执行并发任务。"""
        # 清理旧的停止标记
        if os.path.exists(self.stop_flag_path):
            try:
                os.remove(self.stop_flag_path)
                self.logger.info(f"已清理旧的停止标记文件: {self.stop_flag_path}")
            except OSError as e:
                self.logger.error(f"错误: 无法清理停止标记文件: {e}")

        self.logger.info(f"日志文件将写入: {LOG_FILE_PATH}")
        self.logger.info("-" * 50)

        if not self.parse_xml_to_dict():
            return
        if not self.initialize_clients():
            return

        # --- 阶段一：预检查和任务收集 (与上一个版本逻辑相同) ---
        all_tasks = []
        effective_tasks = []
        total_skipped_precheck_local = 0
        total_effective_bytes_local = 0
        for root, _, files in os.walk(self.english_dir):
            relative_path = os.path.relpath(root, self.english_dir)
            for filename in files:
                if filename.lower().endswith((".ogg", ".wav", ".mp3")):
                    full_audio_path = os.path.join(root, filename)
                    task = (full_audio_path, relative_path, filename)
                    all_tasks.append(task)
                    is_effective, _, file_size = self._pre_check_task(*task)
                    if not is_effective:
                        total_skipped_precheck_local += 1
                    else:
                        effective_tasks.append(task + (file_size,))
                        total_effective_bytes_local += file_size

        total_tasks = len(all_tasks)
        self.effective_tasks_to_run = len(effective_tasks)
        self.total_skipped_precheck = total_skipped_precheck_local
        self.total_effective_bytes = total_effective_bytes_local
        self.total_tasks_for_monitor = total_tasks

        self.logger.info(f"扫描完成：共发现 {total_tasks} 个音频文件。")
        self.logger.info(
            f"预检查跳过 (已存在/无中文)：{self.total_skipped_precheck} 个文件。"
        )
        self.logger.info(
            f"**实际需要调用 TTS 的有效任务总数：{self.effective_tasks_to_run}**"
        )
        self.logger.info(
            f"有效音频总大小 (用于 ETA 估计): {self._format_bytes(self.total_effective_bytes)}"
        )

        if self.effective_tasks_to_run == 0:
            self.logger.info("没有需要生成的文件，程序退出。")
            return

        # --- 阶段二：并发执行有效任务 ---
        self.start_time = time.time()
        self.is_running.set()

        self.logger.info("-" * 50)
        # 重要的启动信息，使用 INFO 级别，会出现在日志文件
        self.logger.info(f"开始使用 {self.max_workers} 个线程并发生成...")
        self.logger.info(">> 使用外部脚本或创建 'stop_flag.txt' 文件来**优雅停止**。")
        # 终端启动信息，使用 WARNING 级别，会出现在终端
        self.logger.warning(f"--- 任务开始: {self.effective_tasks_to_run} 个任务 ---")
        self.logger.warning(f"详细进度请查看日志文件: {LOG_FILE_PATH}")

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=self._monitor_progress, daemon=True, name="MonitorThread"
        )
        monitor_thread.start()

        futures = []
        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                # 提交任务
                futures = [
                    executor.submit(self._process_single_file, *task)
                    for task in effective_tasks
                    if not self.stop_requested
                ]

                with self.client_lock:
                    self.total_submitted_effective = len(futures)

                # 使用 as_completed 专注于结果收集
                for future in concurrent.futures.as_completed(futures):

                    if self.stop_requested:
                        break

                    try:
                        result, file_size_processed = future.result()

                        with self.client_lock:
                            if result == "processed":
                                self.total_processed += 1
                                self.processed_effective_bytes += file_size_processed
                            elif (
                                result == "skipped_runtime" or result == "skipped_fail"
                            ):
                                self.total_skipped_runtime += 1
                            elif result == "interrupted":
                                self.total_skipped_runtime += 1
                                self.stop_requested = True
                                break
                    except Exception as e:
                        self.logger.error(f"线程执行时发生未知错误: {e}")
                        with self.client_lock:
                            self.total_skipped_runtime += 1

                # 循环结束后，如果是因为 stop_requested 退出，取消所有正在运行/等待的任务
                if self.stop_requested:
                    self.logger.info("\n正在取消所有未完成的任务...")
                    running_futures = [f for f in futures if not f.done()]
                    for f in running_futures:
                        f.cancel()

        except Exception as e:
            self.logger.error(f"主线程发生未知错误: {e}")
            self.stop_requested = True

        # --- 阶段三：清理和总结 ---
        self.is_running.clear()
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=5)

        self.logger.info("-" * 50)

        if self.stop_requested:
            self.logger.warning("任务被**中断**。")  # 警告级别，在终端显示

        # 最终总结
        total_runtime = time.time() - self.start_time if self.start_time else 0
        total_skipped = self.total_skipped_precheck + self.total_skipped_runtime

        # 总结信息，使用 INFO 级别，会出现在日志文件
        self.logger.info("配音生成任务完成。")
        self.logger.info(f"总耗时 (有效任务): {total_runtime:.2f} 秒")
        self.logger.info(f"成功生成: {self.total_processed} 个文件。")
        self.logger.info(
            f"总跳过文件: {total_skipped} 个 (预检查跳过: {self.total_skipped_precheck}, 运行时失败: {self.total_skipped_runtime})。"
        )
        self.logger.info(f"中文配音已输出到 '{self.chinese_output_dir}' 文件夹。")

        # 终端总结，使用 WARNING 级别，确保在终端显示
        self.logger.warning("-" * 50)
        self.logger.warning("最终总结：")
        self.logger.warning(f"成功生成文件数: {self.total_processed}")
        self.logger.warning(f"总耗时: {total_runtime:.2f} 秒")


# --- 主程序入口 ---
if __name__ == "__main__":

    # 1. 设置日志系统
    logger = setup_logging(LOG_FILE_PATH)
    logger.info(f"脚本正在运行的目录: {SCRIPT_DIR}")

    processor = VoiceoverProcessor(
        TTS_CLIENT_URLS,
        FULL_XML_PATH,
        ENGLISH_VOICEOVER_DIR,
        CHINESE_VOICEOVER_OUTPUT_DIR,
        TTS_PARAMS_TEMPLATE,
        MAX_WORKERS,
        STOP_FLAG_PATH,
        logger,
    )

    try:
        processor.run()
    except Exception as e:
        logger.critical(f"\n程序主异常：{e}")  # 使用 critical 确保在终端显示
