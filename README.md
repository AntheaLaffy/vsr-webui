简体中文 | [English](README_en.md)

## 项目简介

![License](https://img.shields.io/badge/License-Apache%202-red.svg)
![python version](https://img.shields.io/badge/Python-3.11+-blue.svg)
![support os](https://img.shields.io/badge/OS-Windows/macOS/Linux-green.svg)  

VSR-WebUI fork自YaoFANGUK的VSR项目，继承GPL v2协议

Video-subtitle-remover (VSR) 是一款基于AI技术，将视频中的硬字幕去除的软件。

VSR-WebUI主要实现了以下功能：
- **无损分辨率**将视频中的硬字幕去除，生成去除字幕后的文件
- 通过超强AI算法模型，对去除字幕文本的区域进行填充（非相邻像素填充与马赛克去除）
- 支持自定义字幕位置，仅去除定义位置中的字幕（传入位置）
- 支持全视频自动去除所有文本（不传入位置）
- 支持多选图片批量去除水印文本
- 使用WebUI降低使用门槛

<p style="text-align:center;"><img src="https://github.com/AntheaLaffy/vsr-webui/raw/main/test/webui.png" alt="webui"/></p>

PS:前端程序的预览图片渲染可能有点问题，但问题不大，不影响后端处理结果，就当是一个彩蛋咯

**VSR-WebUI使用说明**

把源码下载下来
进入命令行,安装依赖文件
```bash
pip install -r requirements.txt
```
之后启动webui
```bash
python webui.py
```
看看有没有ModuleNotFound的报错，它的意思是依赖的模块还没有导入
以下图为例操作如下:
<p style="text-align:center;"><img src="https://github.com/AntheaLaffy/vsr-webui/raw/main/test/依赖找不到报错.png" alt="demo.png"/></p>
你别管图上错误追踪是啥意思，看最下方一行报错就了，缺失fsplit模块，你就导入fsplit模块，缺啥你导啥

```bash
pip install fsplit
```
然后继续重启webui直到成功为止
```bash
python webui.py
```

**VSR原项目使用说明：**

## 演示

- GUI版：

<p style="text-align:center;"><img src="https://github.com/YaoFANGUK/video-subtitle-remover/raw/main/design/demo2.gif" alt="demo2.gif"/></p>

- <a href="https://b23.tv/guEbl9C">点击查看演示视频👇</a>

<p style="text-align:center;"><a href="https://b23.tv/guEbl9C"><img src="https://github.com/YaoFANGUK/video-subtitle-remover/raw/main/design/demo.gif" alt="demo.gif"/></a></p>


#### 4. 源码使用教程

- 运行图形化界面

```shell
python gui.py
```

- 运行命令行版本(CLI)

```shell
python ./backend/main.py
```

## 常见问题
1. 提取速度慢怎么办

修改backend/config.py中的参数，可以大幅度提高去除速度
```python
MODE = InpaintMode.STTN  # 设置为STTN算法
STTN_SKIP_DETECTION = True # 跳过字幕检测，跳过后可能会导致要去除的字幕遗漏或者误伤不需要去除字幕的视频帧
```

2. 视频去除效果不好怎么办

修改backend/config.py中的参数，尝试不同的去除算法，算法介绍

> - InpaintMode.STTN 算法：对于真人视频效果较好，速度快，可以跳过字幕检测
> - InpaintMode.LAMA 算法：对于图片效果最好，对动画类视频效果好，速度一般，不可以跳过字幕检测
> - InpaintMode.PROPAINTER 算法： 需要消耗大量显存，速度较慢，对运动非常剧烈的视频效果较好

- 使用STTN算法

```python
MODE = InpaintMode.STTN  # 设置为STTN算法
# 相邻帧数, 调大会增加显存占用，效果变好
STTN_NEIGHBOR_STRIDE = 10
# 参考帧长度, 调大会增加显存占用，效果变好
STTN_REFERENCE_LENGTH = 10
# 设置STTN算法最大同时处理的帧数量，设置越大速度越慢，但效果越好
# 要保证STTN_MAX_LOAD_NUM大于STTN_NEIGHBOR_STRIDE和STTN_REFERENCE_LENGTH
STTN_MAX_LOAD_NUM = 30
```
- 使用LAMA算法
```python
MODE = InpaintMode.LAMA  # 设置为STTN算法
LAMA_SUPER_FAST = False  # 保证效果
```

> 如果对模型去字幕的效果不满意，可以查看design文件夹里面的训练方法，利用backend/tools/train里面的代码进行训练，然后将训练的模型替换旧模型即可

3. CondaHTTPError

将项目中的.condarc放在用户目录下(C:/Users/<你的用户名>)，如果用户目录已经存在该文件则覆盖

解决方案：https://zhuanlan.zhihu.com/p/260034241

4. 7z文件解压错误

解决方案：升级7-zip解压程序到最新版本

