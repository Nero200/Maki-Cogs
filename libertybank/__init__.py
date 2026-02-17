from .libertybank import LibertyBank

async def setup(bot):
    await bot.add_cog(LibertyBank(bot))
