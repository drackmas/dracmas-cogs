import discord
import aiohttp
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    """
    Fully self-contained OpenLumara Discord cog.
    No ai_channel dependency.
    Includes local command routing for /reset /new /compress.
    """

    def __init__(self, bot):
        self.bot = bot

        self.api_url = "http://192.168.8.124:8000/v1/chat/completions"
        self.model_name = "openlumara"

        self.config = {
            "require_mentions": True,
            "use_streaming": True,
            "edit_interval": 1.0,
            "enable_group_chat": True
        }

        # -----------------------------
        # SIMPLE LOCAL SESSION SYSTEM
        # -----------------------------
        self.sessions = {}  # channel_id -> list[messages]

    # =========================================================
    # COMMAND HANDLER (REPLACES core.channel.Channel)
    # =========================================================

    def handle_command(self, channel_id, content):
        """
        Returns:
        - ("reset", None)
        - ("new", None)
        - ("compress", messages)
        - (None, normal_content)
        """

        lower = content.strip().lower()

        if lower.startswith("/reset"):
            self.sessions[channel_id] = []
            return "reset", None

        if lower.startswith("/new"):
            self.sessions[channel_id] = []
            return "new", None

        if lower.startswith("/compress"):
            # simple compression: keep last 10 messages
            if channel_id in self.sessions:
                self.sessions[channel_id] = self.sessions[channel_id][-10:]
            return "compress", None

        return None, content

    # =========================================================
    # STREAMING OUTPUT
    # =========================================================

    async def _stream_to_discord(self, stream, channel, trigger_message=None):
        msg = await channel.send("...")

        buffer = ""
        full = ""

        async for token in stream:
            text = token.get("content")
            if not isinstance(text, str):
                continue

            buffer += text

            if len(full) + len(buffer) >= MAX_CHARS:
                full += buffer
                buffer = ""

                try:
                    await msg.edit(content=full)
                except discord.HTTPException:
                    msg = await channel.send(full)
                    full = ""

        full += buffer

        try:
            await msg.edit(content=full)
        except:
            await channel.send(full)

    # =========================================================
    # SSE STREAM PARSER
    # =========================================================

    async def _sse_stream(self, response):
        async for line in response.content:
            line = line.decode("utf-8", errors="ignore").strip()

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
            except:
                continue

    # =========================================================
    # MAIN HANDLER
    # =========================================================

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.config["require_mentions"] and not self.bot.user.mentioned_in(message):
            return

        content = message.content.strip()
        if not content:
            return

        # remove mentions
        for m in message.raw_mentions:
            content = content.replace(f"<@{m}>", "").replace(f"<@!{m}>", "")

        content = content.strip()
        if not content:
            return

        channel_id = message.channel.id

        # =====================================================
        # COMMAND ROUTING (LOCAL)
        # =====================================================
        cmd_type, processed = self.handle_command(channel_id, content)

        # If it's a command that doesn't go to LLM
        if cmd_type in ("reset", "new", "compress"):
            await message.channel.send(f"✔ {cmd_type} executed.")
            return

        prompt = processed

        # =====================================================
        # SESSION MEMORY
        # =====================================================
        if channel_id not in self.sessions:
            self.sessions[channel_id] = []

        self.sessions[channel_id].append({
            "role": "user",
            "content": prompt
        })

        messages = self.sessions[channel_id][-20:]  # context window

        # =====================================================
        # GROUP CHAT
        # =====================================================
        if self.config["enable_group_chat"]:
            messages[-1]["content"] = f"{message.author.display_name}: {prompt}"

        async with message.channel.typing():
            try:
                payload = {
                    "model": self.model_name,
                    "messages": messages,
                    "stream": True
                }

                timeout = aiohttp.ClientTimeout(total=None, sock_read=60)

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.api_url, json=payload) as resp:

                        if resp.status != 200:
                            await message.channel.send(await resp.text())
                            return

                        stream = self._sse_stream(resp)

                        # collect assistant response into memory
                        assistant_text = ""

                        async def wrapped():
                            nonlocal assistant_text
                            async for t in stream:
                                assistant_text += t.get("content", "")
                                yield t

                        await self._stream_to_discord(wrapped(), message.channel)

                        # store assistant reply
                        self.sessions[channel_id].append({
                            "role": "assistant",
                            "content": assistant_text
                        })

            except Exception as e:
                await message.channel.send(f"Error: {e}")
