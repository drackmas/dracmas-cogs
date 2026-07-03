import discord
import aiohttp
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.api_url = "http://192.168.8.124:8000/v1/chat/completions"
        self.model_name = "openlumara"

        self.config = {
            "require_mentions": True,
            "use_streaming": True,
            "enable_group_chat": True
        }

        self.sessions = {}  # channel_id -> messages

    # =====================================================
    # SAFE CHUNKING (CRITICAL FIX)
    # =====================================================

    def chunk_text(self, text: str):
        return [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]

    async def safe_send(self, channel, text: str):
        for chunk in self.chunk_text(text):
            await channel.send(chunk)

    async def safe_edit_or_send(self, msg, channel, text: str):
        chunks = self.chunk_text(text)

        try:
            await msg.edit(content=chunks[0])
        except discord.HTTPException:
            await channel.send(chunks[0])

        for chunk in chunks[1:]:
            await channel.send(chunk)

    # =====================================================
    # COMMAND HANDLER
    # =====================================================

    def handle_command(self, channel_id, content):
        lower = content.strip().lower()

        if lower.startswith("/reset"):
            self.sessions[channel_id] = []
            return "reset", None

        if lower.startswith("/new"):
            self.sessions[channel_id] = []
            return "new", None

        if lower.startswith("/compress"):
            if channel_id in self.sessions:
                self.sessions[channel_id] = self.sessions[channel_id][-10:]
            return "compress", None

        return None, content

    # =====================================================
    # SSE STREAM PARSER
    # =====================================================

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

                # IMPORTANT: tool-call safety
                if "tool_calls" in delta:
                    yield {"content": json.dumps(delta["tool_calls"], indent=2)}
                    continue

                if "content" in delta:
                    yield {"content": delta["content"]}

            except:
                continue

    # =====================================================
    # STREAM OUTPUT (FIXED)
    # =====================================================

    async def _stream_to_discord(self, stream, channel):
        msg = await channel.send("...")

        buffer = ""
        full = ""

        async for token in stream:
            text = token.get("content")
            if not isinstance(text, str):
                continue

            buffer += text

            # flush incrementally to avoid memory blowups
            if len(full) + len(buffer) >= MAX_CHARS:
                full += buffer
                buffer = ""

                await self.safe_edit_or_send(msg, channel, full)

                # reset message reference after fallback send
                msg = await channel.send("...")
                full = ""

        full += buffer

        # FINAL SAFE OUTPUT (CRITICAL FIX)
        await self.safe_edit_or_send(msg, channel, full)

    # =====================================================
    # MAIN HANDLER
    # =====================================================

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.config["require_mentions"] and not self.bot.user.mentioned_in(message):
            return

        content = message.content.strip()
        if not content:
            return

        # strip mentions
        for m in message.raw_mentions:
            content = content.replace(f"<@{m}>", "").replace(f"<@!{m}>", "")

        content = content.strip()
        if not content:
            return

        channel_id = message.channel.id

        cmd_type, processed = self.handle_command(channel_id, content)

        if cmd_type in ("reset", "new", "compress"):
            await message.channel.send(f"✔ {cmd_type} executed.")
            return

        prompt = processed

        if channel_id not in self.sessions:
            self.sessions[channel_id] = []

        self.sessions[channel_id].append({
            "role": "user",
            "content": prompt
        })

        messages = self.sessions[channel_id][-20:]

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

                        async def stream():
                            async for t in self._sse_stream(resp):
                                yield t

                        assistant_text = ""

                        async def wrapped():
                            nonlocal assistant_text
                            async for t in stream():
                                assistant_text += t.get("content", "")
                                yield t

                        await self._stream_to_discord(wrapped(), message.channel)

                        self.sessions[channel_id].append({
                            "role": "assistant",
                            "content": assistant_text
                        })

            except Exception as e:
                await message.channel.send(f"Error: {e}")
