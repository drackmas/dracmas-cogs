import discord
import aiohttp
import re
from redbot.core import commands

class Llm(commands.Cog):
    """Talk to your local OpenLumara instance via its API Bridge."""

    def __init__(self, bot):
        self.bot = bot
        # Default endpoint configuration pointing to the ApiBridge channel
        self.api_url = "http://0.0.0.0:8000/v1/chat/completions"
        self.model_name = "openlumara" # Or whichever model ID you want to pass

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        # Ignore bots (including itself) and messages not in guilds
        if message.author.bot or not message.guild:
            return

        # Check if the bot was explicitly mentioned
        if not self.bot.user.mentioned_in(message):
            return

        # Verify the mention is an actual ping to the bot user, not a role or everyone tag
        mention_str = self.bot.user.mention
        mention_nick_str = message.guild.me.mention
        
        content = message.content.strip()
        
        if not (content.startswith(mention_str) or content.startswith(mention_nick_str)):
            return

        # Strip out the mention prefix to get the clean user prompt
        clean_prompt = re.sub(r'^<@!?\d+>', '', content).strip()
        
        if not clean_prompt:
            return

        # Trigger typing indicator while waiting for the local API response
        async with message.channel.typing():
            try:
                # Format payload according to the ChatCompletionRequest pydantic model in api_bridge.py
                payload = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "user", "content": clean_prompt}
                    ],
                    "stream": False
                }

                headers = {
                    "Content-Type": "application/json"
                    # If you enable api_key_required, uncomment below:
                    # "Authorization": "Bearer sk-openlumara-dummy-key"
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, json=payload, headers=headers, timeout=60) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Extracting choice back from the standard OpenAI JSON response structure
                            reply = data["choices"][0]["message"]["content"]
                            
                            # Reply directly to the user who pinged it
                            await message.reply(reply, mention_author=False)
                        else:
                            error_text = await response.text()
                            await message.reply(f"⚠️ Error from OpenLumara API ({response.status}): {error_text}", mention_author=False)
            
            except aiohttp.ClientError:
                await message.reply("⚠️ Could not connect to the OpenLumara API Bridge. Is it running on port 8000?", mention_author=False)
            except Exception as e:
                await message.reply(f"⚠️ An unexpected error occurred: {str(e)}", mention_author=False)
