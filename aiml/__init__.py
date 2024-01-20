from .aiml import AIML

def setup(bot):
    bot.add_cog(AIML(bot))
