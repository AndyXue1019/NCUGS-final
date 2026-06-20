import asyncio
import math
import os
import re
import shutil
import platform
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial
from typing import Optional

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

from components.core import BotClient, CogBase


@dataclass
class Song:
    title: str = ''  # 標題
    play_url: str = ''  # 播放網址
    webpage_url: str = ''  # 網頁網址
    duration: float = 0.0  # 時長
    http_headers: dict = field(default_factory=dict)  # HTTP 標頭

    def __bool__(self) -> bool:
        return any(bool(v) for v in vars(self).values())

    def __str__(self):
        return (
            f'Title: {self.title}\n'
            f'Duration: {timedelta(seconds=self.duration)}\n'
            f'Play URL: {self.play_url}\n'
            f'Webpage URL: {self.webpage_url}\n'
            f'HTTP Headers: {self.http_headers}'
        )


@dataclass
class GuildData:
    now_play: Song | None = None  # 當前播放的音樂 Song | None
    music_queue: list[Song] = field(default_factory=list)  # 待播清單 list[Song]
    rpt_mode: str = 'off'  # 重複模式 str
    volume: float = 1.0  # 音量 float
    is_processing: bool = False
    prefetch_task: asyncio.Task | None = None  # 預載任務 asyncio.Task | None
    play_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # 播放操作鎖


class NowPlayingView(discord.ui.View):
    def __init__(self, cog, guild, timeout: float = 180.0):
        # 設定 3 分鐘後按鈕自動失效
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild = guild
        self.message: discord.Message | None = None

    def get_voice_client(self):
        return discord.utils.get(self.cog.bot.voice_clients, guild=self.guild)

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.primary, custom_id='np_play_pause')
    async def play_pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = self.get_voice_client()
        if not voice:
            await interaction.response.send_message('我不在語音頻道裡...', ephemeral=True)
            return

        # 切換暫停與播放狀態
        if voice.is_paused():
            voice.resume()
            await interaction.response.send_message('▶️ 音樂已繼續播放', ephemeral=True)
        elif voice.is_playing():
            voice.pause()
            await interaction.response.send_message('⏸️ 音樂已暫停', ephemeral=True)
        else:
            await interaction.response.send_message('目前沒有音樂可以播放或暫停。', ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary, custom_id='np_skip')
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = self.get_voice_client()
        if not voice or not voice.is_playing():
            await interaction.response.send_message('目前沒有播放中的音樂。', ephemeral=True)
            return

        guild_data: GuildData = self.cog.get_guild_data(self.guild.id)

        # 處理單曲循環時強制切歌的邏輯
        if guild_data.rpt_mode == 'single':
            guild_data.now_play = None

        voice.stop()
        await interaction.response.send_message('⏭️ 已跳過當前曲目', ephemeral=True)

        # 切歌後把這個面板的按鈕反灰，避免使用者重複點擊
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.danger, custom_id='np_stop')
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = self.get_voice_client()
        if not voice:
            await interaction.response.send_message('我不在語音頻道裡喔！', ephemeral=True)
            return

        guild_data = self.cog.get_guild_data(self.guild.id)
        guild_data.music_queue.clear()
        guild_data.now_play = None
        guild_data.is_processing = False

        # 取消可能正在背景倒數的預載任務
        if getattr(guild_data, 'prefetch_task', None):
            guild_data.prefetch_task.cancel()

        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await voice.disconnect()

        await interaction.response.send_message('好，我走。', ephemeral=True)

        # 停止後將按鈕全面反灰
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    async def on_timeout(self):
        """超過設定時間後自動停用按鈕"""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class QueuePaginationView(discord.ui.View):
    def __init__(self, queue: list, sec_to_hms_func, per_page: int = 10, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.queue = queue
        self.per_page = per_page
        self.sec_to_hms = sec_to_hms_func
        self.current_page = 1
        self.total_pages = math.ceil(len(self.queue) / self.per_page)
        self.message: discord.Message | None = None
        self.update_buttons()

    def update_buttons(self):
        """根據當前頁數狀態，啟用或停用按鈕"""
        self.first_page_btn.disabled = self.current_page == 1
        self.prev_page_btn.disabled = self.current_page == 1
        self.next_page_btn.disabled = self.current_page == self.total_pages
        self.last_page_btn.disabled = self.current_page == self.total_pages

    def generate_embed(self) -> discord.Embed:
        """根據當前頁數產生對應的 Embed"""
        start_idx = (self.current_page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        current_items = self.queue[start_idx:end_idx]

        description = ''
        for i, song in enumerate(current_items, start=start_idx + 1):
            description += f'**{i}.** [{song.title}]({song.webpage_url}) - `{self.sec_to_hms(song.duration)}`\n'

        embed = discord.Embed(
            title='🎶 待播清單',
            description=description,
            color=0x1DB954,
        )
        embed.set_footer(
            text=f'第 {self.current_page} / {self.total_pages} 頁 • 總共 {len(self.queue)} 首歌曲'
        )
        return embed

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary)
    async def first_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(emoji='◀️', style=discord.ButtonStyle.primary)
    async def prev_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(emoji='▶️', style=discord.ButtonStyle.primary)
    async def next_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary)
    async def last_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def on_timeout(self):
        """當選單超過設定時間沒有人按，自動停用所有按鈕"""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # 嘗試更新訊息以顯示停用的按鈕
        try:
            # 我們需要保存最初發送的 message 物件來編輯它
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except Exception:
            pass


