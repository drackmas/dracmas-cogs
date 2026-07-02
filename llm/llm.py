import discord
import aiohttp
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    """Stable streaming LLM cog with tool-safe SSE handling."""

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

    # =========================================================
    # STREAM TO DISCORD (INSPIRED BY YOUR discord.py REFERENCE)
    # =========================================================

    async def _stream_to_discord(self, token_stream, channel, trigger_message=None):
        use_replies = self.config.get("use_replies", False)
        edit_interval = self.config.get("edit_interval", 1.0)

        if use_replies and trigger_message:
            msg = await trigger_message.reply("...", mention_author=False)
        else:
            msg = await channel.send("...")

        class StreamState:
            def __init__(self, message):
                self.message = message
                self.buffer = ""
                self.full = ""
                self.running = True
                self.last_edit = asyncio.get_event_loop().time()

        state = StreamState(msg)
        lock = asyncio.Lock()

        async def editor_loop():
            while state.running:
                await asyncio.sleep(edit_interval)

                async with lock:
                    if not state.buffer:
                        continue

                    state.full += state.buffer
                    state.buffer = ""

                    try:
                        await state.message.edit(content=state.full)
                        state.last_edit = asyncio.get_event_loop().time()
                    except discord.HTTPException:
                        # fallback: start new message
                        state.message = await channel.send(state.full)

        editor_task = asyncio.create_task(editor_loop())

        try:
            async for token in token_stream:

                # ----------------------------
                # NORMAL TEXT
                # ----------------------------
                if token.get("type") in (None, "content"):
                    content = token.get("content")
                    if isinstance(content, str):
                        async with lock:
                            state.buffer += content

                # ----------------------------
                # TOOL CALLS (DO NOT BREAK STREAM)
                # ----------------------------
                elif token.get("type") == "tool_calls":
                    # Optional: show lightweight trace
                    async with lock:
                        state.buffer += "\n[Tool call executed]\n"

                # ----------------------------
                # UNKNOWN EVENT SAFETY
                # ----------------------------
                else:
                    continue

                # ----------------------------
                # DISCORD LIMIT PROTECTION
                # ----------------------------
                async with lock:
                    if len(state.full) + len(state.buffer) >= MAX_CHARS:
                        state.full += state.buffer
                        state.buffer = ""

                        try:
                            await state.message.edit(content=state.full)
                        except discord.HTTPException:
                            pass

                        state.message = await channel.send("...")
                        state.full = ""

        finally:
            state.running = False
            editor_task.cancel()
            try:
                await editor_task
            except asyncio.CancelledError:
                pass

            async with lock:
                if state.buffer:
                    state.full += state.buffer

                try:
                    await state.message.edit(content=state.full)
                except discord.HTTPException:
                    await channel.send(state.full)

    # =========================================================
    # SSE STREAM PARSER (FIXES TOOL-CALL HANGING ISSUE)
    # =========================================================

    async def _sse_stream(self, response):
        """
        Robust SSE parser that NEVER stalls on tool calls or partial JSON.
        """

        buffer = ""

        async for line in response.content:
            line = line.decode("utf-8", errors="ignore").strip()

            if not line.startswith("data:"):
                continue

            data = line[5:].strip()

            if data == "[DONE]":
                break

            buffer += data

            try:
                obj = json.loads(buffer)
                buffer = ""

                delta = obj["choices"][0].get("delta", {})

                # text
                if delta.get("content"):
                    yield {"type": "content", "content": delta["content"]}

                # tool calls
                if delta.get("tool_calls"):
                    yield {"type": "tool_calls", "tool_calls": delta["tool_calls"]}

            except json.JSONDecodeError:
                # wait for more chunks (CRITICAL FOR TOOL CALLS)
                continue

    # =========================================================
    # DISCORD EVENT
    # =========================================================

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.config.get("require_mentions"):
            if not self.bot.user.mentioned_in(message):
                return

        content = message.content.strip()

        for m in message.raw_mentions:
            content = content.replace(f"<@{m}>", "").replace(f"<@!{m}>", "")

        content = content.strip()
        if not content:
            return

        if self.config.get("enable_group_chat"):
            content = f"{message.author.name}: {content}"

        async with message.channel.typing():

            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": content}],
                "stream": True
            }

            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json=payload) as resp:

                    if resp.status != 200:
                        err = await resp.text()
                        await message.reply(f"API error: {err}")
                        return

                    stream = self._sse_stream(resp)

                    await self._stream_to_discord(
                        stream,
                        message.channel,
                        trigger_message=message
                    )
