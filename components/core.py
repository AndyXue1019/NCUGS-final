from __future__ import annotations

import os
from dataclasses import dataclass
from logging import Logger  # annotation use
from typing import Any, Optional

import discord
from discord.ext import commands

from components.log import cogs_logger, db_logger
from components.log import main_logger as logger


@dataclass
class BotCore:
    logger_cogs_base: Logger = cogs_logger
    logger_db: Logger = db_logger

    db: Optional[Any] = None


class BotClient(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        self.cmd_prefix = os.getenv('COMMAND_PREFIX', '!')
        super().__init__(command_prefix=self.cmd_prefix, intents=intents)
        self.slash_commands: list = []

        self.core: BotCore = BotCore()

    async def setup_hook(self) -> None:
        try:
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f'Loaded cogs: {filename}')
        except Exception as e:
            logger.info(f'Error loading cogs: {e}')

        self.slash_commands = await self.tree.sync()

    async def on_ready(self) -> None:
        activity = discord.Game(name=f'{self.cmd_prefix}help | {len(self.guilds)} servers')
        status = discord.Status.online
        await self.change_presence(status=status, activity=activity)

        logger.info(f'Logged in as {self.user}')
        logger.info(f'Connected to {len(self.guilds)} servers')
        logger.info(f'Now status: playing {activity.name} ({str(status).upper()})')
        logger.info(f'Commands prefix: {self.cmd_prefix}')
        logger.info(f'Slash commands synced: {len(self.slash_commands)}')


class CogBase(commands.Cog):
    def __init__(self, bot: BotClient):
        self.bot = bot

        core = bot.core
        self.db = core.db
        self.logger = core.logger_cogs_base.getChild(self.qualified_name.lower())
        self.db_logger = core.logger_db.getChild(self.qualified_name.lower())


__all__ = ['BotCore', 'CogBase', 'BotClient']