class Music(CogBase):
    def __init__(self, bot: BotClient):
        super().__init__(bot)
        self.guilds: dict[int, GuildData] = {}
        self.YDL_SEARCH_OPTIONS = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
        }
        self.YDL_PLAY_OPTIONS = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'remote_components': ['ejs:github'],
            'extractor_args': {'youtube': ['player_client=android,ios,web']},
            # 'cookiesfrombrowser': ('chrome',),
            'cookiefile': './data/yt_cookies.txt',
        }
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -loglevel quiet -hide_banner -b:a 256k -bufsize 256k -maxrate 256k',
        }
        self.invalid_keywords = [
            '[private video]',
            '[deleted video]',
            '[video unavailable]',
            '[deleted]',
            'video unavailable',
            'private video',
        ]

    def get_guild_data(self, guild_id: int) -> GuildData:
        # 初始化伺服器的快取
        if guild_id not in self.guilds:
            self.guilds[guild_id] = GuildData()
        return self.guilds[guild_id]

    def get_voice(self, guild):
        return discord.utils.get(self.bot.voice_clients, guild=guild)

    def get_ffmpeg_exec(self) -> str:
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path
        
        system = platform.system()
        if system == 'Windows':
            ffmpeg_exe = shutil.which('ffmpeg.exe')
            if ffmpeg_exe:
                return ffmpeg_exe
            for path in [
                'C:\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
            ]:
                if os.path.exists(path):
                    return path
            return 'ffmpeg.exe'
        elif system == 'Darwin':  # macOS
            for path in ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg']:
                if os.path.exists(path):
                    return path
        return 'ffmpeg'

    def is_valid_source(self, title: str) -> bool:
        if not title:
            return False

        title = title.lower()
        if title in self.invalid_keywords:
            return False

        if not title.strip():
            return False

        return True

    def sec_to_hms(self, seconds: float) -> str:
        hms_time = str(timedelta(seconds=seconds))
        if hms_time.startswith('0:'):
            hms_time = hms_time[2:]
            return hms_time
        return hms_time

    def search(self, item: str, is_url: bool) -> Song | list[Song] | None:
        with YoutubeDL(self.YDL_SEARCH_OPTIONS) as ydl:
            try:
                if is_url:
                    info = ydl.extract_info(item, download=False)
                else:
                    info = ydl.extract_info(f'ytsearch1:{item}', download=False)['entries'][0]
            except Exception as e:
                self.logger.error(f'yt-dlp 擷取失敗: {e}')
                return None  # 如果是不支援的網址或擷取失敗，回傳 None

            if 'entries' in info:  # 播放清單
                songs = []
                for entry in info['entries']:
                    if entry:
                        title = entry.get('title', 'Unknown Title')
                        if not self.is_valid_source(title):
                            continue  # 跳過無效的來源

                        raw_duration = entry.get('duration')
                        duration = float(raw_duration) if raw_duration is not None else 0.0

                        webpage_url = (
                            entry.get('webpage_url', '')
                            if entry.get('webpage_url')
                            else entry.get('url', '')
                        )

                        songs.append(
                            Song(
                                title=title,
                                webpage_url=webpage_url,
                                duration=duration,
                            )
                        )
                return songs
            else:  # 單曲
                title = info.get('title', 'Unknown Title')
                if not self.is_valid_source(title):
                    return None

                raw_duration = info.get('duration')
                duration = float(raw_duration) if raw_duration is not None else 0.0

                webpage_url = (
                    info.get('webpage_url', '') if info.get('webpage_url') else info.get('url', '')
                )

                return Song(
                    title=title,
                    webpage_url=webpage_url,
                    duration=duration,
                )

    def extract(self, song: Song) -> None:
        with YoutubeDL(self.YDL_PLAY_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(song.webpage_url, download=False)
                song.play_url = info.get('url', '')
                song.http_headers = info.get('http_headers', {})
            except Exception as e:
                self.logger.error(f'yt-dlp 擷取播放網址失敗: {e}')

    async def _prefetch_next_song(self, guild_id: int, delay: float):
        try:
            # 倒數計時 (例如歌曲總長 200 秒，delay 就是 190 秒)
            await asyncio.sleep(delay)

            guild_data = self.get_guild_data(guild_id)

            if not guild_data.music_queue or guild_data.rpt_mode == 'single':
                return

            next_song = guild_data.music_queue[0]

            if not next_song.play_url:
                func = partial(self.extract, next_song)
                await self.bot.loop.run_in_executor(None, func)

        except asyncio.CancelledError:
            pass

    async def _async_play_next(self, ctx: commands.Context, voice: discord.VoiceClient):
        guild_data = self.get_guild_data(ctx.guild.id)

        if not voice.is_connected():
            guild_data.is_processing = False
            return

        async with guild_data.play_lock:
            try:
                if not voice.is_connected():
                    return

                # 處理上一首歌的狀態與重複播放邏輯
                if guild_data.now_play:
                    if guild_data.rpt_mode == 'single':
                        pass
                    elif guild_data.rpt_mode == 'all':
                        guild_data.music_queue.append(guild_data.now_play) # 將上一首歌放回queue
                    else:
                        guild_data.now_play = None

                # 如果目前沒有要播的歌，從待播清單中取出
                if not guild_data.now_play:
                    if not guild_data.music_queue:
                        # 如果音樂隊列為空，設置 5 分鐘後讓機器人離開語音頻道
                        async def disconnect_after_delay():
                            await asyncio.sleep(300)
                            if (
                                not guild_data.music_queue
                                and not voice.is_playing()
                                and voice.is_connected()
                            ):
                                await voice.disconnect()

                        asyncio.run_coroutine_threadsafe(disconnect_after_delay(), self.bot.loop)
                        return
                    # 從清單拿出下一首歌
                    guild_data.now_play = guild_data.music_queue.pop(0)

                # JIT 延遲載入，如果這首歌還沒有播放連結，進行提取
                if not guild_data.now_play.play_url:
                    func = partial(self.extract, guild_data.now_play)
                    await self.bot.loop.run_in_executor(None, func)

                # 如果提取失敗（可能是版權、年齡限制等），自動跳過
                if not guild_data.now_play.play_url:
                    await ctx.send(f'⚠️ 無法取得 `{guild_data.now_play.title}` 的播放音源，自動跳過。')
                    guild_data.now_play = None
                    # 建立任務去播下一首，避免無限遞迴卡死
                    self.bot.loop.create_task(self._async_play_next(ctx, voice))
                    return

                play_url = guild_data.now_play.play_url

                # 組合 FFmpeg 標頭參數並播放
                ffmpeg_kwargs = self.FFMPEG_OPTIONS.copy()
                if guild_data.now_play.http_headers:
                    headers = ''.join(f'{k}: {v}\r\n' for k, v in guild_data.now_play.http_headers.items())
                    ffmpeg_kwargs['before_options'] = (
                        f'-headers "{headers}" ' + ffmpeg_kwargs['before_options']
                    )

                voice.play(
                    discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(play_url, **ffmpeg_kwargs, executable=self.get_ffmpeg_exec()),
                        volume=guild_data.volume,
                    ),
                    after=lambda _: self.play_next(ctx, voice),
                )

                # 預載下一首：如果這首歌的長度超過15秒，則在快結束前10秒開始預載下一首
                if getattr(guild_data, 'prefetch_task', None):
                    guild_data.prefetch_task.cancel()

                if guild_data.now_play and guild_data.music_queue and guild_data.now_play.duration > 15:
                    delay = guild_data.now_play.duration - 10  # 在歌曲結束前10秒開始預載下一首
                    guild_data.prefetch_task = self.bot.loop.create_task(
                        self._prefetch_next_song(ctx.guild.id, delay)
                    )
            finally:
                guild_data.is_processing = False

    def play_next(self, ctx: commands.Context, voice: discord.VoiceClient):
        if not voice.is_connected():
            return
        asyncio.run_coroutine_threadsafe(self._async_play_next(ctx, voice), self.bot.loop)

    @commands.command(aliases=['p'], help='用歌名或YouTube、SoundCloud等等連結來播放音樂')
    async def play(self, ctx: commands.Context, *args):
        # 檢查使用者是否在語音頻道中
        if ctx.author.voice is None:
            await ctx.send('請先加入一個語音頻道')
            return

        # 嘗試連接到使用者所在的語音頻道
        voice = self.get_voice(ctx.guild)
        if voice is None:
            try:
                voice = await ctx.author.voice.channel.connect()
            except Exception as e:
                await ctx.send(f'無法連接到語音頻道: {e}')
                return

        song_query = ' '.join(args)
        # 檢查是否有輸入歌曲名稱或連結
        if not song_query:
            await ctx.send('請輸入歌曲名稱或連結')
            return

        # 取得伺服器的快取
        guild_data = self.get_guild_data(ctx.guild.id)

        is_url = bool(re.match(r'^https?://', song_query))
        func = partial(self.search, song_query, is_url=is_url)
        song_info = await self.bot.loop.run_in_executor(None, func)
        if song_info is None:
            await ctx.send('無法解析該連結或找不到歌曲，可能是不支援的網站。')
            return

        if isinstance(song_info, list):
            guild_data.music_queue.extend(song_info)
            await ctx.send(f'偵測到播放清單，已加入 `{len(song_info)}` 首歌曲到待播清單')
        else:
            guild_data.music_queue.append(song_info)
            await ctx.send(f'已加入 `{song_info.title}` 到待播清單')

        if voice.is_playing() and guild_data.rpt_mode == 'single':
            await ctx.send('啊你都開了單曲循環了...?')

        if not voice.is_playing() and not voice.is_paused() and not guild_data.is_processing:
            guild_data.is_processing = True
            self.bot.loop.create_task(self._async_play_next(ctx, voice))

    @commands.command(
        aliases=['rpt'],
        help='重複播放模式: off(關閉,預設), all(全部)、single(單首)或now(查看當前狀態)',
    )
    async def repeat(self, ctx: commands.Context, rpt: Optional[str] = None):
        guild_data = self.get_guild_data(ctx.guild.id)
        rpt = rpt.lower() if rpt else None
        # 沒有給參數則在off, all, single間切換
        if rpt is None:
            match guild_data.rpt_mode:
                case 'off':
                    guild_data.rpt_mode = 'all'
                case 'all':
                    guild_data.rpt_mode = 'single'
                case 'single':
                    guild_data.rpt_mode = 'off'
            await ctx.send(f'已切換重複播放，目前模式 `{guild_data.rpt_mode}`')
        elif rpt == 'now':
            await ctx.send(f'目前重複播放模式為 `{guild_data.rpt_mode}`')
        elif rpt in ['off', 'all', 'single']:
            guild_data.rpt_mode = rpt
            await ctx.send(f'已設定重複播放模式為 `{guild_data.rpt_mode}`')
        else:
            await ctx.send(
                '請輸入有效的模式: `[off, all, single, now]`，不輸入則在[off, all, single]之間切換'
            )

    @commands.command(aliases=['vol'], help='調整為輸入之音量%數(0~500%)，不輸入則顯示當前音量')
    async def volume(self, ctx: commands.Context, vol: Optional[int] = None):
        guild_data = self.get_guild_data(ctx.guild.id)
        voice = self.get_voice(ctx.guild)
        if vol is None:
            await ctx.send(f'目前音量為 {int(guild_data.volume * 100)}%')
        elif not 0 <= vol <= 500:
            await ctx.send('請輸入有效的音量(0~500%)')
            return
        elif vol > 200:
            msg = await ctx.send('你確定嗎?')
            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

            try:
                reaction, _ = await self.bot.wait_for(
                    'reaction_add',
                    timeout=10.0,
                    check=lambda r, u: u == ctx.author and str(r.emoji) in ['✅', '❌'],
                )
                if str(reaction.emoji) == '❌':
                    await ctx.send('音量調整已取消')
                    return
            except asyncio.TimeoutError:
                await ctx.send('等待逾時，音量調整已取消')
                return

        guild_data.volume = vol / 100.0  # type: ignore

        if voice.source:
            voice.source.volume = guild_data.volume
        await ctx.send(f'已調整音量為 {vol}%')

    @commands.command(help='暫停播放音樂')
    async def pause(self, ctx: commands.Context):
        voice = self.get_voice(ctx.guild)
        try:
            if voice.is_playing():
                voice.pause()
            else:
                await ctx.send('我沒有在播音樂啊?')
        except (discord.ClientException, AttributeError):
            await ctx.send('我不在語音頻道裡呢?')

    @commands.command(help='繼續播放音樂')
    async def resume(self, ctx: commands.Context):
        voice = self.get_voice(ctx.guild)
        try:
            if voice.is_paused():
                voice.resume()
            else:
                await ctx.send('我沒有暫停中的音樂啊?')
        except (discord.ClientException, AttributeError):
            await ctx.send('我不在語音頻道裡呢?')

    @commands.command(help='停止播放音樂並離開語音頻道')
    async def stop(self, ctx: commands.Context):
        voice = self.get_voice(ctx.guild)
        if not voice:
            await ctx.send('我不在語音頻道裡呢?')
            return

        guild_data = self.get_guild_data(ctx.guild.id)
        async with guild_data.play_lock:
            try:
                guild_data.music_queue.clear()
                guild_data.now_play = None
                guild_data.is_processing = False
                if getattr(guild_data, 'prefetch_task', None):
                    guild_data.prefetch_task.cancel()

                if voice.is_playing() or voice.is_paused():
                    voice.stop()
                await ctx.send('好，我走。')
                await voice.disconnect()
            except discord.ClientException:
                await ctx.send('無法斷開連線')

    @commands.command(aliases=['quit'], help='離開語音頻道')
    async def leave(self, ctx: commands.Context):
        voice = self.get_voice(ctx.guild)
        try:
            if voice.is_playing():
                await ctx.send('我還播音樂呢卿?')
                return
            await ctx.send('好，我走。')
            await voice.disconnect()
        except (discord.ClientException, AttributeError):
            await ctx.send('我不在語音頻道裡呢?')

    @commands.command(aliases=['np', 'now', 'current', 'playing'], help='顯示目前播放的音樂')
    async def now_playing(self, ctx: commands.Context):
        guild_data = self.get_guild_data(ctx.guild.id)
        now_play = guild_data.now_play

        if not now_play:
            await ctx.send('我沒有在播音樂啊？')
            return

        description = f'**[{now_play.title}]({now_play.webpage_url})**\n\n'
        description += f'⏳ `{self.sec_to_hms(now_play.duration)}`\n'
        rpt_display = {'off': '關閉', 'all': '全部循環', 'single': '單曲循環'}.get(
            guild_data.rpt_mode, guild_data.rpt_mode
        )
        description += f'🔂 重複模式：`{rpt_display}`\n'
        description += f'🔊 音量：`{int(guild_data.volume * 100)}%`'

        embed = discord.Embed(title='🎶 正在播放', description=description, color=0x1DB954)

        view = NowPlayingView(cog=self, guild=ctx.guild)
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(aliases=['ls', 'queue'], help='顯示待播清單')
    async def list(self, ctx: commands.Context):
        guild_data = self.get_guild_data(ctx.guild.id)
        music_queue = guild_data.music_queue
        now_play = guild_data.now_play

        now_playing_text = ''
        if now_play:
            now_playing_text = f'**🔊 正在播放：**\n[{now_play.title}]({now_play.webpage_url}) - `{self.sec_to_hms(now_play.duration)}`\n\n'

        if not music_queue:
            embed = discord.Embed(
                title='🎶 待播清單',
                description=now_playing_text + '待播清單沒有任何東西',
                color=0x2F3136,
            )
            await ctx.send(embed=embed)
            return

        view = QueuePaginationView(music_queue, self.sec_to_hms, per_page=10)
        embed = view.generate_embed()
        embed.description = now_playing_text + '**👇 接下來：**\n' + embed.description  # type: ignore
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(aliases=['next'], help='跳過目前播放的音樂')
    async def skip(self, ctx: commands.Context):
        guild_data = self.get_guild_data(ctx.guild.id)
        voice = self.get_voice(ctx.guild)
        if voice is None or not voice.is_playing():
            await ctx.send('目前沒有播放中的音樂。')
            return

        async with guild_data.play_lock:
            if getattr(guild_data, 'prefetch_task', None):
                guild_data.prefetch_task.cancel()

            if guild_data.rpt_mode == 'single':
                guild_data.now_play = None

            voice.stop()
        await ctx.send('已跳過當前的曲目。')

    @commands.command(aliases=['remove', 'rm'], help='移除待播清單中的音樂')
    async def delete(self, ctx: commands.Context, index: Optional[int] = None):
        if index is None:
            await ctx.send('請輸入要移除的歌曲編號')
            return

        music_queue = self.get_guild_data(ctx.guild.id).music_queue
        if index < 1 or index > len(music_queue):
            await ctx.send(f'請輸入有效的編號 (1-{len(music_queue)})')
            return

        song_title = music_queue[index - 1].title
        music_queue.pop(index - 1)
        await ctx.send(f'已從待播清單中移除 `{song_title}`')

    @commands.command(aliases=['cls'])
    async def clear(self, ctx: commands.Context):
        guild_data = self.get_guild_data(ctx.guild.id)
        guild_data.music_queue.clear()
        await ctx.send('已清空待播清單')


async def setup(bot: BotClient):
    await bot.add_cog(Music(bot))
