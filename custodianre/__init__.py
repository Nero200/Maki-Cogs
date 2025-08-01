from .custodianre import CustodianRefactored

async def setup(bot):
    cog = CustodianRefactored(bot)
    await bot.add_cog(cog)