import os
import random
import asyncio
import re
from PIL import Image
from io import BytesIO
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

# 插件配置
IMAGE_FOLDER = "/var/lib/docker/overlay2/31c9b245627b42ad7fa45585fbeefca8f7bd81d73457d14d806fceb74fa53529/merged/guess_images"  # 使用绝对路径
CROP_SIZE_RATIO = 0.05  # 截取比例（原图的5%）
TIMEOUT = 60  # 游戏超时时间（秒）

# PJSK角色别名映射表（全名、简称、缩写）
PJSK_CHARACTERS = {
    # 初音未来组
    "初音ミク": ["miku", "初音", "ミク", "葱娘", "haku"],
    "鏡音リン": ["rin", "镜音铃", "リン", "镜音"],
    "鏡音レン": ["len", "镜音连", "レン"],
    "巡音ルカ": ["luka", "巡音", "ルカ"],
    
    # 25时Nightcord组
    "宵崎奏": ["kanade", "奏"],
    "朝比奈まふゆ": ["mafuyu", "朝比奈", "まふゆ", "mfy"],
    "東雲絵名": ["ena", "东云绘名", "絵名", "绘名"],
    "暁山瑞希": ["mizuki", "晓山瑞希", "瑞希", "みずき"],
    
    # Wonderlands x Showtime组
    "草薙寧々": ["nene", "草薙宁宁", "宁宁", "寧々"],
    "神代類": ["rui", "神代类", "類", "类"],
    "鳳えむ": ["emu", "凤绘梦", "えむ", "绘梦"],
    "天馬司": ["tsukasa", "天马司", "司"],
    
    # Leo/need组
    "星乃一歌": ["ichika", "星乃一歌", "一歌"],
    "日野森志歩": ["shiho", "日野森志步", "志步", "志歩"],
    "天馬咲希": ["saki", "天马咲希", "咲希"],
    "望月穂波": ["honami", "望月穗波", "穂波", "穗波"],
    
    # Vivid BAD SQUAD组
    "小豆沢こはね": ["kohane", "小豆沢心羽", "心羽"],
    "東雲彰人": ["akito", "东云彰人", "彰人"],
    "青柳冬弥": ["toya", "青柳冬弥", "冬弥"],
    "白石杏": ["an", "白石杏", "杏"],
}

