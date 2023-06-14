import discord
import re
import asyncio
import aiohttp
import tempfile

from io import BytesIO
from discord import Guild, Color, File
from discord.components import Button
from discord.ext import commands
from discord import app_commands
from discord.embeds import Embed
from datetime import datetime
from typing import Optional

from model.issues import Issue
from utils import Cog, send_error, send_success
from utils.utils import hash_color
from utils.enums import PermissionLevel
from utils.modals import IssueModal, EditIssueModal
from utils.services import guild_service
from utils.autocomplete import issues_autocomplete

async def get_discord_file_from_url(url) -> Optional[File]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                file_data = await response.read()
                with tempfile.NamedTemporaryFile(delete=True) as temp_file:
                    temp_file.write(file_data)
                    temp_file.seek(0)
                    file = discord.File(temp_file, filename='file.png')
                return file
            else:
                # Handle the infraction where the URL request fails
                return None

def prepare_issue_embed(issue: Issue) -> Embed:
    """Given an issue object, prepare the appropriate embed for it

    Parameters
    ----------
    issue : Issue
        Issue object from database

    Returns
    -------
    discord.Embed
        The embed we want to send
    """
    embed = discord.Embed(title=issue.name)
    embed.description = issue.content
    embed.timestamp = issue.added_date
    embed.color = Color(issue.color).value or hash_color(issue.name).value

    if issue.image.read() is not None:
        embed.set_image(url="attachment://image.gif" if issue.image.content_type ==
                        "image/gif" else "attachment://image.png")
    embed.set_footer(
        text=f"Submitted by {issue.added_by_tag}")
    return embed


def prepare_issue_view(issue: Issue) -> discord.ui.View:
    if not issue.button_links or issue.button_links is None:
        return discord.utils.MISSING

    view = discord.ui.View()
    for label, link in issue.button_links:
        # regex match emoji in label
        custom_emojis = re.search(
            r'<:\d+>|<:.+?:\d+>|<a:.+:\d+>|[\U00010000-\U0010ffff]', label)
        if custom_emojis is not None:
            emoji = custom_emojis.group(0).strip()
            label = label.replace(emoji, '')
            label = label.strip()
        else:
            emoji = None
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=label,
                url=link,
                emoji=emoji))

    return view

async def refresh_common_issues(guild: Guild) -> None:
    # this function deletes the list message and
    # then resends the updated list.

    channel = guild.get_channel(guild_service.get_guild().channel_common_issues)

    # delete old list message
    if guild_service.get_guild().issues_list_msg is not None:
        for id in guild_service.get_guild().issues_list_msg:
            try: # if someone accidentally deletes something
                msg = await channel.fetch_message(id)
                await msg.delete()
            except:
                pass

    ids = []
    embed = Embed(title="Table of Contents")
    desc = ""
    page = 0

    for i, issue in enumerate(guild_service.get_guild().issues):
        desc += f"{i+1}. [{issue.name}](https://discord.com/channels/{guild.id}/{channel.id}/{issue.message_id})\n"
        if len(desc) > 3072:
            embed.description = desc
            page += 1
            embed.set_footer(text=f"Page {page}")
            msg = await channel.send(embed=embed)
            embed = Embed(title="")
            desc = ""
            ids.append(msg.id)

    if len(desc) > 0:
        embed.description = desc
        page += 1
        embed.set_footer(text=f"Page {page}")
        msg = await channel.send(embed=embed)
        ids.append(msg.id)

    guild_service.edit_issues_list(ids)

async def do_reindex(ctx: discord.Interaction) -> None:
    channel = ctx.guild.get_channel(guild_service.get_guild().channel_common_issues)

    for issue in guild_service.get_guild().issues:
        try:
            msg = await channel.fetch_message(issue.message_id)
            await msg.delete()
        except:
            pass

        _file = issue.image.read()
        if _file is not None:
            _file = discord.File(
                BytesIO(_file),
                filename="image.gif" if issue.image.content_type == "image/gif" else "image.png")
        else:
            _file = discord.utils.MISSING

        msg = await channel.send(file=_file or discord.utils.MISSING, embed=prepare_issue_embed(issue) or discord.utils.MISSING, view=prepare_issue_view(issue) or discord.utils.MISSING)
        issue.message_id = msg.id

        guild_service.edit_issue(issue)

    # refresh common issue list
    await refresh_common_issues(ctx.guild)
    await ctx.followup.send("Reindexed!", ephemeral=True)


