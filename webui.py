# webui.py
import gradio as gr
import cv2
import os
import configparser
import tempfile
import threading
import multiprocessing
import numpy as np
import time
from pathlib import Path
from datetime import datetime
import sys
import importlib
import backend.config as config_module
from backend.config import InpaintMode
import shutil
import zipfile
import logging

# 创建模块化日志记录器
logger = logging.getLogger(__name__)

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def log_info(message):
    """记录INFO级别日志"""
    logging.info(message)


def log_error(message):
    """记录ERROR级别日志"""
    logging.error(message)


def rename_file(file_paths, new_name):
    """重命名单个文件"""
    if not file_paths:
        return "请先选择要重命名的文件", *full_refresh()
  
    if len(file_paths) > 1:
        return "只能选择一个文件进行重命名", *full_refresh()
  
    old_path = file_paths[0]
    old_filename = os.path.basename(old_path)
    directory = os.path.dirname(old_path)
  
    if not new_name.strip():
        return "新文件名不能为空", *full_refresh()
  
    # 确保新文件名没有路径分隔符
    if any(char in new_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
        return "文件名包含非法字符", *full_refresh()
  
    # 验证扩展名
    old_ext = os.path.splitext(old_filename)[1]
    new_name = new_name if new_name.endswith(old_ext) else f"{new_name}{old_ext}"
  
    new_path = os.path.join(directory, new_name)
  
    if os.path.exists(new_path):
        return "文件名已存在，请选择其他名称", *full_refresh()
  
    try:
        os.rename(old_path, new_path)
        logger.info(f"重命名文件成功: {old_filename} -> {new_name}")
        success_msg = f"重命名成功: {old_filename} -> {new_name}"
        return success_msg, *full_refresh()
    except Exception as e:
        logger.error(f"重命名文件失败: {old_filename} -> {new_name}, 错误: {str(e)}")
        return f"重命名失败: {str(e)}", *full_refresh()


# 创建文件夹
INPUT_DIR = "input_videos"
OUTPUT_DIR = "output_videos"
DOWNLOAD_DIR = "downloads"  # 下载目录
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)  # 确保下载目录存在

# 初始化文件状态跟踪变量
last_input_files = []
last_output_files = []


def list_files(directory):
    """列出目录中的所有视频文件"""
    logger.info(f"开始列出目录 {directory} 中的视频文件")
    files = []
    for f in os.listdir(directory):
        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
            path = os.path.join(directory, f)
            size = f"{os.path.getsize(path) / 1024 / 1024:.2f} MB"
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')
            files.append([False, f, path, size, mtime])
    logger.info(f"列出目录 {directory} 中的文件完成，找到 {len(files)} 个视频文件")
    return files


def full_refresh():
    """完全刷新文件列表并清空选中状态"""
    global last_input_files, last_output_files

    input_list = list_files(INPUT_DIR)
    output_list = list_files(OUTPUT_DIR)

    # 更新最后已知状态
    last_input_files = input_list
    last_output_files = output_list

    log_info(f"执行完整刷新，input文件数: {len(input_list)}, output文件数: {len(output_list)}")
    return input_list, output_list, [], []


def upload_file(file):
    """上传文件到input目录"""
    if file:
        filename = os.path.basename(file.name)
        dest = os.path.join(INPUT_DIR, filename)
        logger.info(f"开始上传文件: {filename} 到 {INPUT_DIR} 目录")
        try:
            shutil.copy(file.name, dest)
            logger.info(f"文件上传成功: {filename}")
        except Exception as e:
            logger.error(f"文件上传失败: {filename}, 错误: {str(e)}")
    else:
        logger.info("未选择文件进行上传")
    return full_refresh()


def delete_files(file_paths):
    """批量删除文件"""
    if not file_paths:
        logger.info("删除请求中未选择文件")
        return full_refresh()

    deleted_count = 0
    for path in file_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"成功删除文件: {path}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"删除文件失败: {path}, 错误: {str(e)}")
        else:
            logger.warning(f"尝试删除不存在的文件: {path}")

    logger.info(f"批量删除完成，成功删除 {deleted_count} 个文件")
    return full_refresh()


def download_files(file_paths):
    """批量下载文件 - 创建ZIP压缩包"""
    if not file_paths:
        logger.info("下载请求中未选择文件")
        return None, "📥 请先选择要下载的文件！"

    # 确定来源文件夹名称 (input/output)
    source_dir = "input" if file_paths and file_paths[0].startswith(INPUT_DIR) else "output"
    logger.info(f"开始准备下载文件，来源目录: {source_dir}")

    # 获取文件名（不带扩展名）
    if len(file_paths) == 1:
        base_name = os.path.splitext(os.path.basename(file_paths[0]))[0]
        zip_name = f"{source_dir}_{base_name}.zip"
    else:
        zip_name = f"{source_dir}_多个文件.zip"

    zip_path = os.path.join(DOWNLOAD_DIR, zip_name)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path in file_paths:
                if os.path.exists(path):
                    zipf.write(path, os.path.basename(path))
                    logger.info(f"添加文件到压缩包: {path}")
                else:
                    logger.error(f"尝试添加不存在的文件到压缩包: {path}")

        logger.info(f"下载文件准备完成: {zip_path}")
        return zip_path, "📥 下载文件已准备好！"
    except Exception as e:
        logger.error(f"创建下载文件失败: {str(e)}")
        return None, "📥 下载文件准备失败！"


