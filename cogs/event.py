import random
import re

import discord
from discord.ext import commands

from components.core import BotClient, CogBase

dice_re = re.compile(r'^(\d+)d(\d+)$', flags=re.IGNORECASE)


class Event(CogBase):
    def __init__(self, bot: BotClient):
        super().__init__(bot)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 排除機器人本身的訊息
        if message.author.bot:
            return
        
        cmd_prefix = self.bot.command_prefix
        if message.content.startswith(cmd_prefix):
            return

        try:
            # TODO: 加上一依 guild 決定 handler

            await self.handle_common(message)
        except Exception as e:
            self.logger.exception(f'on_message 處理發生例外: {e}')

    async def handle_common(self, message: discord.Message):
        content = message.content.strip()
        channel = message.channel
        author = message.author
        guild = message.guild

        # 隨機 a b c ...
        if re.match(r'^(隨機|rand|random)\b', content, re.IGNORECASE):
            parts = content.split()
            parts_len = len(parts)
            if parts_len <= 2:
                await message.add_reaction('❓')
                await channel.send(f'{author.mention}\n{parts[0]} [ {parts[1]} ]\n### ¿')
                return

            await channel.send(
                f'{author.mention}\n{parts[0]} [ {" ".join(parts[1:])} ] \n→ {parts[random.randint(1, parts_len - 1)]}'
            )
            return

        # 骰子 xdy
        m = dice_re.match(content)
        if m:
            dice_count = int(m.group(1))
            points = int(m.group(2))
            if dice_count <= 0 or dice_count > 10000:
                await channel.send(f'{author.mention}\n{content} :\n不支援零顆以下及一萬顆骰以上')
                return
            rolls = [random.randint(1, points) for _ in range(dice_count)]
            total = sum(rolls)
            if dice_count == 1:
                await channel.send(f'{author.mention}\n{content} :\n## {rolls[0]}')
            elif dice_count > 85:
                await channel.send(
                    f'{author.mention}\n{content} :\n### 共 {total} (數字太多, 僅顯示總和)'
                )
            else:
                await channel.send(
                    f'{author.mention}\n{content} :\n## {", ".join(map(str, rolls))}\n### 共 {total}'
                )
            return


async def setup(bot: BotClient):
    await bot.add_cog(Event(bot))