async def do_import(ctx: discord.Interaction) -> None:
    # imports embeds from old bot into the new db-based system
    channel = ctx.guild.get_channel(guild_service.get_guild().channel_common_issues)

    async for message in channel.history(limit=None, oldest_first=True):
        if not message.author.bot:
            continue
        if not message.embeds:
            continue

        embed = message.embeds[0]
        if not embed.footer.text:
            continue

        if not embed.footer.text.startswith('Submitted by'):
            continue

        if embed.footer.text.startswith('Submitted by'):
            iss = Issue()
            iss.name = embed.title
            iss.content = embed.description
            iss.added_date = embed.timestamp
            iss.added_by_id = 0
            iss.added_by_tag = ' '.join(embed.footer.text.split(' ')[2:])
            if embed.image.url:
                iss.image = await get_discord_file_from_url(embed.image.url)
            riss = guild_service.get_issue(iss.name)
            iss.button_links = []
            iss.color = embed.color.value

            for ar in message.components:
                for btn in ar.children:
                    if type(btn) is Button:
                        iss.button_links.append((btn.label, btn.url))

            msg = await channel.send(file=iss.image or discord.utils.MISSING, embed=prepare_issue_embed(iss) or discord.utils.MISSING, view=prepare_issue_view(iss) or discord.utils.MISSING)
            iss.message_id = msg.id

            if riss is not None:
                guild_service.edit_issue(iss)
            else:
                guild_service.add_issue(iss)
            await message.delete()
        elif embed.title.startswith('Table of'):
            await message.delete()

    # refresh common issue list
    await refresh_common_issues(ctx.guild)
    await ctx.followup.send("Imported all embeds as common issues!", ephemeral=True)


class Issues(Cog):
    cooldown = commands.CooldownMapping.from_cooldown(1.0, 5.0, commands.BucketType.channel)

    @app_commands.autocomplete(name=issues_autocomplete)
    @app_commands.command()
    async def issue(self, ctx: discord.Interaction, name: str, user_to_mention: discord.Member = None) -> None:
        """Send a common issue

        Args:
            ctx (discord.Interaction): Context
            name (str): Name of the issue
            user_to_mention (discord.Member, optional): User to mention. Defaults to None.
        """

        issue = guild_service.get_issue(name)

        if issue is None:
            raise commands.BadArgument("That issue does not exist.")

        # run cooldown so tag can't be spammed
        bucket = self.cooldown.get_bucket(ctx)
        current = datetime.now().timestamp()
        # ratelimit only if the invoker is not a moderator
        if bucket.update_rate_limit(current) and not PermissionLevel.MOD == ctx.user:
           raise commands.BadArgument("That issue is on cooldown.")

        # if the Issue has an image, add it to the embed
        _file = issue.image.read()
        if _file is not None:
            _file = discord.File(
                BytesIO(_file),
                filename="image.gif" if issue.image.content_type == "image/gif" else "image.png")
        else:
            _file = discord.utils.MISSING

        if user_to_mention is not None:
            title = f"Hey {user_to_mention.mention}, have a look at this!"
        else:
            title = None

        await ctx.response.send_message(content=title, embed=prepare_issue_embed(issue), view=prepare_issue_view(issue), file=_file)


