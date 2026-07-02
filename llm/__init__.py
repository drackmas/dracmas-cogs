from .llm import LLM

async def setup(bot):
    await bot.add_cog(LLM(bot))
