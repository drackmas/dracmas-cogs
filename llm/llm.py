import discord
import aiohttp
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    """Stream responses from OpenLumara with proper command passthrough."""

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
    # STREAM TO DISCORD
    # =========================================================

    async def _stream_to_discord(self, stream, channel, trigger_message=None):
        use_replies = self.config.get("use_replies", False)
        edit_interval = self.config.get("edit_interval", 1.0)

        msg = (
            await trigger_message.reply("...", mention_author=False)
            if use_replies and trigger_message
            else await channel.send("...")
        )

        class State:
            def __init__(self, message):
                self.msg = message
                self.buffer = ""
                self.full = ""
                self.running = True

        state = State(msg)
        lock = asyncio.Lock()

        async def editor():
            while state.running:
                await asyncio.sleep(edit_interval)

                async with lock:
                    if not state.buffer:
                        continue

                    state.full += state.buffer
                    state.buffer = ""

                    try:
                        await state.msg.edit(content=state.full)
                    except discord.HTTPException:
                        state.msg = await channel.send(state.full)

        editor_task = asyncio.create_task(editor())

        try:
            async for token in stream:

                # TEXT
                if token.get("type") in (None, "content"):
                    content = token.get("content")
                    if isinstance(content, str):
                        async with lock:
                            state.buffer += content

                # TOOL CALLS (do not break stream)
                elif token.get("type") == "tool_calls":
                    async with lock:
                        state.buffer += "\n[tool call]\n"

                # UNKNOWN
                else:
                    continue

                # Discord overflow protection
                async with lock:
                    if len(state.full) + len(state.buffer) >= MAX_CHARS:
                        state.full += state.buffer
                        state.buffer = ""

                        try:
                            await state.msg.edit(content=state.full)
                        except discord.HTTPException:
                            pass

                        state.msg = await channel.send("...")
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
                    await state.msg.edit(content=state.full)
                except discord.HTTPException:
                    await channel.send(state.full)

    # =========================================================
    # SSE STREAM PARSER (tool-safe)
    # =========================================================

    async def _sse_stream(self, response):
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

                if delta.get("content"):
                    yield {"type": "content", "content": delta["content"]}

                if delta.get("tool_calls"):
                    yield {"type": "tool_calls", "tool_calls": delta["tool_calls"]}

            except json.JSONDecodeError:
                continue

    # =========================================================
    # MESSAGE HANDLER
    # =========================================================

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.config.get("require_mentions"):
            if not self.bot.user.mentioned_in(message):
                return

        # ----------------------------
        # RAW CONTENT (DO NOT STRIP COMMAND MEANING)
        # ----------------------------
        content = message.content.strip()

        if not content:
            return

        # ----------------------------
        # COMMAND EXTRACTION (RESTORED FROM ORIGINAL SYSTEM)
        # ----------------------------
        cmd_prefix = "/"
        cmd = None
        args = None
        is_cmd = False

        try:
            cmd_prefix, cmd, args = await self.ai_channel.commands._extract_cmd(content)

            if cmd:
                is_cmd = content.lower().strip().startswith(cmd_prefix.lower())

        except Exception:
            # if extraction fails, fallback to normal text
            pass

        # ----------------------------
        # PRESERVE COMMAND FORMAT FOR OPENLUMARA
        # ----------------------------
        if is_cmd:
            prompt = f"{cmd_prefix}{' '.join(cmd)}"
        else:
            prompt = content

        # ----------------------------
        # GROUP CHAT CONTEXT (optional)
        # ----------------------------
        if self.config.get("enable_group_chat") and not is_cmd:
            prompt = f"{message.author.name}: {prompt}"

        # ----------------------------
        # SEND TO OPENLUMARA
        # ----------------------------
        async with message.channel.typing():

            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }

            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json=payload) as resp:

                    if resp.status != 200:
                        await message.reply(await resp.text())
                        return

                    stream = self._sse_stream(resp)

                    await self._stream_to_discord(
                        stream,
                        message.channel,
                        trigger_message=message
                    )