@register(
    "astrbot_plugin_pjskct",
    "bunana417",
    "PJSK角色猜图游戏插件",
    "1.0.0",
    "https://github.com/banana417/astrbot_plugin_pjskct"
)
class PJSKGuessGamePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.active_games = {}  # 存储当前活跃的游戏 {会话ID: 游戏数据}
        self.character_files = self._load_character_files()  # 加载角色图片文件
        
        # 创建图片目录（如果不存在）
        os.makedirs(IMAGE_FOLDER, exist_ok=True)
    
    def _load_character_files(self):
        """加载角色图片文件并映射到标准角色名"""
        if not os.path.exists(IMAGE_FOLDER):
            logger.warning(f"图片目录不存在: {IMAGE_FOLDER}")
            return {}
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        character_mapping = {}
        
        for filename in os.listdir(IMAGE_FOLDER):
            if not os.path.isfile(os.path.join(IMAGE_FOLDER, filename)):
                continue
                
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in valid_extensions:
                continue
            
            # 提取基础文件名（不含扩展名）
            base_name = os.path.splitext(filename)[0]
            
            # 去除文件名中的编号部分（如"miku01" -> "miku"）
            clean_name = re.sub(r'\d+$', '', base_name)  # 移除末尾数字
            
            # 尝试匹配标准角色名
            matched_character = None
            for char_name, aliases in PJSK_CHARACTERS.items():
                # 检查文件名是否匹配角色名或别名
                normalized_name = clean_name.lower().replace(' ', '').replace('_', '')
                if normalized_name == char_name.lower().replace(' ', ''):
                    matched_character = char_name
                    break
                for alias in aliases:
                    if normalized_name == alias.lower().replace(' ', ''):
                        matched_character = char_name
                        break
                if matched_character:
                    break
            
            # 如果没有匹配到标准角色，使用文件名作为角色名
            if not matched_character:
                matched_character = clean_name
                logger.warning(f"无法匹配角色: {clean_name}")
            
            # 将文件添加到角色映射
            if matched_character not in character_mapping:
                character_mapping[matched_character] = []
            character_mapping[matched_character].append(os.path.join(IMAGE_FOLDER, filename))
        
        return character_mapping
    
    def _get_random_character(self):
        """随机选择一个角色和该角色的随机图片"""
        if not self.character_files:
            logger.error("没有可用的角色图片")
            return None, None, None
        
        character = random.choice(list(self.character_files.keys()))
        image_path = random.choice(self.character_files[character])
        return character, image_path, PJSK_CHARACTERS.get(character, [])
    
    def _crop_small_square(self, image_path):
        """截取图片中一个很小的正方形部分"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                
                # 计算正方形截取大小（取宽高中较小值的5%）
                min_dimension = min(width, height)
                crop_size = int(min_dimension * CROP_SIZE_RATIO)
                
                # 确保截取大小至少为10像素
                crop_size = max(crop_size, 10)
                
                # 计算随机截取位置
                left = random.randint(0, width - crop_size)
                top = random.randint(0, height - crop_size)
                
                # 截取正方形区域
                cropped = img.crop((left, top, left + crop_size, top + crop_size))
                
                # 转换为字节流
                byte_arr = BytesIO()
                cropped.save(byte_arr, format='PNG')
                return byte_arr.getvalue()
        except Exception as e:
            logger.error(f"图片处理失败: {str(e)}")
            return None
    
    @filter.command("#猜图")
    async def start_guess_game(self, event: AstrMessageEvent):
        """开始猜图游戏"""
        session_id = event.unified_msg_origin
        
        # 检查是否已有游戏进行中
        if session_id in self.active_games:
            yield event.plain_result("⏳ 当前已有游戏进行中，请先完成或等待超时！")
            return
        
        # 检查是否有可用的角色图片
        if not self.character_files:
            yield event.plain_result("❌ 角色图片库为空，请联系管理员添加PJSK角色图片！")
            return
        
        # 随机选择角色
        character, image_path, aliases = self._get_random_character()
        
        # 生成截图
        cropped_image = self._crop_small_square(image_path)
        if not cropped_image:
            yield event.plain_result("❌ 图片处理失败，请重试！")
            return
        
        # 存储游戏状态
        self.active_games[session_id] = {
            "character": character,
            "aliases": [a.lower() for a in aliases] + [character.lower()],
            "image_path": image_path,
            "timeout_task": None
        }
        
        # 发送截取的部分图片
        yield event.image_result(cropped_image, filename="PJSK猜角色挑战.png")
        
        # 发送游戏提示
        hint = (
            "🎵 PJSK角色猜图游戏开始！\n"
            "根据图片片段猜出Project SEKAI的角色\n"
            f"你有 {TIMEOUT} 秒时间回答，直接在聊天框输入角色名字\n"
            "提示：可以输入角色全名、简称或缩写\n"
            "示例: miku、初音、司、akito\n"
            "回答格式: #猜图 答案"
        )
        yield event.plain_result(hint)
        
        # 设置超时任务
        self.active_games[session_id]["timeout_task"] = asyncio.create_task(
            self._game_timeout(session_id)
        )
    
    async def _game_timeout(self, session_id):
        """游戏超时处理"""
        await asyncio.sleep(TIMEOUT)
        
        if session_id in self.active_games:
            game_data = self.active_games.pop(session_id)
            character = game_data["character"]
            
            # 发送完整图片作为提示
            full_image = None
            try:
                with open(game_data["image_path"], "rb") as f:
                    full_image = f.read()
            except Exception as e:
                logger.error(f"无法读取完整图片: {str(e)}")
            
            # 通知会话超时
            message = (
                f"⏰ 时间到！游戏结束\n"
                f"正确答案是: {character}\n"
                "输入 #猜图 开始新游戏"
            )
            
            # 发送消息
            response = [Comp.Plain(message)]
            
            if full_image:
                # 获取图片文件名（不含路径）
                filename = os.path.basename(game_data["image_path"])
                response.append(Comp.Image(full_image, filename=filename))
            
            await self.context.send_message(session_id, response)
    
    @filter.command("#猜图")
    async def check_answer(self, event: AstrMessageEvent, user_answer: str):
        """检查用户答案"""
        session_id = event.unified_msg_origin
        
        # 检查当前会话是否有游戏进行中
        if session_id not in self.active_games:
            # 如果没有进行中的游戏，提示开始新游戏
            yield event.plain_result("⚠️ 当前没有进行中的猜图游戏，发送 #猜图 开始新游戏")
            return
        
        game_data = self.active_games[session_id]
        valid_answers = game_data["aliases"]
        character = game_data["character"]
        
        # 标准化用户答案
        user_answer = user_answer.strip().lower()
        
        # 验证答案（支持多种别名）
        if user_answer in valid_answers:
            # 取消超时任务
            if game_data["timeout_task"]:
                game_data["timeout_task"].cancel()
            
            # 移除游戏状态
            self.active_games.pop(session_id)
            
            # 发送完整图片
            full_image = None
            try:
                with open(game_data["image_path"], "rb") as f:
                    full_image = f.read()
            except Exception as e:
                logger.error(f"无法读取完整图片: {str(e)}")
            
            # 发送成功消息
            response = [
                Comp.Plain(
                    f"🎉 恭喜你猜对了！\n"
                    f"正确答案是: {character}\n"
                    "输入 #猜图 开始新游戏"
                )
            ]
            
            if full_image:
                # 获取图片文件名（不含路径）
                filename = os.path.basename(game_data["image_path"])
                response.append(Comp.Image(full_image, filename=filename))
            
            yield event.chain_result(response)
        else:
            # 提示错误但继续游戏
            yield event.plain_result("❌ 答案不正确，请再试一次！")
    
    async def terminate(self):
        """插件卸载时清理所有游戏"""
        for session_id, game_data in list(self.active_games.items()):
            if game_data["timeout_task"]:
                game_data["timeout_task"].cancel()
            self.active_games.pop(session_id)
