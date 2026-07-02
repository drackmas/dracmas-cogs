import discord
import asyncio
from redbot.core import commands

MAX_CHARS = 1900


class Llm(commands.Cog):
    """Stream responses through OpenLumara core channel system (correct command routing)."""

    def __init__(self, bot):
        self.bot = bot

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

        task = asyncio.create_task(editor())

        try:
            async for token in stream:
                content = token.get("content")
                if isinstance(content, str):
                    async with lock:
                        state.buffer += content

                # overflow protection
                async with lock:
                    if len(state.full) + len(state.buffer) >= MAX_CHARS:
                        state.full += state.buffer
                        state.buffer = ""

                        try:
                            await state.msg.edit(content=state.full)
                        except:
                            pass

                        state.msg = await channel.send("...")
                        state.full = ""

        finally:
            state.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            async with lock:
                if state.buffer:
                    state.full += state.buffer

                try:
                    await state.msg.edit(content=state.full)
                except:
                    await channel.send(state.full)

    # =========================================================
    # MESSAGE HANDLER
    # =========================================================

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Require mention unless disabled
        if self.config.get("require_mentions"):
            if not self.bot.user.mentioned_in(message):
                return

        content = message.content.strip()
        if not content:
            return

        # remove bot mention text only (DO NOT modify command semantics)
        for m in message.raw_mentions:
            content = content.replace(f"<@{m}>", "").replace(f"<@!{m}>", "")

        content = content.strip()
        if not content:
            return

        # =====================================================
        # ADMIN CHECK (REPLACES authorized_user_id)
        # =====================================================
        commands_authorized = message.author.guild_permissions.administrator

        # =====================================================
        # GROUP CHAT CONTEXT
        # =====================================================
        if self.config.get("enable_group_chat"):
            content = f"{message.author.display_name}: {content}"

        async with message.channel.typing():
            try:
                # =================================================
                # CRITICAL FIX:
                # DO NOT call OpenLumara directly anymore
                # MUST go through ai_channel to preserve commands
                # =================================================

                stream = self.ai_channel.send_stream(
                    {"role": "user", "content": content},
                    commands_authorized=commands_authorized
                )

                formatted_stream = self.ai_channel.format_stream_for_text(
                    stream,
                    chunk_size=MAX_CHARS
                )

                await self._stream_to_discord(
                    formatted_stream,
                    message.channel,
                    trigger_message=message
                )

            except Exception as e:
                await message.channel.send(f"Error: {e}")