class IssuesGroup(Cog, commands.GroupCog, group_name="commonissue"):
    @PermissionLevel.HELPER
    @app_commands.command()
    async def add(self, ctx: discord.Interaction, name: str, image: discord.Attachment = None, panic_keyword: str = None, color: str = None) -> None:
        """Add a common issue

        Args:
            ctx (discord.Interaction): Context
            name (str): Name of the issue
            image (discord.Attachment, optional): Issue image. Defaults to None.
            panic_keyword (str): The panic keyword for this common issue.
            color (str): The hexadecimal color of the embed.
        """

        if (guild_service.get_issue(name)) is not None:
            raise commands.BadArgument("Issue with that name already exists.")

        content_type = None
        if image is not None:
            content_type = image.content_type
            if content_type not in [
                "image/png",
                "image/jpeg",
                "image/gif",
                    "image/webp"]:
                raise commands.BadArgument("Attached file was not an image!")

            if image.size > 8_000_000:
                raise commands.BadArgument("That image is too big!")

            image = await image.read()

        modal = IssueModal(bot=self.bot, issue_name=name, author=ctx.user)
        await ctx.response.send_modal(modal)
        await modal.wait()

        issue = modal.issue
        if issue is None:
            return

        # did the user want to attach an image to this issue?
        if image is not None:
            issue.image.put(image, content_type=content_type)

        _file = issue.image.read()
        if _file is not None:
            _file = discord.File(
                BytesIO(_file),
                filename="image.gif" if issue.image.content_type == "image/gif" else "image.png")


        # send the issue in #common-issues channel
        ci_channel = guild_service.get_guild().channel_common_issues
        ci_msg = await ctx.guild.get_channel(ci_channel).send(file=_file or discord.utils.MISSING, embed=prepare_issue_embed(issue) or discord.utils.MISSING, view=prepare_issue_view(issue) or discord.utils.MISSING)
        issue.message_id = ci_msg.id
        issue.panic_string = panic_keyword or ''
        issue.color = Color.from_str(color) if color else hash_color(name).value

        # store issue in database
        guild_service.add_issue(issue)

        # refresh common issue list
        await refresh_common_issues(ctx.guild)

        followup = await ctx.followup.send("Added new issue!", file=_file or discord.utils.MISSING, embed=prepare_issue_embed(issue) or discord.utils.MISSING, view=prepare_issue_view(issue) or discord.utils.MISSING)
        await asyncio.sleep(5)
        await followup.delete()

    @PermissionLevel.HELPER
    @app_commands.autocomplete(name=issues_autocomplete)
    @app_commands.command()
    async def edit(self, ctx: discord.Interaction, name: str, image: discord.Attachment = None, panic_keyword: str = None, color: str = None) -> None:
        """Edit a common issue

        Args:
            ctx (discord.Interaction): Context
            name (str): Name of the issue
            image (discord.Attachment, optional): Issue image. Defaults to None.
            panic_keyword (str): The panic keyword for this common issue.
            color (str): The hexadecimal color of the embed.
        """


        issue = guild_service.get_issue(name)
        if issue is None:
            raise commands.BadArgument("That issue does not exist.")

        content_type = None
        if image is not None:
            # ensure the attached file is an image
            content_type = image.content_type
            if image.size > 8_000_000:
                raise commands.BadArgument("That image is too big!")

            image = await image.read()
            # save image bytes
            if issue.image is not None:
                issue.image.replace(image, content_type=content_type)
            else:
                issue.image.put(image, content_type=content_type)
        else:
            issue.image.delete()

        modal = EditIssueModal(issue=issue, author=ctx.user)
        await ctx.response.send_modal(modal)
        await modal.wait()

        if not modal.edited:
            await send_error(ctx, "Issue edit was cancelled.", ephemeral=True)
            return

        issue = modal.issue

        _file = issue.image.read()
        if _file is not None:
            _file = discord.File(
                BytesIO(_file),
                filename="image.gif" if issue.image.content_type == "image/gif" else "image.png")
        issue.panic_string = panic_keyword or ''
        issue.color = Color.from_str(color) if color else hash_color(name).value

        # store issue in database
        guild_service.edit_issue(issue)

        # update the issue in #common-issues channel
        ci_channel = guild_service.get_guild().channel_common_issues
        ci_msg = await ctx.guild.get_channel(ci_channel).fetch_message(issue.message_id)
        await ci_msg.edit(attachments=[_file] if _file else [], embed=prepare_issue_embed(issue) or discord.utils.MISSING, view=prepare_issue_view(issue) or discord.utils.MISSING)

        followup = await ctx.followup.send("Edited issue!", file=_file or discord.utils.MISSING, embed=prepare_issue_embed(issue), view=prepare_issue_view(issue) or discord.utils.MISSING)
        await asyncio.sleep(5)
        await followup.delete()

    @PermissionLevel.HELPER
    @app_commands.autocomplete(name=issues_autocomplete)
    @app_commands.command()
    async def delete(self, ctx: discord.Interaction, name: str) -> None:
        """Delete a common issue

        Args:
            ctx (discord.Interaction): Context
            name (str): Name of the issue
        """

        issue = guild_service.get_issue(name)
        if issue is None:
            raise commands.BadArgument("That issue does not exist.")

        if issue.image is not None:
            issue.image.delete()

        # remove the issue in #common-issues channel
        ci_channel = guild_service.get_guild().channel_common_issues
        ci_msg = await ctx.guild.get_channel(ci_channel).fetch_message(issue.message_id)
        await ci_msg.delete()

        # delete the issue from the database
        guild_service.remove_issue(name)

        # refresh common issue list
        await refresh_common_issues(ctx.guild)

        await send_success(ctx, f"Deleted issue `{issue.name}`.", delete_after=5)

    @PermissionLevel.HELPER
    @app_commands.command()
    async def reindex(self, ctx: discord.Interaction) -> None:
        """Reposts the issues in the common issues channel

        Args:
            ctx (discord.Interaction): Context
        """

        await ctx.response.defer(ephemeral=True, thinking=True)
        ctx.client.loop.create_task(do_reindex(ctx))

    @PermissionLevel.HELPER
    @app_commands.command()
    async def importembeds(self, ctx: discord.Interaction) -> None:
        """Imports all embeds as common issues.

        Args:
            ctx (discord.Interaction): Context
        """

        await ctx.response.defer(ephemeral=True, thinking=True)
        ctx.client.loop.create_task(do_import(ctx))
