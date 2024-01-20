import aiml
import discord
from redbot.core import commands

class MentionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kernel = aiml.Kernel()
        self.kernel.learn("std-startup.xml")
        self.kernel.respond("load aiml b")

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.bot.user.mentioned_in(message):
            response = self.kernel.respond(message.content)
            await message.channel.send(response)

def setup(bot):
    bot.add_cog(MentionCog(bot))
