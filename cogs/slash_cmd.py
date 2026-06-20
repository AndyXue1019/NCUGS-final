import os
import subprocess
from typing import Optional

import discord
from discord import app_commands

from components.core import BotClient, CogBase


class SlashCmd(CogBase):
    def __init__(self, bot: BotClient):
        super().__init__(bot)

    @app_commands.command(
        name='ping', description='檢查機器人的延遲或對指定伺服器進行 Ping'
    )
    async def ping(self, interaction: discord.Interaction, server: Optional[str] = None):
        if server:
            if len(server) > 200:
                return await interaction.response.send_message(
                    '伺服器位址過長，請提供有效的位址。', ephemeral=True
                )

            await interaction.response.defer(thinking=True, ephemeral=True)

            if os.name != 'nt':
                cmd = ['ping', '-c', '4', server]
            else:
                # Windows: ping -n 4 <host>
                cmd = ['ping', '-n', '4', server]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                return await interaction.followup.send(
                    f'Ping {server} 超時。', ephemeral=True
                )
            except Exception as e:
                self.logger.exception('Ping 失敗，發生異常')
                return await interaction.followup.send(
                    f'Ping 失敗:\n```{type(e).__name__}: {e}```', ephemeral=True
                )

            if result.returncode == 0:
                await interaction.followup.send(
                    f'Ping {server} 的結果: \n```{result.stdout}```', ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f'無法 Ping {server}。\n```{result.stderr}```', ephemeral=True
                )
        else:
            await interaction.response.send_message(
                f'Pong!機器人延遲: {round(self.bot.latency * 1000)} ms', ephemeral=True
            )


async def setup(bot: BotClient):
    await bot.add_cog(SlashCmd(bot))
