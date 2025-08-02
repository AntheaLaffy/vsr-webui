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
import sys
import importlib
import backend.config as config_module
from backend.config import InpaintMode

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend.main
from backend.tools.common_tools import is_image_file


class SubtitleRemoverWebUI:
    def __init__(self):
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
                return None, "请输入视频文件路径"

            self.video_path = video_path
            self.video_cap = cv2.VideoCapture(video_path)

            if not self.video_cap.isOpened():
                return None, f"错误: 无法打开视频文件: {video_path}"

            # 获取视频信息
            self.frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT) + 0.5)
            self.frame_height = int(self.video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.frame_width = int(self.video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.fps = self.video_cap.get(cv2.CAP_PROP_FPS)

            # 读取第一帧
            ret, frame = self.video_cap.read()
            if not ret:
                return None, "错误: 无法读取视频帧"

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
            return resized_frame, f"已加载: {os.path.basename(video_path)}\n尺寸: {self.frame_width}x{self.frame_height} | 帧率: {self.fps:.1f}"
        except Exception as e:
            return None, f"错误: {str(e)}"

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
            return resized_frame, f"字幕区域: Y:{y}-{y + h} X:{x}-{x + w}"
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
                elif not os.path.exists(self.video_path):
                    error_msg += f" - 文件不存在: {self.video_path}"
                else:
                    error_msg += f" - 无效路径类型: {type(self.video_path)}"

                self.status = error_msg
                print(error_msg)  # 打印到控制台
                self.is_processing = False
                return None, self.status

            # 创建字幕提取器
            subtitle_area = (self.ymin, self.ymax, self.xmin, self.xmax)

            # 创建配置字典 - 确保值在合理范围内
            safe_params = {
                "mode": str(params["mode"]),  # 确保是字符串
                "sttn_skip_detection": bool(params["sttn_skip_detection"]),
                "sttn_neighbor_stride": max(1, min(int(params["sttn_neighbor_stride"]), 200)),
                "sttn_reference_length": max(1, min(int(params["sttn_reference_length"]), 100)),
                "sttn_max_load_num": max(50, min(int(params["sttn_max_load_num"]), 500)),
                "lama_super_fast": bool(params["lama_super_fast"]),
                "propainter_max_load_num": max(20, min(int(params["propainter_max_load_num"]), 1000))
            }

            # 打印参数用于调试
            print(f"Processing video with params: {safe_params}")

            # 创建字幕去除器
            self.sr = backend.main.SubtitleRemover(
                self.video_path,
                subtitle_area,
                True,
                safe_params
            )

            # 新增：传递中止事件给SubtitleRemover
            self.sr.abort_event = self.abort_event

            # 启动处理线程
            def run_remover():
                try:
                    self.sr.run()
                    if self.abort_event.is_set():
                        self.status = "处理已中止"
                        print("处理已中止")
                    else:
                        self.output_path = self.sr.video_out_name
                        self.status = "处理完成"
                except Exception as e:
                    self.status = f"处理错误: {str(e)}"
                finally:
                    self.is_processing = False
                    self.sr = None

            # 创建线程并启动（移动到函数外部）
            self.processing_thread = threading.Thread(target=run_remover)
            self.processing_thread.start()

            # 更新进度
            while self.processing_thread.is_alive():
                if self.sr:
                    self.progress = self.sr.progress_total
                    if self.sr.preview_frame is not None:
                        # 调整预览图大小
                        self.preview_frame = self.img_resize(self.sr.preview_frame)
                time.sleep(0.1)
                progress(self.progress / 100, desc=self.status)

                # 检查是否中止
                if self.abort_event.is_set():
                    break

            # 处理完成或中止
            if self.abort_event.is_set():
                self.status = "处理已中止"
                return self.preview_frame, self.status
            else:
                return self.preview_frame, self.status
        except Exception as e:
            self.status = f"错误: {str(e)}"
            self.is_processing = False
            return None, self.status

    def abort_processing(self):
        """中止处理过程"""
        if self.is_processing:
            self.abort_event.set()
            self.status = "正在中止处理..."
            print("中止请求已发送")
            return "中止请求已发送"
        else:
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
                    label="跳过字幕检测（极度不推荐）",
                    value=self.algorithm_params["sttn_skip_detection"],
                    interactive=True
                )
                sttn_neighbor_stride = gr.Slider(
                    minimum=1, maximum=50, step=1,
                    label="相邻帧步长（值越大速度越快）",
                    value=self.algorithm_params["sttn_neighbor_stride"],
                    interactive=True
                )
                sttn_reference_length = gr.Slider(
                    minimum=1, maximum=50, step=1,
                    label="参考帧长度（值越大效果越好）",
                    value=self.algorithm_params["sttn_reference_length"],
                    interactive=True
                )
                sttn_max_load_num = gr.Slider(
                    minimum=10, maximum=200, step=5,
                    label="批处理大小（值越大效果越好）",
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
                    minimum=10, maximum=200, step=5,
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

    def create_ui(self):
        """创建Gradio UI界面（中文版）"""
        with gr.Blocks(title=f"视频字幕去除器", theme=gr.themes.Soft()) as demo:
            gr.Markdown(f"## 🎬 视频字幕去除器")

            with gr.Row():
                # 左侧控制面板
                with gr.Column(scale=1):
                    # 视频输入
                    video_input = gr.Textbox(label="视频路径", placeholder="输入视频文件路径，或使用文件选择器选择")

                    # 文件选择器
                    video_upload = gr.File(
                        label="选择视频文件",
                        file_types=["video", "image"],
                        file_count="single"
                    )

                    load_btn = gr.Button("加载视频", variant="primary")

                    # 状态信息
                    status_display = gr.Textbox(label="状态", value="就绪", interactive=False)

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
                        gr.Markdown("**提示**: 拖动滑块调整绿色矩形框位置，覆盖字幕区域")

                    # 算法参数设置
                    param_components = self.create_algorithm_params_ui()

                    # 处理按钮
                    process_btn = gr.Button("开始去除字幕", variant="primary")

                    # 新增：中止按钮
                    abort_btn = gr.Button("中止处理", variant="stop")

                    # 进度条
                    progress_bar = gr.HTML("<div style='margin-top:10px;'><b>处理进度:</b></div>")

                    # 输出
                    output_display = gr.Textbox(label="输出信息", interactive=False)
                    output_file = gr.File(label="下载结果")

                # 右侧预览面板
                with gr.Column(scale=2):
                    # 视频预览
                    video_preview = gr.Image(label="视频预览（带坐标）", interactive=False)
                    # 处理预览
                    process_preview = gr.Image(label="处理过程预览", interactive=False)

            # 事件处理
            # 文件选择器选择文件后更新路径输入框
            video_upload.change(
                fn=lambda file: file.name if file else "",
                inputs=video_upload,
                outputs=video_input
            )

            # 加载视频
            load_btn.click(
                fn=self.load_video,
                inputs=video_input,
                outputs=[video_preview, status_display]
            ).then(
                fn=lambda status_msg: [self.ymin, self.ymax - self.ymin, self.xmin,
                                       self.xmax - self.xmin] if "错误" not in status_msg else [0, 0, 0, 0],
                inputs=status_display,
                outputs=[y_slider, h_slider, x_slider, w_slider]
            ).then(
                fn=lambda status_msg: [
                    gr.update(minimum=0, maximum=self.frame_height if "错误" not in status_msg else 0),
                    gr.update(minimum=0, maximum=self.frame_height if "错误" not in status_msg else 0),
                    gr.update(minimum=0, maximum=self.frame_width if "错误" not in status_msg else 0),
                    gr.update(minimum=0, maximum=self.frame_width if "错误" not in status_msg else 0),
                ],
                inputs=status_display,
                outputs=[y_slider, h_slider, x_slider, w_slider]
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
                inputs=param_components,  # 直接使用组件列表
                outputs=[process_preview, output_display],
                show_progress="minimal"
            ).then(
                fn=lambda: self.output_path,
                inputs=[],
                outputs=output_file
            )

            # 新增：中止按钮事件
            abort_btn.click(
                fn=self.abort_processing,
                inputs=[],
                outputs=[status_display]  # 使用已定义的 status_display 组件
            )

            # 添加使用说明
            with gr.Accordion("使用说明", open=False):
                gr.Markdown("""
                ### 视频字幕去除器使用指南

                1. **加载视频**:
                   - 在"视频路径"输入框中直接输入文件路径，或
                   - 使用"选择视频文件"按钮选择视频文件
                   - 点击"加载视频"按钮

                2. **设置字幕区域**:
                   - 调整滑块设置绿色矩形框位置，覆盖字幕区域
                   - 使用"对齐到视频底部中央"按钮快速定位常见字幕位置
                   - 使用"重置为默认位置"恢复初始设置

                3. **算法参数设置**:
                   - STTN算法：适合真人视频，速度快
                     - 跳过字幕检测：不能提高速度但可能遗漏字幕
                     - 相邻帧步长：值越大处理速度越快
                     - 参考帧长度：值越大效果越好，但太大可能爆显存
                     - 最大处理帧数：值越大效果越好
                   - LAMA算法：适合动画和图片
                     - 极速模式：速度更快但效果稍差
                   - PROPAINTER算法：适合运动剧烈视频
                     - 最大处理帧数：值越大效果越好

                4. **开始处理**:
                   - 点击"开始去除字幕"按钮
                   - 处理过程可能需要一些时间，请耐心等待
                   - 处理完成后可在"下载结果"处获取处理后的文件

                5. **提示**:
                   - 确保绿色矩形框完全覆盖字幕区域
                   - 矩形框不要覆盖重要画面内容
                   - 处理高分辨率视频需要更多时间和资源
                """)

        return demo


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    webui = SubtitleRemoverWebUI()
    demo = webui.create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860)
