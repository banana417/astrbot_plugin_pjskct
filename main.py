import os
import random
import shutil
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import astrbot.api.message_components as Comp
from PIL import Image
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# 角色别名映射（可扩展）
CHARACTER_ALIASES = {
    "初音未来": ["miku", "初音", "初音ミク", "haku", "m"],
    "镜音铃": ["rin", "镜音", "镜音リン", "l"],
    "镜音连": ["len", "连", "镜音レン", "r"],
    "巡音流歌": ["luka", "巡音", "巡音ルカ", "l"],
    "MEIKO": ["meiko", "大姐", "m"],
    "KAITO": ["kaito", "大哥", "k"],
    "宵崎奏": ["kanade", "奏", "宵崎", "k"],
    "朝比奈真冬": ["mafuyu", "真冬", "朝比奈", "m"],
    "东云绘名": ["ena", "绘名", "东云", "e"],
    "晓山瑞希": ["mizuki", "瑞希", "晓山", "m"],
    "白石杏": ["shiho", "杏", "白石", "s"],
    "日野森志步": ["saki", "志步", "日野森", "s"],
    "天马司": ["tsukasa", "司", "天马", "t"],
    "凤笑梦": ["emu", "笑梦", "凤", "e"],
    "草薙宁宁": ["nene", "宁宁", "草薙", "n"],
    "神代类": ["rui", "类", "神代", "r"],
}

class GameSession:
    """游戏会话状态管理"""
    def __init__(self, character: str, image_path: str, cropped_path: str):
        self.character = character  # 正确答案（角色名）
        self.start_time = datetime.now()
        self.image_path = image_path  # 原图路径
        self.cropped_path = cropped_path  # 截图路径
        self.guessed = False  # 是否已猜中

@register("astrbot_plugin_pjskct", "bunana417", "PJSK猜图游戏", "1.0.0")
class PJSKGuessGame(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.active_games: Dict[str, GameSession] = {}  # 当前活跃游戏 {会话ID: GameSession}
        self.plugin_dir = Path(__file__).parent
        self.config = self.load_config()
        self.images_info = self.scan_images()
        
        # 确保目录存在
        os.makedirs(self.get_absolute_path(self.config["cropped_dir"]), exist_ok=True)
        
    def get_absolute_path(self, relative_path: str) -> Path:
        """获取插件目录下的绝对路径"""
        return self.plugin_dir / relative_path
        
    def load_config(self) -> dict:
        """加载插件配置"""
        config_path = self.plugin_dir / "pjsk_config.json"
        default_config = {
            "image_dir": "pjskct1",  # 图片目录（相对于插件目录）
            "cropped_dir": "pjskct2",  # 截图目录（相对于插件目录）
            "crop_size": 200,  # 截图尺寸（正方形）
            "timeout": 60,  # 游戏超时时间（秒）
            "alias_map": CHARACTER_ALIASES  # 角色别名映射
        }
        
        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
        
        # 保存默认配置
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        return default_config
    
    def scan_images(self) -> List[Tuple[str, str]]:
        """扫描图片目录，返回(角色名, 图片路径)列表"""
        images = []
        image_dir = self.get_absolute_path(self.config["image_dir"])
        
        if not image_dir.exists():
            logger.warning(f"图片目录不存在: {image_dir}")
            # 尝试创建目录
            os.makedirs(image_dir, exist_ok=True)
            logger.info(f"已创建图片目录: {image_dir}")
            return images
        
        for file in image_dir.glob("*"):
            if file.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                # 从文件名提取角色名（格式：角色名_其他信息.扩展名）
                character = file.stem.split("_")[0]
                images.append((character, str(file)))
        
        logger.info(f"扫描到 {len(images)} 张图片")
        return images
    
    def get_random_image(self) -> Optional[Tuple[str, str]]:
        """随机获取一张图片"""
        if not self.images_info:
            return None
        return random.choice(self.images_info)
    
    def crop_image(self, image_path: str) -> str:
        """随机裁剪图片并保存，返回裁剪后的路径"""
        with Image.open(image_path) as img:
            width, height = img.size
            
            # 计算随机裁剪区域
            crop_size = min(self.config["crop_size"], width, height)
            left = random.randint(0, width - crop_size)
            top = random.randint(0, height - crop_size)
            
            # 裁剪并保存
            cropped = img.crop((left, top, left + crop_size, top + crop_size))
            cropped_dir = self.get_absolute_path(self.config["cropped_dir"])
            cropped_path = cropped_dir / f"cropped_{int(datetime.now().timestamp())}.png"
            cropped.save(cropped_path)
            
            return str(cropped_path)
    
    def check_answer(self, character: str, guess: str) -> bool:
        """检查答案是否正确"""
        # 标准化输入（去除空格和特殊字符，转为小写）
        normalized_guess = re.sub(r'\W+', '', guess).lower()
        normalized_char = re.sub(r'\W+', '', character).lower()
        
        # 检查直接匹配
        if normalized_guess == normalized_char:
    
