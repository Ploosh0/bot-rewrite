import asyncio
import discord
import mongoengine
import traceback
import base64
import hashlib
import re

from discord import app_commands
from discord.ext import commands

from os import getenv
mongoengine.connect(
    'bridget',
    host=getenv("DB_HOST"),
    port=int(
        getenv("DB_PORT")))

from cogs import ChatGPT, Logging, Mod, NativeActionsListeners, Say, Snipe, Sync, Tags, TagsGroup, Unshorten, Timezones, Helper, FiltersGroup, Issues, IssuesGroup, Misc, Memes, MemesGroup, LogParsing, Canister, Xp, Appeals
from utils.startup_checks import checks
from utils.config import cfg
from utils.fetchers import init_client_session
from utils import send_error, send_success

for check in checks:
    check()

bot = commands.Bot(
    command_prefix=cfg.prefix,
    intents=discord.Intents.all(),
    allowed_mentions=discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=True),
)
bot.remove_command("help")

# Apps
# @bot.tree.context_menu(name="Meowcrypt Decrypt")
# async def meowcrypt_decrypt(interaction: discord.Interaction, message: discord.Message) -> None:
#     if "nya>.<" not in message.content:
#         await send_error(interaction, "The selected message is not encrypted by Meowcrypt.")

#     spl = message.content.split(">.<")
#     one = base64.b64decode(spl[1])
#     two = base64.b64decode(spl[2])
#     three = base64.b64decode(spl[3])

#     pass_str = "8f5SCpAbDyCdtPTNBwQpYPJVussZFXVaVWP587ZNgZr3uxKGzRLf4naudDBxmdw5"
#     pass_bytes = pass_str.encode("utf-8")

#     key = hashlib.pbkdf2_hmac('sha512', pass_bytes, one, 50000, dklen=32)

#     cipher = AES.new(key, AES.MODE_GCM, nonce=two)
#     plaintext = cipher.decrypt_and_verify(
#         three[:-16], three[-16:]).decode('utf-8')

#     embed = discord.Embed(
#         title="Decrypted text",
#         description=f"```{plaintext}```",
#         color=discord.Color.green()
#     )
#     embed.set_author(name=message.author, icon_url=message.author.avatar.url)
#     await send_success(interaction, embed=embed, ephemeral=True)


# Cogs
asyncio.run(bot.add_cog(ChatGPT(bot)))
asyncio.run(bot.add_cog(Logging(bot)))
asyncio.run(bot.add_cog(Mod(bot)))
asyncio.run(bot.add_cog(NativeActionsListeners(bot)))
asyncio.run(bot.add_cog(Say(bot)))
asyncio.run(bot.add_cog(Snipe(bot)))
asyncio.run(bot.add_cog(Sync(bot)))
asyncio.run(bot.add_cog(Tags(bot)))
asyncio.run(bot.add_cog(TagsGroup(bot)))
asyncio.run(bot.add_cog(Unshorten(bot)))
asyncio.run(bot.add_cog(Timezones(bot)))
asyncio.run(bot.add_cog(Helper(bot)))
asyncio.run(bot.add_cog(FiltersGroup(bot)))
asyncio.run(bot.add_cog(Issues(bot)))
asyncio.run(bot.add_cog(IssuesGroup(bot)))
asyncio.run(bot.add_cog(Misc(bot)))
asyncio.run(bot.add_cog(Memes(bot)))
asyncio.run(bot.add_cog(MemesGroup(bot)))
asyncio.run(bot.add_cog(LogParsing(bot)))
asyncio.run(bot.add_cog(Canister(bot)))
asyncio.run(bot.add_cog(Xp(bot)))
asyncio.run(bot.add_cog(Appeals(bot)))

@bot.event
async def on_ready() -> None:
    await init_client_session()

# Error handler
@bot.tree.error
async def app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, discord.errors.NotFound):
        await interaction.channel.send(embed=discord.Embed(color=discord.Color.red(), description=f"Sorry {interaction.user.mention}, it looks like I took too long to respond to you! If I didn't do what you wanted in time, please try again."), delete_after=5)
        return

    if (isinstance(error, commands.MissingRequiredArgument)
            or isinstance(error, app_commands.TransformerError)
            or isinstance(error, commands.BadArgument)
            or isinstance(error, commands.BadUnionArgument)
            or isinstance(error, app_commands.MissingPermissions)
            or isinstance(error, app_commands.BotMissingPermissions)
            or isinstance(error, commands.MaxConcurrencyReached)
            or isinstance(error, app_commands.NoPrivateMessage)):
        await send_error(interaction, error)
    else:
        try:
            raise error
        except BaseException:
            tb = traceback.format_exc()
            print(tb)
            if len(tb.split('\n')) > 8:
                tb = '\n'.join(tb.split('\n')[-8:])

            tb_formatted = tb
            if len(tb_formatted) > 1000:
                tb_formatted = "...\n" + tb_formatted[-1000:]

            await send_error(interaction, f"`{error}`\n```{tb_formatted}```")

bot.run(getenv("TOKEN"))
