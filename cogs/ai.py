import os

import discord
from discord import app_commands
from google import genai
from google.genai import types

from components.core import BotClient, CogBase


class AI(CogBase):
    def __init__(self, bot: BotClient):
        super().__init__(bot)
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.model_name = 'gemini-3.1-flash-lite'
        else:
            self.logger.warning('未設定AI api key')
            self.client = None

        self.system_prompt = (
            '你是一個整合在 Discord 頻道中的 AI 助手。請務必遵循以下 Discord Markdown 渲染規範來排版你的回答：\n'
            '1. 標題：僅使用 `# 標題`、`## 標題`、`### 標題`（最多到三級標題，且井字號後必須加空格）。\n'
            '2. 粗體與斜體：重要名詞使用 `**粗體**`，需要強調可用 `*斜體*`。\n'
            '3. 程式碼：程式碼區塊務必使用三個反單引號並指定語言，例如 ```python ... ```。行內程式碼使用 `單引號`。\n'
            '4. 列表：使用 `- 項目` 或 `1. 項目` 來製作清單。\n'
            '5. 連結：若有提供網址，請使用 `[顯示文字](網址)` 的格式。\n'
            '6. 限制：絕對不要使用 Discord 無法渲染的標準 Markdown 語法（例如 Markdown 表格、HTML 標籤、超過三級的標題）。若需呈現表格，請改用粗體與換行或程式碼區塊來排版。\n'
            '7. 請直接切入正題回答，不需加入不必要的客套話，也不要回覆任何跟問題無關的內容。'
        )

    def _chunk_text(self, text: str, chunk_size: int = 1900) -> list[str]:
        """將過長的文字切分為符合 Discord 限制的區塊"""
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    @app_commands.command(name='ask', description='向 AI (Gemini) 詢問任何問題')
    @app_commands.describe(prompt='你想問 AI 什麼？')
    async def ask(self, interaction: discord.Interaction, prompt: str):
        if not self.client:
            return await interaction.response.send_message(
                'AI 尚未設定完畢 (缺少 API Key)，請聯絡機器人管理員。', ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        try:
            config = types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.7,
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            answer = response.text

            header = f'**{interaction.message.author.mention}：**\n{prompt}\n\n**AI 回覆：**\n' # type: ignore
            full_reply = header + answer  # type: ignore

            if len(full_reply) <= 2000:
                await interaction.followup.send(full_reply)
            else:
                chunks = self._chunk_text(full_reply)
                await interaction.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)

        except Exception as e:
            self.logger.exception('AI 請求失敗')
            await interaction.followup.send(
                f'發生錯誤，無法取得 AI 回覆: {type(e).__name__}', ephemeral=True
            )


async def setup(bot: BotClient):
    await bot.add_cog(AI(bot))
