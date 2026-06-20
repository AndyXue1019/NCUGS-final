import re

import discord
from discord.ext import commands

from components.core import BotClient, CogBase
from components.log import LOG_DIR


class Admin(CogBase):
    def __init__(self, bot: BotClient):
        super().__init__(bot)

    def _valid_extension_name(self, extension: str) -> bool:
        """驗證extension名稱，只允許字母、數字和下劃線"""
        return bool(re.match(r'^[a-zA-Z0-9_]+$', extension))

    # 載入Cog
    @commands.command(hidden=True)
    @commands.is_owner()
    async def load(self, ctx: commands.Context, extension):
        if not self._valid_extension_name(extension):
            await ctx.message.add_reaction('❌')
            await ctx.send('無效的extension名稱，只允許字母、數字和下劃線')
            return
        try:
            await self.bot.load_extension(f'cogs.{extension}')
            await ctx.message.add_reaction('✅')
            await ctx.send(f'載入 {extension} 完成')
            self.logger.info(f'[31m{ctx.author.name}\x1b[0m : 載入 {extension} 完成')
        except Exception as e:
            await ctx.message.add_reaction('❌')
            await ctx.send(f'載入 {extension} 失敗')
            await ctx.send(f'錯誤訊息 : `{e}`')

    # 卸載Cog
    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, extension):
        if not self._valid_extension_name(extension):
            await ctx.message.add_reaction('❌')
            await ctx.send('無效的extension名稱，只允許字母、數字和下劃線')
            return
        try:
            await self.bot.unload_extension(f'cogs.{extension}')
            await ctx.message.add_reaction('✅')
            await ctx.send(f'卸載 {extension} 完成')
            self.logger.info(f'[31m{ctx.author.name}\x1b[0m : 卸載 {extension} 完成')
        except Exception as e:
            await ctx.message.add_reaction('❌')
            await ctx.send(f'卸載 {extension} 失敗')
            await ctx.send(f'錯誤訊息 : `{e}`')

    # 重新載入Cog
    @commands.command(help='重新載入指定Cog', hidden=True)
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, extension):
        if not self._valid_extension_name(extension):
            await ctx.message.add_reaction('❌')
            await ctx.send('無效的extension名稱，只允許字母、數字和下劃線')
            return
        try:
            await self.bot.reload_extension(f'cogs.{extension}')
            if extension == 'slash_cmd':
                await self.bot.tree.sync()
            await ctx.message.add_reaction('✅')
            await ctx.send(f'重新載入 {extension} 完成')
            self.logger.info(f'[31m{ctx.author.name}\x1b[0m : 重新載入 [{extension}] 完成')
        except Exception as e:
            await ctx.message.add_reaction('❌')
            await ctx.send(f'重新載入 {extension} 失敗')
            await ctx.send(f'錯誤訊息 : `{e}`')
            self.logger.info(
                f'[31m{ctx.author.name}\x1b[0m : 重新載入 [{extension}] 失敗，錯誤訊息 : `{e}`'
            )

    # 同步斜線指令
    @commands.command(help='同步斜線指令', hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        try:
            slash_cmds = await self.bot.tree.sync()
            await ctx.message.add_reaction('✅')
            await ctx.send(f'同步{len(slash_cmds)}條斜線指令完成')
            self.logger.info(f'[31m{ctx.author.name}\x1b[0m : 同步{len(slash_cmds)}條斜線指令完成')
        except Exception as e:
            await ctx.message.add_reaction('❌')
            await ctx.send('同步斜線指令失敗')
            await ctx.send(f'錯誤訊息 : `{e}`')
            self.logger.info(f'[31m{ctx.author.name}\x1b[0m : 同步斜線指令失敗，錯誤訊息 : `{e}`')

    # 取得最新log檔案
    @commands.command(help='取得最新log檔案', hidden=True)
    @commands.is_owner()
    async def getlog(self, ctx: commands.Context):
        try:
            log = discord.File(LOG_DIR / 'DCbot.py.log')
            await ctx.reply(file=log, mention_author=False)
        except FileNotFoundError:
            await ctx.send('找不到log檔案')
        except Exception as e:
            await ctx.send(f'發生未知錯誤：{str(e)}')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # 處理權限錯誤
        if isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            return

        raise error


async def setup(bot: BotClient):
    await bot.add_cog(Admin(bot))
