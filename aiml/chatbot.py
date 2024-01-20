import aiml
from redbot.core import commands

class chatbot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.aiml_kernel = aiml.Kernel()
        self.aiml_kernel.learn("std-startup.xml")
        self.aiml_kernel.respond("load aiml b")

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.bot.user.mentioned_in(message):
            response = self.aiml_kernel.respond(message.content)
            await message.channel.send(response)

def setup(bot):
    bot.add_cog(chatbot(bot))
