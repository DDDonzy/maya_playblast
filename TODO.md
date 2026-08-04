## 用户反馈
- install ffmpeg.py 合并到 install.py 中
- playblast_src 文件夹中新建一个ui 文件夹，把 attach...,playblast_ui.py，qrc_res_playblast.py.....等等和ui相关的代码工程放进去
- scene_audio.py 改名为 audio
- 和核心逻辑无关的，debug相关的工具，放在...src/_debug/文件夹中
- playblast.py 中有太多常量，部分常量可以新建一个config文件放进去
- validate 关键词我不喜欢，改为ensure
- _resolve_width_height 这个函数名我也不喜欢
- 有关获取场景数据的部分，我觉得可以做一个通用的dataclass，dataclass包含一些方法，从场景获取数据，写入自身的dataclass
- _focus_panel 或许我们根本不需要这个方法，直接再命令最开始就记录panel，填充到dataclass，后面_load_path丢失焦点也无所谓，palyblast的时候，直接使用记录的panel填充到playblast函数的参数中
- sequence_to_video 是一个纯粹的，脱离maya环境的方法，我觉得可以分理playblast.py,新开一个文件

以上都是我的看法，不全对。
我需要你根据我的建议，以及你的理解，重构这个项目。
（这个项目最开始没有考虑那么多问题，很多东西都是一边做一边改的，最终完成有点狗屎山的味道了）
需要你根据我们现在的代码功能进行重构，尤其是ui部分，更加的乱，需要你帮忙重构。

## 重构注重一下几点：
- 代码精简，如果为了一个很不重要的功能，让代码变得有点屎山味道，你可以询问我是否要保留这个功能
- 不要有太多防御性编程，这个项目最终只会给用户开放ui点击的功能，应该不会有很多问题
- UI 环节实现 要简化
- 涉及到 路径相关内容，采用pathlib.Path 处理，最终传递到cmd参数或者maya参数的时候，转为str
- 只需要简单的类型备注，类型备注不要太不人性化
- 如果一个功能50行代码即可实现，你用了200行，请你重写
- 函数，变量名字尽量不要使用简写，使用通俗易懂的单词描述
