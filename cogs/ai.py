import random

import discord
from discord.ext import commands
from discord.commands import default_permissions
from lib.llm import LLM
from config import llm_model, llm_prompt
import os


class AI(commands.Cog):
    def __init__(self, bot, key: str, model: str) -> None:
        self.bot = bot
        self.LLM = LLM(
            api_key=key,
            model=model
        )
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        
        # Get message history
        history = []
        async for msg in message.channel.history(limit=15):
            if msg.author == self.bot.user:
                continue
            msg_content = msg.content
            for mention in msg.mentions:
                msg_content = msg_content.replace(f'<@{mention.id}>', f'@{mention.name}')
                msg_content = msg_content.replace(f'<@!{mention.id}>', f'@{mention.name}')
            for channel in msg.channel_mentions:
                msg_content = msg_content.replace(f'<#{channel.id}>', f'#{channel.name}')
            history.append(f"{msg.author.name}: {msg_content}")
        
        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            async with message.channel.typing():
                response = self.LLM.generate(chat_history=history, prompt=llm_prompt)
            if response:
                await message.reply(response)
            else:
                return

        # Respond to direct messages
        if isinstance(message.channel, discord.DMChannel):
            history = []
            async for msg in message.channel.history(limit=15):
                if msg.author == self.bot.user:
                    continue
                msg_content = msg.content
                history.append(f"{msg.author.name}: {msg_content}")
            async with message.channel.typing():
                response = self.LLM.generate(chat_history=history, prompt=llm_prompt)
            if response:
                await message.channel.send(response)
            return

def setup(bot):
    model = os.getenv("LLM_MODEL", llm_model)
    key = os.getenv("LLM_KEY")
    bot.add_cog(AI(bot, key, model))
