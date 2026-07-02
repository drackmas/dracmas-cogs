import discord
import aiohttp
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    """Stream responses from OpenLumara (or any OpenAI-compatible API)."""

    def __init__(self, bot):
        self.bot = bot
        self.api_url = "http://192.168.8.124:8000/v1/chat/completions"
        self.model_name = "openlumara"

        self.config = {
            "require_mentions": True,
            "use_streaming": True,
            "edit_interval": 1.0,
            "use_replies": False,
            "enable_group_chat": True
        }

    # ----------------------------
    # STREAM HANDLER
    # ----------------------------

    async def _stream_to_discord(self, stream, channel, trigger_message=None):
        """
        Handles streaming tokens and safely paginates into Discord messages.
        """

        use_replies = self.config.get("use_replies", False)
        edit_interval = self.config.get("edit_interval", 1.0)

        # create initial message
        if use_replies and trigger_message:
            msg = await trigger_message.reply("...", mention_author=False)
        else:
            msg = await channel.send("...")

        buffer = ""
        displayed = ""
        last_edit = asyncio.get_event_loop().time()

        async def safe_edit(force=False):
            nonlocal last_edit, displayed, buffer, msg

            now = asyncio.get_event_loop().time()

            if not force and (now - last_edit) < edit_interval:
                return

            if not buffer:
                return

            displayed += buffer
            buffer = ""

            try:
                await msg.edit(content=displayed)
                last_edit = now
            except discord.HTTPException:
                # If edit fails (rare), fall back to new message
                msg = await channel.send(displayed)

        async for token in stream:
            content = token.get("content")
            if not content:
                continue

            # append token
            buffer += content

            # overflow protection (DISCORD LIMIT)
            if len(displayed) + len(buffer) >= MAX_CHARS:
                await safe_edit(force=True)

                # start new message
                msg = await channel.send("...")
                displayed = ""
                buffer = ""

            # periodic edit
            await safe_edit(force=False)

        # final flush
        if buffer:
            displayed += buffer

        try:
            await msg.edit(content=displayed)
        except discord.HTTPException:
            await channel.send(displayed)

    # ----------------------------
    # MESSAGE LISTENER
    # ----------------------------

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        mentioned = self.bot.user.mentioned_in(message)
        if self.config.get("require_mentions") and not mentioned:
            return

        content = message.content

        # strip mentions
        for m in message.raw_mentions:
            content = content.replace(f"<@{m}>", "").replace(f"<@!{m}>", "")

        content = content.strip()
        if not content:
            return

        # build payload context
        payload_text = content

        if self.config.get("enable_group_chat"):
            payload_text = f"{message.author.name}: {content}"

        async with message.channel.typing():
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": payload_text}],
                "stream": True
            }

            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json=payload) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        await message.reply(f"API error: {err}")
                        return

                    async def stream():
                        async for line in resp.content:
                            line = line.decode("utf-8").strip()
                            if not line.startswith("data:"):
                                continue

                            data = line[5:].strip()
                            if data == "[DONE]":
                                break

                            try:
                                obj = json.loads(data)
                                delta = obj["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield {"content": delta["content"]}
                            except Exception:
                                continue

                    await self._stream_to_discord(
                        stream(),
                        message.channel,
                        trigger_message=message
                    )
