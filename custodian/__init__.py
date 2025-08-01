from .custodian import Custodian

async def setup(bot):
    cog = Custodian(bot)
    await bot.add_cog(cog)
    # Consider initializing the weekly reset loop here if needed at load time
    # cog.weekly_reset_task.start() # Start the task loop