from .voicecommands import VoiceCommands

async def setup(bot):
    cog = VoiceCommands(bot)
    await bot.add_cog(cog)