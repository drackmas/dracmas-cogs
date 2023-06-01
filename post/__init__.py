from .post import Post


async def setup(bot):
    await bot.add_cog(Post(bot))
