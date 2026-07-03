import discord
import aiohttp
import asyncio
import logging
from typing import Optional
import json
from redbot.core import commands, Config

MAX_CHARS = 1900

# Set up logging matching Red's standards
log = logging.getLogger("red.openlumara.llm")

class Llm(commands.Cog):
    """Talk to your AI over Discord via OpenLumara."""

    def __init__(self, bot, ai_channel):
        self.bot = bot
        self.ai_channel = ai_channel
        
        # Red Configuration Initialization
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        
        default_global = {
            "require_mentions": True,
            "use_message_streaming": False,
            "edit_interval": 1,
            "show_reasoning": False,
            "stream_tool_calls": False,
            "use_replies": False,
            "enable_group_chat": True,
            "startup_message": None,
            "shutdown_message": None,
        }
        self.config.register_global(**default_global)

    async def cog_load(self):
        """Native Red Cog lifecycle hook acting as the old 'on_ready'."""
        self.ai_channel.log("discord", "logged in.")
        startup_message = await self.config.startup_message()
        if startup_message:
            await self.ai_channel.push(startup_message)

    async def cog_unload(self):
        """Native Red Cog lifecycle hook acting as the old 'on_shutdown'."""
        shutdown_message = await self.config.shutdown_message()
        if shutdown_message:
            await self.ai_channel.push(shutdown_message)

    async def _stream_to_discord(self, token_stream, discord_channel):
        """Streams a message to discord in steps."""
        edit_interval = await self.config.edit_interval()
        message_obj = await discord_channel.send("processing your request...")
        edit_lock = asyncio.Lock()

        class StreamState:
            def __init__(self, initial_msg):
                self.message_obj = initial_msg
                self.full_content = ""
                self.pending_content = ""
                self.is_running = True

        state = StreamState(message_obj)

        async def periodic_editor():
            while state.is_running:
                await asyncio.sleep(edit_interval)
                async with edit_lock:
                    if state.pending_content:
                        try:
                            chunk = state.pending_content
                            state.pending_content = ""
                            state.full_content += chunk
                            await state.message_obj.edit(content=state.full_content)
                        except Exception:
                            pass

        editor_task = asyncio.create_task(periodic_editor())

        try:
            async with message_obj.channel.typing():
                async for token in token_stream:
                    if token.get("type") == "new_chunk":
                        async with edit_lock:
                            if state.pending_content:
                                state.full_content += state.pending_content
                                state.pending_content = ""
                                try:
                                    await state.message_obj.edit(content=state.full_content)
                                    self.ai_channel.log(self.ai_channel.name, state.full_content)
                                except:
                                    pass
                            
                            state.message_obj = await discord_channel.send("...")
                            state.full_content = ""
                        continue

                    word = token.get("content")
                    if not word or not isinstance(word, str):
                        continue
                    state.pending_content += word
        finally:
            state.is_running = False
            editor_task.cancel()
            try:
                await editor_task
            except asyncio.CancelledError:
                pass
            
            async with edit_lock:
                if state.pending_content:
                    state.full_content += state.pending_content
                    state.pending_content = ""
                
                if state.full_content:
                    self.ai_channel.log(self.ai_channel.name, state.full_content)
                    try:
                        await state.message_obj.edit(content=state.full_content)
                    except Exception:
                        try:
                            await discord_channel.send(state.full_content)
                        except:
                            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        # Target channel restrictions removed entirely.
        # Authorization maps directly to Guild Administrator permissions.
        commands_authorized = False
        if message.guild and message.author.guild_permissions.administrator:
            commands_authorized = True

        if message.content:
            mentioned = False
            for member in message.mentions:
                if member.id == self.bot.user.id:
                    mentioned = True

            # If replying directly to the bot, inherit explicit conversation engagement
            if message.reference and message.reference.cached_message:
                if message.reference.cached_message.author.id == self.bot.user.id:
                    mentioned = True

            if not await self.config.require_mentions():
                mentioned = True

            if mentioned:
                self.ai_channel.log("discord", f"<{message.author.name}> {message.clean_content}")

                async with message.channel.typing():
                    try:
                        # Clean up raw message strings from mentions
                        content = message.content.strip()
                        for mention in message.raw_mentions:
                            content = content.replace(str(mention), "")
                            content = content.replace("<@>", "")
                            content = content.strip()

                        is_cmd = False
                        cmd_prefix, cmd, args = await self.ai_channel.commands._extract_cmd(content)
                        if cmd:
                            is_cmd = content.lower().strip().startswith(cmd_prefix.lower())

                        if is_cmd:
                            content = f"{cmd_prefix}{' '.join(cmd)}"
                        else:
                            orig_content = str(content)
                            content = ""

                            group_chat = await self.config.enable_group_chat()

                            if message.reference:
                                replied_message = await message.channel.fetch_message(message.reference.message_id)
                                replied_content = replied_message.content or ""
                                replied_message_formatted = "> " + "\n> ".join(replied_content.split("\n"))
                                content += f"in reply to:\n{replied_message_formatted}\n\n"

                            if group_chat:
                                cmd_prefix_temp = str(core.config.get("core", "cmd_prefix", default="/"))
                                author_name = str(message.author.name).lstrip(cmd_prefix_temp)
                                content += f"{author_name} said: {orig_content}"
                            else:
                                content += orig_content

                    except Exception as e:
                        return await message.channel.send(f"error while processing your request: {e}")

                    try:
                        if await self.config.use_message_streaming():
                            response_obj = self.ai_channel.format_stream_for_text(
                                self.ai_channel.send_stream(
                                    {"role": "user", "content": content},
                                    commands_authorized=commands_authorized
                                ),
                                chunk_size=MAX_CHARS
                            )
                            await self._stream_to_discord(response_obj, message.channel)
                        else:
                            response_obj = await self.ai_channel.send(
                                {"role": "user", "content": content}, 
                                commands_authorized=commands_authorized
                            )

                            if response_obj:
                                response_content = response_obj.get("content")
                                chunks = [response_content[i:i + MAX_CHARS] for i in range(0, len(response_content), MAX_CHARS)]

                                for chunk in chunks:
                                    await message.channel.send(
                                        chunk, 
                                        mention_author=await self.config.use_replies()
                                    )
                                    self.ai_channel.log("discord", f"<{message.guild.me.name}> {chunk}")
                                    await asyncio.sleep(0.5)
                    except Exception as e:
                        err_msg = core.detail_error(e) if core.debug else str(e)
                        return await message.channel.send(f"error while sending request to AI: {err_msg}")

    async def on_push(self, message: dict, target_channel_id: int):
        """Faithful reproduction of the framework's external push loop."""
        if not message or message.get("role") != "assistant":
            return None

        content = message.get("content")
        self.ai_channel.log(f"{self.ai_channel.name} push", content)
        chunks = [content[i:i + MAX_CHARS] for i in range(0, len(content), MAX_CHARS)]

        try:
            channel = self.bot.get_channel(target_channel_id) or await self.bot.fetch_channel(target_channel_id)
        except Exception:
            self.ai_channel.log(self.ai_channel.name, f"Error while sending push message: Could not fetch channel context {target_channel_id}")
            return

        if isinstance(channel, discord.TextChannel):
            if channel.permissions_for(channel.guild.me).send_messages:
                for chunk in chunks:
                    await channel.send(chunk)
                    await asyncio.sleep(0.5)
            else:
                self.ai_channel.log(self.ai_channel.name, "Error while sending push message: Discord bot does not have required permissions.")
