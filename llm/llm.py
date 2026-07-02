import discord
import aiohttp
import re
import asyncio
import json
from redbot.core import commands

MAX_CHARS = 1900

class Llm(commands.Cog):
    """Talk to your local OpenLumara instance via its API Bridge with full features."""

    def __init__(self, bot):
        self.bot = bot
        self.api_url = "http://192.168.8.124:8000/v1/chat/completions"
        self.model_name = "openlumara"

        self.config = {
            "require_mentions": True,
            "use_message_streaming": True,
            "edit_interval": 1.0,
            "use_replies": False,
            "enable_group_chat": True
        }

    async def _stream_to_discord(self, response_stream, discord_channel, use_replies=False, trigger_message=None):
        """Streams or extracts chunks from an incoming stream to Discord in steps."""
        edit_interval = self.config.get("edit_interval", 1.0)
        
        if use_replies and trigger_message:
            message_obj = await trigger_message.reply("processing your request...", mention_author=False)
        else:
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
            async with discord_channel.typing():
                async for token in response_stream:
                    trigger_new_chunk = False
                    
                    if token.get("type") == "new_chunk":
                        trigger_new_chunk = True
                    else:
                        word = token.get("content")
                        if not word or not isinstance(word, str):
                            continue
                        
                        async with edit_lock:
                            current_len = len(state.full_content) + len(state.pending_content)
                            if current_len + len(word) > MAX_CHARS:
                                trigger_new_chunk = True

                    if trigger_new_chunk:
                        async with edit_lock:
                            if state.pending_content:
                                state.full_content += state.pending_content
                                state.pending_content = ""
                                try:
                                    await state.message_obj.edit(content=state.full_content)
                                except Exception:
                                    pass
                        
                        new_msg = await discord_channel.send("...")
                        
                        async with edit_lock:
                            state.message_obj = new_msg
                            state.full_content = ""
                        
                        if token.get("type") == "new_chunk":
                            continue

                    async with edit_lock:
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
                    try:
                        await state.message_obj.edit(content=state.full_content)
                    except Exception:
                        try:
                            if use_replies and trigger_message:
                                await trigger_message.reply(state.full_content, mention_author=False)
                            else:
                                await discord_channel.send(state.full_content)
                        except Exception:
                            pass

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        mentioned = False
        if self.bot.user.mentioned_in(message):
            mention_str = self.bot.user.mention
            mention_nick_str = message.guild.me.mention
            content_strip = message.content.strip()
            if content_strip.startswith(mention_str) or content_strip.startswith(mention_nick_str):
                mentioned = True

        if not self.config.get("require_mentions"):
            mentioned = True

        if not mentioned:
            return

        content = message.content.strip()
        for mention in message.raw_mentions:
            content = content.replace(f"<@!{mention}>", "").replace(f"<@{mention}>", "")
        content = content.replace("<@>", "").strip()

        if content.startswith("/") or content.strip() == "":
            return

        orig_content = str(content)
        content_payload = ""

        try:
            if message.reference:
                try:
                    replied_message = await message.channel.fetch_message(message.reference.message_id)
                    replied_content = replied_message.content or ""
                    replied_message_formatted = "> " + "\n> ".join(replied_content.split("\n"))
                    content_payload += f"in reply to:\n{replied_message_formatted}\n\n"
                except Exception:
                    pass

            if self.config.get("enable_group_chat"):
                author_name = str(message.author.name).lstrip("/")
                content_payload += f"{author_name} said: {orig_content}"
            else:
                content_payload += orig_content

        except Exception as e:
            return await message.channel.send(f"Error while processing context request: {e}")

        async with message.channel.typing():
            try:
                use_stream = self.config.get("use_message_streaming", False)

                payload = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": content_payload}],
                    "stream": use_stream
                }

                headers = {"Content-Type": "application/json"}
                timeout_settings = aiohttp.ClientTimeout(total=None, sock_read=30, connect=10)

                async with aiohttp.ClientSession(timeout=timeout_settings) as session:
                    if not use_stream:
                        async with session.post(self.api_url, json=payload, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                response_content = data["choices"][0]["message"]["content"]
                                chunks = [response_content[i:i + MAX_CHARS] for i in range(0, len(response_content), MAX_CHARS)]

                                for chunk in chunks:
                                    if self.config.get("use_replies"):
                                        await message.reply(chunk, mention_author=False)
                                    else:
                                        await message.channel.send(chunk)
                                    await asyncio.sleep(0.5)
                            else:
                                error_text = await response.text()
                                await message.reply(f"⚠️ Error from OpenLumara API ({response.status}): {error_text}", mention_author=False)
                    else:
                        async with session.post(self.api_url, json=payload, headers=headers) as response:
                            if response.status == 200:
                                
                                async def sse_stream_generator():
                                    async_content = response.content
                                    async for line in async_content:
                                        decoded_line = line.decode('utf-8').strip()
                                        if not decoded_line:
                                            continue
                                            
                                        if decoded_line.startswith("data:"):
                                            data_str = decoded_line[5:].strip()
                                            if data_str == "[DONE]":
                                                break
                                            try:
                                                stream_data = json.loads(data_str)
                                                choices = stream_data.get("choices", [])
                                                if not choices:
                                                    continue
                                                    
                                                choice = choices[0]
                                                delta = choice.get("delta", {})
                                                
                                                if choice.get("finish_reason") == "new_chunk":
                                                    yield {"type": "new_chunk"}
                                                    continue
                                                    
                                                if "content" in delta and delta["content"]:
                                                    yield {"type": "content", "content": delta["content"]}
                                                    
                                            except Exception:
                                                pass

                                await self._stream_to_discord(
                                    sse_stream_generator(), 
                                    message.channel, 
                                    use_replies=self.config.get("use_replies"),
                                    trigger_message=message
                                )
                            else:
                                error_text = await response.text()
                                await message.reply(f"⚠️ Error from OpenLumara API Stream ({response.status}): {error_text}", mention_author=False)

            except aiohttp.ClientError as ce:
                await message.reply(f"⚠️ Connection error to OpenLumara API Bridge: {type(ce).__name__}", mention_author=False)
            except Exception as e:
                await message.reply(f"⚠️ An unexpected error occurred: [{type(e).__name__}] {str(e)}", mention_author=False)
