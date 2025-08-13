from .makialert import MakiAlert

async def setup(bot):
    cog = MakiAlert(bot)
    await bot.add_cog(cog)