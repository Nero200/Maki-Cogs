from .dmlisten import DMListen

async def setup(bot):
    cog = DMListen(bot)
    await bot.add_cog(cog)