def list_downloads():
    """列出下载目录中的所有文件"""
    downloads = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR)
                 if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
    log_info(f"列出下载目录文件，当前有 {len(downloads)} 个下载文件")
    return downloads


def clear_downloads():
    """清除下载目录中的所有文件"""
    logger.info("开始清除下载目录中的所有文件")
    cleared_count = 0
    for f in os.listdir(DOWNLOAD_DIR):
        file_path = os.path.join(DOWNLOAD_DIR, f)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
                logger.info(f"清除下载文件: {file_path}")
                cleared_count += 1
        except Exception as e:
            logger.error(f"删除下载文件失败: {file_path} - {e}")

    logger.info(f"下载目录清理完成，共清除 {cleared_count} 个文件")
    return "📥 下载文件已清除！", list_downloads()


# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend.main
from backend.tools.common_tools import is_image_file


class SubtitleRemoverWebUI:
    def __init__(self):
        self.logger = logging.getLogger(__name__ + '.SubtitleRemoverWebUI')
        self.font = 'Arial'
        # 设置视频预览区域大小
        self.video_preview_width = 960
        self.video_preview_height = self.video_preview_width * 9 // 16
        # 视频路径
        self.video_path = None
        # 视频cap
        self.video_cap = None
        # 视频的帧率
        self.fps = None
        # 视频的帧数
        self.frame_count = None
        # 视频的宽
        self.frame_width = None
        # 视频的高
        self.frame_height = None
        # 设置字幕区域高宽
        self.xmin = 0
        self.xmax = 0
        self.ymin = 0
        self.ymax = 0
        # 字幕提取器
        self.sr = None
        # 处理进度
        self.progress = 0
        # 状态消息
        self.status = "就绪"
        # 预览图像
        self.preview_frame = None
        # 输出文件路径
        self.output_path = None
        # 字幕配置
        self.subtitle_config_file = os.path.join(os.path.dirname(__file__), 'subtitle.ini')
        # 加载默认配置
        self.y_p, self.h_p, self.x_p, self.w_p = self.parse_subtitle_config()
        # 缓存第一帧
        self.first_frame = None
        # 算法参数配置
        self.algorithm_params = self.get_default_params()
        # 新增：中止处理相关属性
        self.abort_event = threading.Event()  # 用于通知处理线程中止
        self.processing_thread = None  # 处理线程引用
        self.is_processing = False  # 是否正在处理
        # 上传进度相关变量
        self.last_upload_progress = 0
        self.last_upload_update = 0

    def get_default_params(self):
        """获取默认算法参数"""
        return {
            "mode": config_module.MODE.name,
            "sttn_skip_detection": config_module.STTN_SKIP_DETECTION,
            "sttn_neighbor_stride": config_module.STTN_NEIGHBOR_STRIDE,
            "sttn_reference_length": config_module.STTN_REFERENCE_LENGTH,
            "sttn_max_load_num": config_module.STTN_MAX_LOAD_NUM,
            "lama_super_fast": config_module.LAMA_SUPER_FAST,
            "propainter_max_load_num": config_module.PROPAINTER_MAX_LOAD_NUM
        }

    def parse_subtitle_config(self):
        y_p, h_p, x_p, w_p = .78, .21, .05, .9
        # 如果配置文件不存在，则写入配置文件
        if not os.path.exists(self.subtitle_config_file):
            self.set_subtitle_config(y_p, h_p, x_p, w_p)
            return y_p, h_p, x_p, w_p
        else:
            try:
                config = configparser.ConfigParser()
                config.read(self.subtitle_config_file, encoding='utf-8')
                conf_y_p, conf_h_p, conf_x_p, conf_w_p = float(config['AREA']['Y']), float(config['AREA']['H']), float(
                    config['AREA']['X']), float(config['AREA']['W'])
                return conf_y_p, conf_h_p, conf_x_p, conf_w_p
            except Exception:
                self.set_subtitle_config(y_p, h_p, x_p, w_p)
                return y_p, h_p, x_p, w_p

    def set_subtitle_config(self, y, h, x, w):
        # 写入配置文件
        with open(self.subtitle_config_file, mode='w', encoding='utf-8') as f:
            f.write('[AREA]\n')
            f.write(f'Y = {y}\n')
            f.write(f'H = {h}\n')
            f.write(f'X = {x}\n')
            f.write(f'W = {w}\n')

    def load_video(self, video_path):
        """加载视频并返回第一帧预览"""
        self.logger.info(f"开始加载视频: {video_path}")
        try:
            # 重置属性
            self.video_path = None
            self.video_cap = None
            self.fps = None
            self.frame_count = None
            self.frame_width = None
            self.frame_height = None
            self.first_frame = None

            if not video_path:
                self.logger.warning("视频路径为空")
                return None, "请输入视频文件路径"

            self.video_path = video_path
            self.video_cap = cv2.VideoCapture(video_path)

            if not self.video_cap.isOpened():
                error_msg = f"错误: 无法打开视频文件: {video_path}"
                self.logger.error(error_msg)
                return None, error_msg

            # 获取视频信息
            self.frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT) + 0.5)
            self.frame_height = int(self.video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.frame_width = int(self.video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.fps = self.video_cap.get(cv2.CAP_PROP_FPS)
            
            self.logger.info(f"视频信息 - 尺寸: {self.frame_width}x{self.frame_height}, 帧率: {self.fps:.2f}, 总帧数: {self.frame_count}")

            # 读取第一帧
            ret, frame = self.video_cap.read()
            if not ret:
                error_msg = "错误: 无法读取视频帧"
                self.logger.error(error_msg)
                return None, error_msg

            # 保存第一帧
            self.first_frame = frame.copy()

            # 绘制默认字幕区域
            self.ymin = int(self.frame_height * self.y_p)
            self.ymax = int(self.ymin + self.frame_height * self.h_p)
            self.xmin = int(self.frame_width * self.x_p)
            self.xmax = int(self.xmin + self.frame_width * self.w_p)

            # 绘制矩形框
            frame = self.draw_subtitle_area(frame)

            # 添加坐标轴
            frame = self.add_coordinates(frame)

            # 调整大小
            resized_frame = self.img_resize(frame)
            success_msg = f"已加载: {os.path.basename(video_path)}\n尺寸: {self.frame_width}x{self.frame_height} | 帧率: {self.fps:.1f}"
            self.logger.info(f"视频加载成功: {video_path}")
            return resized_frame, success_msg
        except Exception as e:
            error_msg = f"错误: {str(e)}"
            self.logger.error(f"加载视频时发生异常: {error_msg}")
            return None, error_msg
        finally:
            # 释放视频捕获资源
            if self.video_cap and self.video_cap.isOpened():
                self.video_cap.release()

    def update_subtitle_area(self, y, h, x, w):
        """更新字幕区域并返回带框的预览图"""
        try:
            if self.first_frame is None:
                return None, "未加载视频"

            # 设置字幕区域
            self.ymin = int(y)
            self.ymax = int(y + h)
            self.xmin = int(x)
            self.xmax = int(x + w)

            # 使用缓存的第一帧
            frame = self.first_frame.copy()

            # 绘制矩形框
            frame = self.draw_subtitle_area(frame)

            # 添加坐标轴
            frame = self.add_coordinates(frame)

            # 调整大小
            resized_frame = self.img_resize(frame)
            status_msg = f"字幕区域: Y:{y}-{y + h} X:{x}-{x + w}\n宽度: {w} 高度: {h}"
            return resized_frame, status_msg
        except Exception as e:
            return None, f"错误: {str(e)}"

    def draw_subtitle_area(self, frame):
        """在帧上绘制字幕区域矩形"""
        draw = cv2.rectangle(
            img=frame,
            pt1=(self.xmin, self.ymin),
            pt2=(self.xmax, self.ymax),
            color=(0, 255, 0),
            thickness=3
        )
        return draw

    def add_coordinates(self, frame):
        """在图像上添加坐标轴"""
        # 添加坐标轴标签
        cv2.putText(frame, f"X: {self.xmin}-{self.xmax}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Y: {self.ymin}-{self.ymax}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # 添加坐标轴线
        cv2.line(frame, (0, self.ymin), (frame.shape[1], self.ymin), (0, 255, 0), 1)
        cv2.line(frame, (0, self.ymax), (frame.shape[1], self.ymax), (0, 255, 0), 1)
        cv2.line(frame, (self.xmin, 0), (self.xmin, frame.shape[0]), (0, 255, 0), 1)
        cv2.line(frame, (self.xmax, 0), (self.xmax, frame.shape[0]), (0, 255, 0), 1)

        return frame

    def img_resize(self, image):
        """调整图像大小以适应预览区域"""
        height, width = image.shape[0], image.shape[1]
        scale = min(self.video_preview_width / width, self.video_preview_height / height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        resized = cv2.resize(image, (new_width, new_height))
        return resized

    def process_video(self, params, progress=gr.Progress()):
        """处理视频并更新进度"""
        self.logger.info("开始处理视频")
        try:
            # 重置中止事件
            self.abort_event.clear()

            self.status = "处理中..."
            self.progress = 0
            self.output_path = None
            self.is_processing = True  # 标记为正在处理

            # 添加额外检查确保视频路径是有效的字符串
            if not isinstance(self.video_path, str) or not self.video_path or not os.path.exists(self.video_path):
                # 显示更详细的错误信息
                error_msg = "错误: 视频路径无效"
                if self.video_path is None:
                    error_msg += " - 路径为None. 请先加载视频."
                    self.logger.error("视频路径为None，未加载视频")
                elif not os.path.exists(self.video_path):
                    error_msg += f" - 文件不存在: {self.video_path}"
                    self.logger.error(f"视频文件不存在: {self.video_path}")
                else:
                    error_msg += f" - 无效路径类型: {type(self.video_path)}"
                    self.logger.error(f"无效的视频路径类型: {type(self.video_path)}")

                self.status = error_msg
                self.logger.error(error_msg)
                self.is_processing = False
                return None, self.status

            # 创建字幕提取器
            subtitle_area = (self.ymin, self.ymax, self.xmin, self.xmax)
            self.logger.info(f"设置字幕区域: ymin={self.ymin}, ymax={self.ymax}, xmin={self.xmin}, xmax={self.xmax}")

            # 创建配置字典 - 确保值在合理范围内
            safe_params = {
                "mode": str(params["mode"]),  # 确保是字符串
                "sttn_skip_detection": bool(params["sttn_skip_detection"]),
                "sttn_neighbor_stride": max(1, min(int(params["sttn_neighbor_stride"]), 800)),
                "sttn_reference_length": max(1, min(int(params["sttn_reference_length"]), 400)),
                "sttn_max_load_num": max(50, min(int(params["sttn_max_load_num"]), 2000)),
                "lama_super_fast": bool(params["lama_super_fast"]),
                "propainter_max_load_num": max(20, min(int(params["propainter_max_load_num"]), 4000))
            }

            self.logger.info(f"处理参数: {safe_params}")

            # 创建字幕去除器
            self.logger.info("开始创建字幕去除器")
            self.sr = backend.main.SubtitleRemover(
                self.video_path,
                subtitle_area,
                True,
                safe_params,
                self.abort_event,
                output_dir=OUTPUT_DIR  # 添加输出目录参数
            )

            # 新增：传递中止事件给SubtitleRemover
            self.sr.abort_event = self.abort_event

            # 启动处理线程
            def run_remover():
                self.logger.info("启动视频处理线程")
                try:
                    self.sr.run()
                    if self.abort_event.is_set():
                        self.status = "处理已中止"
                        self.logger.info("视频处理已中止")
                    else:
                        self.output_path = self.sr.video_out_name
                        self.status = "处理完成"
                        self.logger.info(f"视频处理完成，输出路径: {self.output_path}")
                except Exception as e:
                    self.status = f"处理错误: {str(e)}"
                    self.logger.error(f"视频处理过程中发生异常: {str(e)}", exc_info=True)
                finally:
                    self.is_processing = False
                    self.sr = None

            # 创建线程并启动（移动到函数外部）
            self.processing_thread = threading.Thread(target=run_remover)
            self.processing_thread.start()

            # 更新进度 (降低更新频率)
            last_update = time.time()
            while self.processing_thread.is_alive():
                # 每0.5秒更新一次进度，避免过于频繁
                if time.time() - last_update > 0.5:
                    if self.sr:
                        self.progress = self.sr.progress_total
                        if self.sr.preview_frame is not None:
                            # 调整预览图大小
                            self.preview_frame = self.img_resize(self.sr.preview_frame)
                            
                        # 更新详细状态信息
                        if hasattr(self.sr, 'current_frame') and hasattr(self.sr, 'total_frames'):
                            self.status = f"处理中... ({self.sr.current_frame}/{self.sr.total_frames} 帧)"
                        elif hasattr(self.sr, 'progress_text'):
                            self.status = self.sr.progress_text
                        else:
                            self.status = f"处理中... {self.progress}%"
                        
                        progress(self.progress / 100, desc=self.status)
                        last_update = time.time()
                
                # 检查是否中止
                if self.abort_event.is_set():
                    self.status = "正在中止处理..."
                    progress(0, desc=self.status)
                    self.logger.info("检测到中止信号，正在停止处理")
                    break
                    
                time.sleep(0.1)
            # 确保线程结束后再返回
            if self.abort_event.is_set():
                # 等待线程完全结束
                self.processing_thread.join(timeout=2.0)
                self.logger.info("处理已中止")
                return self.preview_frame, "处理已中止"
            else:
                self.logger.info("视频处理完成")
                completion_msg = f"处理完成\n输出文件: {os.path.basename(self.output_path)}\n总耗时: {getattr(self.sr, 'processing_time', '未知')}"
                return self.preview_frame, completion_msg
        except Exception as e:
            self.status = f"错误: {str(e)}"
            self.is_processing = False
            self.logger.error(f"处理视频时发生异常: {str(e)}", exc_info=True)
            return None, self.status

    def abort_processing(self):
        """中止处理过程"""
        self.logger.info("收到中止处理请求")
        if self.is_processing:
            self.abort_event.set()
            self.status = "正在中止处理..."
            self.logger.info("已发送中止信号")

            # 尝试强制停止处理线程
            if self.processing_thread and self.processing_thread.is_alive():
                try:
                    # 非阻塞方式尝试停止
                    self.processing_thread.join(timeout=1.0)
                except RuntimeError:
                    pass

            self.logger.info("中止请求已发送")
            return "中止请求已发送"
        else:
            self.logger.info("没有正在进行的处理")
            return "没有正在进行的处理"

    def create_algorithm_params_ui(self):
        """创建算法参数设置UI"""
        with gr.Accordion("算法参数设置", open=False):
            # 算法选择
            algorithm = gr.Dropdown(
                choices=["STTN", "LAMA", "PROPAINTER"],
                value=self.algorithm_params["mode"],
                label="选择算法",
                interactive=True
            )

            # STTN参数
            with gr.Group(visible=True) as sttn_params:
                sttn_skip_detection = gr.Checkbox(
                    label="跳过字幕检测",
                    value=self.algorithm_params["sttn_skip_detection"],
                    interactive=True
                )
                sttn_neighbor_stride = gr.Slider(
                    minimum=1, maximum=200, step=1,
                    label="相邻帧步长（增大此值，提速）",
                    value=self.algorithm_params["sttn_neighbor_stride"],
                    interactive=True
                )
                sttn_reference_length = gr.Slider(
                    minimum=1, maximum=200, step=1,
                    label="参考帧长度（增大此值，降速增强效果）",
                    value=self.algorithm_params["sttn_reference_length"],
                    interactive=True
                )
                sttn_max_load_num = gr.Slider(
                    minimum=10, maximum=2000, step=5,
                    label="批处理大小（增大此值，提速增强效果，显存占用增大）",
                    value=self.algorithm_params["sttn_max_load_num"],
                    interactive=True
                )

            # LAMA参数
            with gr.Group(visible=False) as lama_params:
                lama_super_fast = gr.Checkbox(
                    label="极速模式（速度更快但效果稍差）",
                    value=self.algorithm_params["lama_super_fast"],
                    interactive=True
                )

            # PROPAINTER参数
            with gr.Group(visible=False) as propainter_params:
                propainter_max_load_num = gr.Slider(
                    minimum=10, maximum=4000, step=5,
                    label="最大处理帧数（值越大效果越好）",
                    value=self.algorithm_params["propainter_max_load_num"],
                    interactive=True
                )

            # 算法切换时更新可见参数组
            def update_param_visibility(selected_algorithm):
                return [
                    gr.update(visible=selected_algorithm == "STTN"),
                    gr.update(visible=selected_algorithm == "LAMA"),
                    gr.update(visible=selected_algorithm == "PROPAINTER")
                ]

            algorithm.change(
                update_param_visibility,
                inputs=algorithm,
                outputs=[sttn_params, lama_params, propainter_params]
            )

            # 参数收集
            params = {
                "mode": algorithm,
                "sttn_skip_detection": sttn_skip_detection,
                "sttn_neighbor_stride": sttn_neighbor_stride,
                "sttn_reference_length": sttn_reference_length,
                "sttn_max_load_num": sttn_max_load_num,
                "lama_super_fast": lama_super_fast,
                "propainter_max_load_num": propainter_max_load_num
            }

        return [
            algorithm,
            sttn_skip_detection,
            sttn_neighbor_stride,
            sttn_reference_length,
            sttn_max_load_num,
            lama_super_fast,
            propainter_max_load_num
        ]

    def _process_video_wrapper(self, *args):
        """包装函数将位置参数转换为字典格式"""
        keys = [
            "mode", "sttn_skip_detection", "sttn_neighbor_stride",
            "sttn_reference_length", "sttn_max_load_num",
            "lama_super_fast", "propainter_max_load_num"
        ]
        params = dict(zip(keys, args))
        return self.process_video(params)

    def create_file_management_tab(self):
        """创建文件管理标签页"""
        with gr.Tab("文件管理"):
            # 存储选中的文件路径
            selected_input_files = gr.State([])
            selected_output_files = gr.State([])

            # 初始化文件列表
            initial_input, initial_output, _, _ = full_refresh()

            gr.Markdown("## 🗂️ 文件管理")
            # 将操作状态移到顶部，在文件夹上方
            status = gr.Textbox(label="操作状态", interactive=False, value="就绪")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 📤 Input文件夹")
                    # 添加进度条组件（放在文件列表上方）
                    upload_progress = gr.Slider(
                        minimum=0, 
                        maximum=100, 
                        step=1,
                        label="上传进度",
                        interactive=False,
                        visible=False  # 初始隐藏，上传时才显示
                    )
                    input_files = gr.DataFrame(
                        headers=["选择", "文件名", "路径", "大小", "修改时间"],
                        datatype=["bool", "str", "str", "str", "str"],
                        interactive=True,
                        type="array",
                        value=initial_input
                    )

                    with gr.Row():
                        upload_btn = gr.UploadButton("⬆️ 上传视频", file_types=["video"])
                        refresh_input_btn = gr.Button("🔄 刷新")
                        clear_input_btn = gr.Button("🧹 清空文件夹", variant="stop")
                    with gr.Row():
                        download_selected_input = gr.Button("📥 下载选中文件")
                        delete_selected_input = gr.Button("🗑️ 删除选中文件", variant="stop")
                        rename_input_btn = gr.Button("✏️ 重命名选中文件", variant="secondary")
                    # 新增重命名行
                    with gr.Row():
                        rename_input_text = gr.Textbox(
                            label="新文件名(带扩展名)", 
                            placeholder="输入新文件名",
                            lines=1
                        )
                    gr.Markdown("**已选中文件:**")
                    input_selected_count = gr.Textbox("0", label="数量")
                    input_selected_display = gr.Textbox("暂无选中文件", label="文件列表", lines=4, interactive=False)

                with gr.Column():
                    gr.Markdown("### 📥 Output文件夹")
                    output_files = gr.DataFrame(
                        headers=["选择", "文件名", "路径", "大小", "修改时间"],
                        datatype=["bool", "str", "str", "str", "str"],
                        interactive=True,
                        type="array",
                        value=initial_output
                    )

                    with gr.Row():
                        refresh_output_btn = gr.Button("🔄 刷新")
                        # 添加复制到input按钮到同一行
                        copy_to_input_btn = gr.Button("📥 复制到Input", variant="primary")
                        clear_output_btn = gr.Button("🧹 清空文件夹", variant="stop")
                    with gr.Row():
                        download_selected_output = gr.Button("📥 下载选中文件")
                        delete_selected_output = gr.Button("🗑️ 删除选中文件", variant="stop")
                        rename_output_btn = gr.Button("✏️ 重命名选中文件", variant="secondary")
                    # 新增重命名行
                    with gr.Row():
                        rename_output_text = gr.Textbox(
                            label="新文件名(带扩展名)", 
                            placeholder="输入新文件名",
                            lines=1
                        )
                    gr.Markdown("**已选中文件:**")
                    output_selected_count = gr.Textbox("0", label="数量")
                    output_selected_display = gr.Textbox("暂无选中文件", label="文件列表", lines=4, interactive=False)

            # 下载组件
            download_comp = gr.File(label="下载文件", value=list_downloads())
            with gr.Row():
                clear_downloads_btn = gr.Button("🗑️ 清除所有下载文件", variant="stop")

            # 事件绑定
            refresh_input_btn.click(
                fn=lambda: full_refresh(),
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            refresh_output_btn.click(
                fn=lambda: full_refresh(),
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            
            def upload_file_with_progress(file):
                """带进度条的文件上传功能"""
                if not file:
                    return input_files, output_files, selected_input_files, selected_output_files, "ℹ️ 未选择文件进行上传"
                
                filename = os.path.basename(file.name)
                dest = os.path.join(INPUT_DIR, filename)
                logger.info(f"开始上传文件: {filename} 到 {INPUT_DIR} 目录")
                
                # 第一步：显示开始上传状态
                yield input_files, output_files, selected_input_files, selected_output_files, f"📤 开始上传: {filename} (0%)"
                
                try:
                    # 获取源文件大小
                    file_size = os.path.getsize(file.name)
                    chunk_size = 1024 * 1024  # 1MB chunks
                    copied_size = 0
                    
                    # 显示进度条
                    with open(file.name, 'rb') as src, open(dest, 'wb') as dst:
                        while True:
                            chunk = src.read(chunk_size)
                            if not chunk:
                                break
                            dst.write(chunk)
                            copied_size += len(chunk)
                            # 更新进度
                            progress_percent = min(copied_size / file_size, 1.0) * 100
                            
                            # 更新状态（每5%更新一次或最后一步）
                            if progress_percent % 5 < 0.1 or progress_percent > 99.9:
                                status_msg = f"📤 正在上传: {filename} ({progress_percent:.1f}%)"
                                yield input_files, output_files, selected_input_files, selected_output_files, status_msg
                    
                    logger.info(f"文件上传成功: {filename}")
                    status_msg = f"✅ 文件上传成功: {filename}"
                except Exception as e:
                    logger.error(f"文件上传失败: {filename}, 错误: {str(e)}")
                    status_msg = f"❌ 文件上传失败: {filename}"
                
                # 刷新文件列表
                input_list, output_list, _, _ = full_refresh()
                yield input_list, output_list, selected_input_files, selected_output_files, status_msg
            
            upload_btn.upload(
                fn=upload_file_with_progress,
                inputs=upload_btn,
                outputs=[input_files, output_files, selected_input_files, selected_output_files, status],
                show_progress="minimal"
            )
            
            delete_selected_input.click(
                fn=delete_files,
                inputs=selected_input_files,
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            delete_selected_output.click(
                fn=delete_files,
                inputs=selected_output_files,
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            download_selected_input.click(
                fn=download_files,
                inputs=selected_input_files,
                outputs=[download_comp, status]
            )
            download_selected_output.click(
                fn=download_files,
                inputs=selected_output_files,
                outputs=[download_comp, status]
            )
            clear_input_btn.click(
                fn=lambda: delete_files([os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR)]),
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            clear_output_btn.click(
                fn=lambda: delete_files([os.path.join(OUTPUT_DIR, f) for f in os.listdir(OUTPUT_DIR)]),
                outputs=[input_files, output_files, selected_input_files, selected_output_files]
            )
            clear_downloads_btn.click(
                fn=clear_downloads,
                outputs=[status, download_comp]
            )

            # 添加复制到input功能
            def copy_to_input(file_paths):
                if not file_paths:
                    return "请先选择文件"
                    
                copied_files = []
                for path in file_paths:
                    if os.path.exists(path):
                        try:
                            filename = os.path.basename(path)
                            dest = os.path.join(INPUT_DIR, filename)
                            shutil.copy2(path, dest)
                            copied_files.append(filename)
                        except Exception as e:
                            return f"复制失败: {str(e)}"
                    else:
                        return f"文件不存在: {path}"
                        
                return f"已复制 {len(copied_files)} 个文件到Input目录"

            copy_to_input_btn.click(
                fn=copy_to_input,
                inputs=selected_output_files,
                outputs=status
            )

            # 新增重命名事件绑定
            rename_input_btn.click(
                fn=rename_file,
                inputs=[selected_input_files, rename_input_text],
                outputs=[
                    status, 
                    input_files, 
                    output_files, 
                    selected_input_files, 
                    selected_output_files
                ]
            )
          
            rename_output_btn.click(
                fn=rename_file,
                inputs=[selected_output_files, rename_output_text],
                outputs=[
                    status, 
                    input_files, 
                    output_files, 
                    selected_input_files, 
                    selected_output_files
                ]
            )

            # 更新选择状态
            def update_selections(input_df, output_df, input_selected, output_selected):
                new_input_selected = [row[2] for row in input_df if row[0]]
                new_output_selected = [row[2] for row in output_df if row[0]]
                return (
                    new_input_selected,
                    new_output_selected,
                    str(len(new_input_selected)),
                    "\n".join([f"• {os.path.basename(p)}" for p in new_input_selected]) or "暂无选中文件",
                    str(len(new_output_selected)),
                    "\n".join([f"• {os.path.basename(p)}" for p in new_output_selected]) or "暂无选中文件"
                )

            input_files.change(
                fn=update_selections,
                inputs=[input_files, output_files, selected_input_files, selected_output_files],
                outputs=[
                    selected_input_files,
                    selected_output_files,
                    input_selected_count,
                    input_selected_display,
                    output_selected_count,
                    output_selected_display
                ]
            )
            output_files.change(
                fn=update_selections,
                inputs=[input_files, output_files, selected_input_files, selected_output_files],
                outputs=[
                    selected_input_files,
                    selected_output_files,
                    input_selected_count,
                    input_selected_display,
                    output_selected_count,
                    output_selected_display
                ]
            )

    def create_subtitle_removal_tab(self):
        """创建去字幕标签页"""
        with gr.Tab("去字幕"):
            gr.Markdown("## 🎬 视频字幕去除器")

            with gr.Row():
                # 左侧控制面板
                with gr.Column(scale=1):
                    # 视频选择
                    with gr.Column():
                        # 添加空选项作为默认值
                        initial_choices = ["-- 请选择 --"] + [f for f in os.listdir(INPUT_DIR) if
                                     f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]
                        
                        video_selector = gr.Dropdown(
                            choices=initial_choices,
                            label="选择视频文件",
                            interactive=True,
                            value="-- 请选择 --"  # 设置默认值
                        )
                        with gr.Row():
                            refresh_video_btn = gr.Button("🔄 刷新列表", size="sm")
                            load_video_btn = gr.Button("📥 加载视频", size="sm", variant="primary")  # 添加加载按钮
                    
                    # 状态信息
                    status_display = gr.Textbox(label="状态", value="就绪", interactive=False, lines=3)
                                
                    # 创建视频列表更新函数
                    def update_video_list():
                        """更新视频列表"""
                        logger.info("更新视频列表")
                        video_list = [f for f in os.listdir(INPUT_DIR) if 
                                      f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]
                        logger.info(f"找到 {len(video_list)} 个视频文件")
                        # 添加空选项作为第一个选项
                        choices = ["-- 请选择 --"] + video_list
                        return gr.update(choices=choices, value="-- 请选择 --")
                    
                    # 创建视频加载函数
                    def load_selected_video(filename):
                        """加载选中的视频"""
                        if filename == "-- 请选择 --" or not filename:
                            return None, "请选择要加载的视频文件", 0, 0, 0, 0, None, None, None
                        
                        # 加载视频
                        preview, status_msg = self.load_video(os.path.join(INPUT_DIR, filename))
                        
                        # 返回更新后的滑块值
                        ymin = self.ymin if self.ymin is not None else 0
                        ymax = self.ymax if self.ymax is not None else 0
                        xmin = self.xmin if self.xmin is not None else 0
                        xmax = self.xmax if self.xmax is not None else 0
                        
                        return (
                            preview, 
                            status_msg, 
                            ymin, 
                            ymax - ymin if ymax and ymin else 0, 
                            xmin, 
                            xmax - xmin if xmax and xmin else 0,
                            gr.update(minimum=0, maximum=self.frame_height if self.frame_height else 0),
                            gr.update(minimum=0, maximum=self.frame_width if self.frame_width else 0),
                            os.path.join(INPUT_DIR, filename)  # 添加视频路径用于完整预览
                        )

                    # 字幕区域设置
                    with gr.Accordion("字幕区域设置", open=True):
                        with gr.Row():
                            y_slider = gr.Slider(minimum=0, maximum=2000, step=1, label="Y位置", value=0,
                                                 interactive=True)
                            h_slider = gr.Slider(minimum=0, maximum=2000, step=1, label="高度", value=0,
                                                 interactive=True)
                        with gr.Row():
                            x_slider = gr.Slider(minimum=0, maximum=4000, step=1, label="X位置", value=0,
                                                 interactive=True)
                            w_slider = gr.Slider(minimum=0, maximum=4000, step=1, label="宽度", value=0,
                                                 interactive=True)
                        with gr.Row():
                            align_btn = gr.Button("对齐到视频底部中央", variant="secondary")
                            reset_btn = gr.Button("重置为默认位置", variant="secondary")
                        gr.Markdown("**提示**: 搭配使用滑块和预览图调整绿色矩形框位置，覆盖字幕区域")

                    # 算法参数设置
                    param_components = self.create_algorithm_params_ui()

                    # 处理按钮
                    process_btn = gr.Button("开始去除字幕", variant="primary")

                    # 中止按钮
                    abort_btn = gr.Button("中止处理", variant="stop")

                    # 进度条
                    progress_bar = gr.HTML("<div style='margin-top:10px;'><b>处理进度:</b></div>")

                    # 输出
                    output_display = gr.Textbox(label="输出信息", interactive=False, lines=3)
                    output_file = gr.File(label="下载结果")

                # 右侧预览面板
                with gr.Column(scale=2):
                    # 完整视频预览
                    full_video_preview = gr.Video(label="完整视频预览", height=400)
                    # 视频预览（带坐标）
                    video_preview = gr.Image(label="视频预览（带坐标）", interactive=False)
                    # 处理预览
                    process_preview = gr.Image(label="处理过程预览", interactive=False)

            # 事件处理
            # 刷新按钮点击事件
            refresh_video_btn.click(
                fn=update_video_list,
                outputs=video_selector
            )
            
            # 加载按钮点击事件
            load_video_btn.click(
                fn=load_selected_video,
                inputs=video_selector,
                outputs=[
                    video_preview, 
                    status_display,
                    y_slider,
                    h_slider,
                    x_slider,
                    w_slider,
                    y_slider,  # 用于更新最大值
                    x_slider,  # 用于更新最大值
                    full_video_preview  # 添加完整视频预览输出
                ]
            )
                    
            # 下拉框选择事件保持不变
            video_selector.change(
                fn=lambda filename: (None, "请选择要加载的视频文件", 0, 0, 0, 0, gr.update(), gr.update(), None) if filename == "-- 请选择 --" or not filename else load_selected_video(filename),
                inputs=video_selector,
                outputs=[
                    video_preview, 
                    status_display,
                    y_slider,
                    h_slider,
                    x_slider,
                    w_slider,
                    y_slider,  # 用于更新最大值
                    x_slider,  # 用于更新最大值
                    full_video_preview  # 添加完整视频预览输出
                ]
            )

            # 滑块改变时更新预览
            y_slider.change(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )
            h_slider.change(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )
            x_slider.change(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )
            w_slider.change(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )

            # 对齐到视频底部中央
            def align_to_bottom_center():
                if not self.frame_height or not self.frame_width:
                    return [0, 0, 0, 0]

                # 设置字幕区域为视频底部中央
                width = self.frame_width * 0.9
                height = self.frame_height * 0.2
                x = self.frame_width * 0.05
                y = self.frame_height * 0.78

                return [y, height, x, width]

            align_btn.click(
                fn=align_to_bottom_center,
                inputs=[],
                outputs=[y_slider, h_slider, x_slider, w_slider]
            ).then(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )

            # 重置为默认位置
            def reset_to_default():
                if not self.frame_height or not self.frame_width:
                    return [0, 0, 0, 0]

                return [
                    self.frame_height * self.y_p,
                    self.frame_height * self.h_p,
                    self.frame_width * self.x_p,
                    self.frame_width * self.w_p,
                ]

            reset_btn.click(
                fn=reset_to_default,
                inputs=[],
                outputs=[y_slider, h_slider, x_slider, w_slider]
            ).then(
                fn=self.update_subtitle_area,
                inputs=[y_slider, h_slider, x_slider, w_slider],
                outputs=[video_preview, status_display]
            )

            # 去除字幕
            process_btn.click(
                fn=self._process_video_wrapper,
                inputs=param_components,
                outputs=[process_preview, output_display],
                show_progress="minimal"
            ).then(
                fn=lambda: self.output_path,
                inputs=[],
                outputs=output_file
            )

            # 中止按钮事件
            abort_btn.click(
                fn=self.abort_processing,
                inputs=[],
                outputs=status_display
            )

            # 添加使用说明
            with gr.Accordion("使用说明", open=False):
                gr.Markdown("""
                ### 视频字幕去除器使用指南

                1. **选择视频**: 从下拉框选择input_videos目录中的视频
                2. **设置字幕区域**: 
                   - 调整滑块设置绿色矩形框位置，覆盖字幕区域
                   - 使用"对齐到视频底部中央"按钮快速定位常见字幕位置
                   - 使用"重置为默认位置"恢复初始设置
                3. **算法参数设置**: 根据视频类型选择合适的算法和参数
                4. **开始处理**: 点击"开始去除字幕"按钮
                5. **查看结果**: 处理完成后可在下方下载处理后的文件

                ### 状态信息说明

                - **就绪**: 系统等待操作
                - **加载中**: 正在加载视频文件
                - **处理中**: 正在去除字幕
                - **处理完成**: 字幕去除完成，可下载结果
                - **处理错误**: 处理过程中发生错误
                - **处理已中止**: 用户中止了处理过程
                """)

    def create_ui(self):
        """创建包含文件管理和去字幕两个标签页的UI"""
        with gr.Blocks(title="视频字幕去除器", theme=gr.themes.Soft()) as demo:
            gr.Markdown("# 🎬 视频字幕去除器")
            gr.Markdown("上传视频到input_videos目录，处理后的视频保存到output_videos目录")

            # 创建标签页
            self.create_file_management_tab()
            self.create_subtitle_removal_tab()

        return demo


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    webui = SubtitleRemoverWebUI()
    demo = webui.create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860)