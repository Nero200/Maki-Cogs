from .msgprune import MsgPrune


async def setup(bot):
    await bot.add_cog(MsgPrune(bot))