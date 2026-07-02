from .llm import Llm

async def setup(bot):
    await bot.add_cog(Llm(bot))
