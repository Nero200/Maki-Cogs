from .chimeradice import ChimeraDice

async def setup(bot):
    await bot.add_cog(ChimeraDice(bot))