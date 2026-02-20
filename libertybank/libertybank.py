import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number, pagify

log = logging.getLogger("red.libertybank")


# --- UI Classes ---


class AmountMemoModal(discord.ui.Modal):
    """Modal for deposit, withdraw, partyadd, partytake actions."""

    amount = discord.ui.TextInput(
        label="Amount", placeholder="e.g. 500", required=True, max_length=20,
    )
    memo = discord.ui.TextInput(
        label="Memo", placeholder="Optional note", required=False, max_length=200,
    )

    def __init__(self, cog: "LibertyBank", action: str, guild: discord.Guild, user: discord.Member, view: "DashboardView", title: str):
        super().__init__(title=title)
        self.cog = cog
        self.action = action
        self.guild = guild
        self.user = user
        self.dashboard_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Amount must be a whole number.", ephemeral=True)
            return
        if value <= 0:
            await interaction.response.send_message("Amount must be a positive number.", ephemeral=True)
            return

        memo = self.memo.value or ""
        currency = await self.cog._currency(self.guild)
        await self.cog._ensure_account(self.guild, self.user)
        current = await self.cog._get_balance(self.guild, self.user.id)

        if self.action == "deposit":
            new_bal = current + value
            await self.cog._set_balance(self.guild, self.user.id, new_bal)
            await self.cog._log_transaction(
                self.guild, self.user.id, str(self.user.id), value, new_bal, memo, "deposit",
            )
            await interaction.response.send_message(
                f"{self.user.mention} deposited **{humanize_number(value)}** {currency}.",
            )
            await interaction.followup.send(
                f"New balance: **{humanize_number(new_bal)}** {currency}.",
                ephemeral=True,
            )

        elif self.action == "withdraw":
            if value > current:
                await interaction.response.send_message(
                    f"Insufficient funds. You have **{humanize_number(current)}** {currency}.", ephemeral=True,
                )
                return
            new_bal = current - value
            await self.cog._set_balance(self.guild, self.user.id, new_bal)
            await self.cog._log_transaction(
                self.guild, self.user.id, str(self.user.id), -value, new_bal, memo, "withdraw",
            )
            await interaction.response.send_message(
                f"{self.user.mention} withdrew **{humanize_number(value)}** {currency}.",
            )
            await interaction.followup.send(
                f"New balance: **{humanize_number(new_bal)}** {currency}.",
                ephemeral=True,
            )

        elif self.action == "partyadd":
            if value > current:
                await interaction.response.send_message(
                    f"Insufficient funds. You have **{humanize_number(current)}** {currency}.", ephemeral=True,
                )
                return
            new_personal = current - value
            await self.cog._set_balance(self.guild, self.user.id, new_personal)
            async with self.cog.config.guild(self.guild).party_account() as party:
                party["balance"] += value
                new_party = party["balance"]
            await self.cog._log_transaction(
                self.guild, self.user.id, str(self.user.id), -value, new_personal, memo, "party_deposit",
            )
            await self.cog._log_transaction(
                self.guild, self.user.id, "party", value, new_party, memo, "party_deposit",
            )
            await interaction.response.send_message(
                f"{self.user.mention} added **{humanize_number(value)}** {currency} to party fund.\n"
                f"Party fund: **{humanize_number(new_party)}** {currency}",
            )
            await interaction.followup.send(
                f"Your balance: **{humanize_number(new_personal)}** {currency}",
                ephemeral=True,
            )

        elif self.action == "partytake":
            party_data = await self.cog.config.guild(self.guild).party_account()
            if value > party_data["balance"]:
                await interaction.response.send_message(
                    f"Insufficient party funds. Party has **{humanize_number(party_data['balance'])}** {currency}.",
                    ephemeral=True,
                )
                return
            async with self.cog.config.guild(self.guild).party_account() as party:
                party["balance"] -= value
                new_party = party["balance"]
            new_personal = current + value
            await self.cog._set_balance(self.guild, self.user.id, new_personal)
            await self.cog._log_transaction(
                self.guild, self.user.id, "party", -value, new_party, memo, "party_withdraw",
            )
            await self.cog._log_transaction(
                self.guild, self.user.id, str(self.user.id), value, new_personal, memo, "party_withdraw",
            )
            await interaction.response.send_message(
                f"{self.user.mention} took **{humanize_number(value)}** {currency} from party fund.\n"
                f"Party fund: **{humanize_number(new_party)}** {currency}",
            )
            await interaction.followup.send(
                f"Your balance: **{humanize_number(new_personal)}** {currency}",
                ephemeral=True,
            )

        # Refresh dashboard embed
        embed = await self.dashboard_view._refresh_embed()
        await self.dashboard_view.message.edit(embed=embed, view=self.dashboard_view)


class SendAmountModal(discord.ui.Modal, title="Send Eddies"):
    """Modal for amount + memo after recipient is selected."""

    amount = discord.ui.TextInput(
        label="Amount", placeholder="e.g. 500", required=True, max_length=20,
    )
    memo = discord.ui.TextInput(
        label="Memo", placeholder="Optional note", required=False, max_length=200,
    )

    def __init__(self, cog: "LibertyBank", guild: discord.Guild, user: discord.Member, target: discord.Member, dashboard_view: "DashboardView"):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.user = user
        self.target = target
        self.dashboard_view = dashboard_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Amount must be a whole number.", ephemeral=True)
            return
        if value <= 0:
            await interaction.response.send_message("Amount must be a positive number.", ephemeral=True)
            return

        target = self.target
        memo = self.memo.value or ""
        currency = await self.cog._currency(self.guild)
        await self.cog._ensure_account(self.guild, self.user)
        await self.cog._ensure_account(self.guild, target)
        current = await self.cog._get_balance(self.guild, self.user.id)

        if value > current:
            await interaction.response.send_message(
                f"Insufficient funds. You have **{humanize_number(current)}** {currency}.", ephemeral=True,
            )
            return

        sender_new = current - value
        receiver_bal = await self.cog._get_balance(self.guild, target.id)
        receiver_new = receiver_bal + value

        await self.cog._set_balance(self.guild, self.user.id, sender_new)
        await self.cog._set_balance(self.guild, target.id, receiver_new)

        await self.cog._log_transaction(
            self.guild, self.user.id, str(self.user.id), -value, sender_new, memo, "transfer",
        )
        await self.cog._log_transaction(
            self.guild, self.user.id, str(target.id), value, receiver_new, memo, "transfer",
        )
        await interaction.response.send_message(
            f"{self.user.mention} sent **{humanize_number(value)}** {currency} to {target.mention}.",
        )
        await interaction.followup.send(
            f"Your balance: **{humanize_number(sender_new)}** {currency}",
            ephemeral=True,
        )
        try:
            await target.send(
                f"**{self.user.display_name}** sent you **{humanize_number(value)}** {currency}. "
                f"Your balance: **{humanize_number(receiver_new)}** {currency}"
            )
        except discord.Forbidden:
            pass

        # Refresh dashboard embed
        embed = await self.dashboard_view._refresh_embed()
        await self.dashboard_view.message.edit(embed=embed, view=self.dashboard_view)


class RecipientSelectView(discord.ui.View):
    """Ephemeral dropdown to pick a transfer recipient from existing accounts."""

    def __init__(self, cog: "LibertyBank", user: discord.Member, guild: discord.Guild, dashboard_view: "DashboardView", options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.guild = guild
        self.dashboard_view = dashboard_view
        self.select = discord.ui.Select(placeholder="Choose a recipient...", options=options)
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        target_id = int(self.select.values[0])
        target = self.guild.get_member(target_id)
        if target is None:
            await interaction.response.send_message("That member is no longer in the server.", ephemeral=True)
            return
        modal = SendAmountModal(self.cog, self.guild, self.user, target, self.dashboard_view)
        await interaction.response.send_modal(modal)


class DashboardView(discord.ui.View):
    """Interactive dashboard for LibertyBank."""

    def __init__(self, cog: "LibertyBank", user_id: int, guild: discord.Guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your dashboard.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _refresh_embed(self) -> discord.Embed:
        member = self.guild.get_member(self.user_id)
        balance = await self.cog._get_balance(self.guild, self.user_id) or 0
        party = await self.cog.config.guild(self.guild).party_account()
        currency = await self.cog._currency(self.guild)
        bank = await self.cog._bank_name(self.guild)
        embed = discord.Embed(title=bank, color=discord.Color.gold())
        name = member.display_name if member else "Unknown"
        embed.add_field(name="Your Balance", value=f"{humanize_number(balance)} {currency}", inline=True)
        embed.add_field(name="Party Fund", value=f"{humanize_number(party['balance'])} {currency}", inline=True)
        embed.set_footer(text=f"{name}'s Dashboard")
        return embed

    # Row 1 — Personal
    @discord.ui.button(label="Deposit", style=discord.ButtonStyle.green, row=0)
    async def deposit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AmountMemoModal(self.cog, "deposit", self.guild, interaction.user, self, title="Deposit")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Withdraw", style=discord.ButtonStyle.red, row=0)
    async def withdraw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AmountMemoModal(self.cog, "withdraw", self.guild, interaction.user, self, title="Withdraw")
        await interaction.response.send_modal(modal)

    # Row 2 — Send & Logs
    @discord.ui.button(label="Send", style=discord.ButtonStyle.blurple, row=1)
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        accounts = await self.cog.config.guild(self.guild).accounts()
        options = []
        for uid, data in sorted(accounts.items(), key=lambda x: x[1].get("name", "")):
            if int(uid) == interaction.user.id:
                continue
            member = self.guild.get_member(int(uid))
            name = member.display_name if member else data.get("name", f"User {uid}")
            options.append(discord.SelectOption(label=name, value=uid))
        if not options:
            await interaction.response.send_message("No other accounts to send to.", ephemeral=True)
            return
        view = RecipientSelectView(self.cog, interaction.user, self.guild, self, options)
        await interaction.response.send_message("Who do you want to send to?", view=view, ephemeral=True)

    @discord.ui.button(label="My Log", style=discord.ButtonStyle.grey, row=1)
    async def mylog_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ledger = await self.cog.config.guild(self.guild).ledger()
        uid = str(self.user_id)
        mine = [e for e in ledger if e.get("actor") == uid or e.get("target") == uid]
        recent = mine[-10:]
        currency = await self.cog._currency(self.guild)
        formatted = self.cog._format_ledger(recent, currency, self.guild)
        bank = await self.cog._bank_name(self.guild)
        embed = discord.Embed(title=f"{bank} — Your Transactions", description=formatted, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Party Log", style=discord.ButtonStyle.grey, row=1)
    async def partylog_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ledger = await self.cog.config.guild(self.guild).ledger()
        party_entries = [e for e in ledger if e.get("target") == "party"]
        recent = party_entries[-10:]
        currency = await self.cog._currency(self.guild)
        formatted = self.cog._format_ledger(recent, currency, self.guild)
        bank = await self.cog._bank_name(self.guild)
        embed = discord.Embed(title=f"{bank} — Party Fund Log", description=formatted, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    # Row 3 — Party fund
    @discord.ui.button(label="Party Deposit", style=discord.ButtonStyle.green, row=2)
    async def partyadd_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AmountMemoModal(self.cog, "partyadd", self.guild, interaction.user, self, title="Add to Party Fund")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Party Withdraw", style=discord.ButtonStyle.red, row=2)
    async def partytake_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AmountMemoModal(self.cog, "partytake", self.guild, interaction.user, self, title="Take from Party Fund")
        await interaction.response.send_modal(modal)


class PersistentBankView(discord.ui.View):
    """A persistent single-button view that opens a player's dashboard."""

    def __init__(self, cog: "LibertyBank"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Bank", style=discord.ButtonStyle.blurple, custom_id="libertybank_open_dashboard")
    async def open_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        await self.cog._ensure_account(guild, user)
        view = DashboardView(self.cog, user.id, guild)
        embed = await view._refresh_embed()
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


DEFAULT_GUILD = {
    "currency_name": "eddies",
    "bank_name": "Liberty Bank",
    "manager_role_id": None,
    "accounts": {},
    "party_account": {"balance": 0},
    "ledger": [],
    "bank_panel_message_id": None,
}


class LibertyBank(commands.Cog):
    """TTRPG party fund and character money management."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x4C42414E4B, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)
        self._persistent_view_registered = False

    async def cog_load(self):
        self.bot.add_listener(self._on_ready_register_views, "on_ready")
        if self.bot.is_ready():
            await self._on_ready_register_views()

    async def _on_ready_register_views(self):
        if self._persistent_view_registered:
            return
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            panel_id = guild_data.get("bank_panel_message_id")
            if panel_id:
                view = PersistentBankView(self)
                self.bot.add_view(view, message_id=panel_id)
        self._persistent_view_registered = True

    def cog_unload(self):
        pass

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            uid = str(user_id)
            if uid in guild_data.get("accounts", {}):
                async with self.config.guild_from_id(guild_id).accounts() as accounts:
                    accounts.pop(uid, None)
            # Remove ledger entries where user is actor or target
            ledger = guild_data.get("ledger", [])
            cleaned = [e for e in ledger if e.get("actor") != uid and e.get("target") != uid]
            if len(cleaned) != len(ledger):
                await self.config.guild_from_id(guild_id).ledger.set(cleaned)

    # --- Helpers ---

    async def _is_gm(self, ctx: commands.Context) -> bool:
        if await self.bot.is_owner(ctx.author):
            return True
        manager_role_id = await self.config.guild(ctx.guild).manager_role_id()
        if manager_role_id and ctx.author.get_role(manager_role_id):
            return True
        return False

    async def _ensure_account(self, guild: discord.Guild, member: discord.Member) -> int:
        """Ensure account exists, update display name. Returns current balance."""
        async with self.config.guild(guild).accounts() as accounts:
            uid = str(member.id)
            if uid not in accounts:
                accounts[uid] = {"balance": 0, "name": member.display_name}
                log.info("Created account for %s (%s) in guild %s", member.display_name, member.id, guild.id)
            else:
                accounts[uid]["name"] = member.display_name
            return accounts[uid]["balance"]

    async def _get_balance(self, guild: discord.Guild, user_id: int) -> Optional[int]:
        accounts = await self.config.guild(guild).accounts()
        entry = accounts.get(str(user_id))
        return entry["balance"] if entry else None

    async def _set_balance(self, guild: discord.Guild, user_id: int, amount: int) -> None:
        async with self.config.guild(guild).accounts() as accounts:
            uid = str(user_id)
            if uid in accounts:
                accounts[uid]["balance"] = amount

    async def _log_transaction(
        self, guild: discord.Guild, actor: int, target: str,
        amount: int, balance_after: int, memo: str, tx_type: str,
    ):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": str(actor),
            "target": target,
            "amount": amount,
            "balance_after": balance_after,
            "memo": memo or "",
            "type": tx_type,
        }
        async with self.config.guild(guild).ledger() as ledger:
            ledger.append(entry)

    async def _currency(self, guild: discord.Guild) -> str:
        return await self.config.guild(guild).currency_name()

    async def _bank_name(self, guild: discord.Guild) -> str:
        return await self.config.guild(guild).bank_name()

    def _format_ledger(self, entries: list, currency: str, guild: discord.Guild) -> str:
        if not entries:
            return "No transactions found."
        lines = []
        for e in entries:
            ts = e["timestamp"][:16].replace("T", " ")
            # Resolve names
            actor_id = int(e["actor"])
            actor_member = guild.get_member(actor_id)
            actor_name = actor_member.display_name if actor_member else f"User {e['actor']}"

            if e["target"] == "party":
                target_name = "Party"
            else:
                target_id = int(e["target"])
                target_member = guild.get_member(target_id)
                target_name = target_member.display_name if target_member else f"User {e['target']}"

            if e.get("type") == "set":
                sign = "="
            elif e["amount"] >= 0:
                sign = "+"
            else:
                sign = ""
            amount_str = f"{sign}{humanize_number(e['amount'])}"
            memo = f" - {e['memo']}" if e.get("memo") else ""
            bal = humanize_number(e["balance_after"])
            lines.append(f"`{ts}` **{actor_name}** → {target_name}: {amount_str} {currency} (bal: {bal}){memo}")
        return "\n".join(lines)

    # --- Command Group ---

    @commands.guild_only()
    @commands.group(name="eddies", aliases=["eds", "eddys"], invoke_without_command=True)
    async def eddies(self, ctx: commands.Context):
        """Show your interactive balance dashboard."""
        await self._ensure_account(ctx.guild, ctx.author)
        view = DashboardView(self, ctx.author.id, ctx.guild)
        embed = await view._refresh_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @eddies.command(name="balance")
    async def eddies_balance(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Check a user's balance."""
        target = user or ctx.author
        balance = await self._get_balance(ctx.guild, target.id)
        currency = await self._currency(ctx.guild)
        if balance is None:
            await ctx.send(f"{target.display_name} doesn't have an account yet.")
            return
        try:
            await ctx.author.send(f"**{target.display_name}**: {humanize_number(balance)} {currency}")
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Please enable DMs from server members.")

    @eddies.command(name="party")
    async def eddies_party(self, ctx: commands.Context):
        """Show party fund balance."""
        party = await self.config.guild(ctx.guild).party_account()
        currency = await self._currency(ctx.guild)
        await ctx.send(f"**Party Fund**: {humanize_number(party['balance'])} {currency}")

    @eddies.command(name="deposit", aliases=["add"])
    async def eddies_deposit(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Add to your own account (you earned/found money). Alias: add"""
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, ctx.author)
        current = await self._get_balance(ctx.guild, ctx.author.id)
        new_bal = current + amount
        await self._set_balance(ctx.guild, ctx.author.id, new_bal)
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(ctx.author.id),
            amount, new_bal, memo, "deposit",
        )
        await ctx.send(f"**{ctx.author.display_name}** deposited **{humanize_number(amount)}** {currency}.")
        try:
            await ctx.author.send(f"New balance: **{humanize_number(new_bal)}** {currency}.")
        except discord.Forbidden:
            pass

    @eddies.command(name="withdraw", aliases=["spend"])
    async def eddies_withdraw(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Remove from your own account (you spent money). Alias: spend"""
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, ctx.author)
        current = await self._get_balance(ctx.guild, ctx.author.id)
        if amount > current:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"Insufficient funds. You have **{humanize_number(current)}** {currency}.")
            return
        new_bal = current - amount
        await self._set_balance(ctx.guild, ctx.author.id, new_bal)
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(ctx.author.id),
            -amount, new_bal, memo, "withdraw",
        )
        await ctx.send(f"**{ctx.author.display_name}** withdrew **{humanize_number(amount)}** {currency}.")
        try:
            await ctx.author.send(f"New balance: **{humanize_number(new_bal)}** {currency}.")
        except discord.Forbidden:
            pass

    @eddies.command(name="send")
    async def eddies_send(self, ctx: commands.Context, user: discord.Member, amount: int, *, memo: str = ""):
        """Transfer from your account to another player."""
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        if user.id == ctx.author.id:
            await ctx.send("You can't send money to yourself.")
            return
        if user.bot:
            await ctx.send("You can't send money to a bot.")
            return

        await self._ensure_account(ctx.guild, ctx.author)
        await self._ensure_account(ctx.guild, user)
        current = await self._get_balance(ctx.guild, ctx.author.id)
        if amount > current:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"Insufficient funds. You have **{humanize_number(current)}** {currency}.")
            return

        sender_new = current - amount
        receiver_bal = await self._get_balance(ctx.guild, user.id)
        receiver_new = receiver_bal + amount

        await self._set_balance(ctx.guild, ctx.author.id, sender_new)
        await self._set_balance(ctx.guild, user.id, receiver_new)
        currency = await self._currency(ctx.guild)

        await self._log_transaction(
            ctx.guild, ctx.author.id, str(ctx.author.id),
            -amount, sender_new, memo, "transfer",
        )
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(user.id),
            amount, receiver_new, memo, "transfer",
        )
        await ctx.send(f"**{ctx.author.display_name}** sent **{humanize_number(amount)}** {currency} to **{user.display_name}**.")
        try:
            await ctx.author.send(f"Your balance: **{humanize_number(sender_new)}** {currency}.")
        except discord.Forbidden:
            pass
        try:
            await user.send(
                f"**{ctx.author.display_name}** sent you **{humanize_number(amount)}** {currency}. "
                f"Your balance: **{humanize_number(receiver_new)}** {currency}"
            )
        except discord.Forbidden:
            pass

    @eddies.command(name="partyadd")
    async def eddies_partyadd(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Move money from your account to the party fund."""
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, ctx.author)
        current = await self._get_balance(ctx.guild, ctx.author.id)
        if amount > current:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"Insufficient funds. You have **{humanize_number(current)}** {currency}.")
            return

        new_personal = current - amount
        await self._set_balance(ctx.guild, ctx.author.id, new_personal)

        async with self.config.guild(ctx.guild).party_account() as party:
            party["balance"] += amount
            new_party = party["balance"]

        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(ctx.author.id),
            -amount, new_personal, memo, "party_deposit",
        )
        await self._log_transaction(
            ctx.guild, ctx.author.id, "party",
            amount, new_party, memo, "party_deposit",
        )
        await ctx.send(
            f"Moved **{humanize_number(amount)}** {currency} to party fund.\n"
            f"Your balance: **{humanize_number(new_personal)}** {currency} | "
            f"Party fund: **{humanize_number(new_party)}** {currency}"
        )

    @eddies.command(name="partytake")
    async def eddies_partytake(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Move money from the party fund to your account."""
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, ctx.author)

        party = await self.config.guild(ctx.guild).party_account()
        if amount > party["balance"]:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"Insufficient party funds. Party has **{humanize_number(party['balance'])}** {currency}.")
            return

        async with self.config.guild(ctx.guild).party_account() as party:
            party["balance"] -= amount
            new_party = party["balance"]

        current = await self._get_balance(ctx.guild, ctx.author.id)
        new_personal = current + amount
        await self._set_balance(ctx.guild, ctx.author.id, new_personal)

        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, "party",
            -amount, new_party, memo, "party_withdraw",
        )
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(ctx.author.id),
            amount, new_personal, memo, "party_withdraw",
        )
        await ctx.send(
            f"Took **{humanize_number(amount)}** {currency} from party fund.\n"
            f"Your balance: **{humanize_number(new_personal)}** {currency} | "
            f"Party fund: **{humanize_number(new_party)}** {currency}"
        )

    @eddies.command(name="mylog")
    async def eddies_mylog(self, ctx: commands.Context, number: int = 10):
        """Show your recent transactions."""
        ledger = await self.config.guild(ctx.guild).ledger()
        uid = str(ctx.author.id)
        mine = [e for e in ledger if e.get("actor") == uid or e.get("target") == uid]
        recent = mine[-number:]
        currency = await self._currency(ctx.guild)
        formatted = self._format_ledger(recent, currency, ctx.guild)
        bank = await self._bank_name(ctx.guild)
        for page in pagify(formatted, delims=["\n"], page_length=1900):
            embed = discord.Embed(title=f"{bank} — Your Transactions", description=page, color=discord.Color.blue())
            await ctx.send(embed=embed)

    @eddies.command(name="partylog")
    async def eddies_partylog(self, ctx: commands.Context, number: int = 10):
        """Show recent party fund transactions."""
        ledger = await self.config.guild(ctx.guild).ledger()
        party_entries = [e for e in ledger if e.get("target") == "party"]
        recent = party_entries[-number:]
        currency = await self._currency(ctx.guild)
        formatted = self._format_ledger(recent, currency, ctx.guild)
        bank = await self._bank_name(ctx.guild)
        for page in pagify(formatted, delims=["\n"], page_length=1900):
            embed = discord.Embed(title=f"{bank} — Party Fund Log", description=page, color=discord.Color.blue())
            await ctx.send(embed=embed)

    @eddies.command(name="log")
    async def eddies_log(self, ctx: commands.Context, number: int = 10):
        """Show all recent transactions. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        ledger = await self.config.guild(ctx.guild).ledger()
        currency = await self._currency(ctx.guild)
        recent = ledger[-number:]
        formatted = self._format_ledger(recent, currency, ctx.guild)
        bank = await self._bank_name(ctx.guild)
        try:
            for page in pagify(formatted, delims=["\n"], page_length=1900):
                embed = discord.Embed(title=f"{bank} — Transaction Log", description=page, color=discord.Color.blue())
                await ctx.author.send(embed=embed)
            await ctx.send("Transaction log sent to your DMs.")
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Please enable DMs from server members.")

    # --- GM / Manager Commands ---

    @eddies.command(name="set")
    async def eddies_set(self, ctx: commands.Context, user: discord.Member, amount: int, *, memo: str = ""):
        """Set a player's balance to an exact amount. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount < 0:
            await ctx.send("Balance cannot be negative.")
            return
        await self._ensure_account(ctx.guild, user)
        await self._set_balance(ctx.guild, user.id, amount)
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(user.id),
            amount, amount, memo, "set",
        )
        await ctx.send(f"Set **{user.display_name}**'s balance to **{humanize_number(amount)}** {currency}.")

    @eddies.command(name="setparty")
    async def eddies_setparty(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Set party fund to an exact amount. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount < 0:
            await ctx.send("Balance cannot be negative.")
            return
        async with self.config.guild(ctx.guild).party_account() as party:
            party["balance"] = amount
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, "party",
            amount, amount, memo, "set",
        )
        await ctx.send(f"Set party fund to **{humanize_number(amount)}** {currency}.")

    @eddies.command(name="give")
    async def eddies_give(self, ctx: commands.Context, user: discord.Member, amount: int, *, memo: str = ""):
        """Add to a player's balance (no source deduction). (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, user)
        current = await self._get_balance(ctx.guild, user.id)
        new_bal = current + amount
        await self._set_balance(ctx.guild, user.id, new_bal)
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(user.id),
            amount, new_bal, memo, "deposit",
        )
        await ctx.send(f"Gave **{humanize_number(amount)}** {currency} to **{user.display_name}**. New balance: **{humanize_number(new_bal)}** {currency}.")

    @eddies.command(name="take")
    async def eddies_take(self, ctx: commands.Context, user: discord.Member, amount: int, *, memo: str = ""):
        """Remove from a player's balance. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        await self._ensure_account(ctx.guild, user)
        current = await self._get_balance(ctx.guild, user.id)
        if amount > current:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"**{user.display_name}** only has **{humanize_number(current)}** {currency}.")
            return
        new_bal = current - amount
        await self._set_balance(ctx.guild, user.id, new_bal)
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, str(user.id),
            -amount, new_bal, memo, "withdraw",
        )
        await ctx.send(f"Took **{humanize_number(amount)}** {currency} from **{user.display_name}**. New balance: **{humanize_number(new_bal)}** {currency}.")

    @eddies.command(name="giveparty")
    async def eddies_giveparty(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Add to party fund (no source deduction). (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        async with self.config.guild(ctx.guild).party_account() as party:
            party["balance"] += amount
            new_bal = party["balance"]
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, "party",
            amount, new_bal, memo, "party_deposit",
        )
        await ctx.send(f"Added **{humanize_number(amount)}** {currency} to party fund. Party balance: **{humanize_number(new_bal)}** {currency}.")

    @eddies.command(name="takeparty")
    async def eddies_takeparty(self, ctx: commands.Context, amount: int, *, memo: str = ""):
        """Remove from party fund. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
        party = await self.config.guild(ctx.guild).party_account()
        if amount > party["balance"]:
            currency = await self._currency(ctx.guild)
            await ctx.send(f"Party fund only has **{humanize_number(party['balance'])}** {currency}.")
            return
        async with self.config.guild(ctx.guild).party_account() as party:
            party["balance"] -= amount
            new_bal = party["balance"]
        currency = await self._currency(ctx.guild)
        await self._log_transaction(
            ctx.guild, ctx.author.id, "party",
            -amount, new_bal, memo, "party_withdraw",
        )
        await ctx.send(f"Took **{humanize_number(amount)}** {currency} from party fund. Party balance: **{humanize_number(new_bal)}** {currency}.")

    @eddies.command(name="balances")
    async def eddies_balances(self, ctx: commands.Context):
        """Show all player balances and party fund. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        accounts = await self.config.guild(ctx.guild).accounts()
        party = await self.config.guild(ctx.guild).party_account()
        currency = await self._currency(ctx.guild)
        bank = await self._bank_name(ctx.guild)

        lines = []
        for uid, data in sorted(accounts.items(), key=lambda x: x[1].get("name", "")):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else data.get("name", f"User {uid}")
            lines.append(f"**{name}**: {humanize_number(data['balance'])} {currency}")
        lines.append(f"\n**Party Fund**: {humanize_number(party['balance'])} {currency}")

        embed = discord.Embed(
            title=f"{bank} — All Balances",
            description="\n".join(lines) if lines else "No accounts.",
            color=discord.Color.gold(),
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("Balances sent to your DMs.")
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Please enable DMs from server members.")

    @eddies.command(name="removeaccount")
    async def eddies_removeaccount(self, ctx: commands.Context, user: discord.Member):
        """Remove a player's account from the bank. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        async with self.config.guild(ctx.guild).accounts() as accounts:
            uid = str(user.id)
            if uid not in accounts:
                await ctx.send(f"**{user.display_name}** doesn't have an account.")
                return
            del accounts[uid]
        await ctx.send(f"Removed **{user.display_name}**'s account.")

    @eddies.command(name="clearlog")
    async def eddies_clearlog(self, ctx: commands.Context):
        """Clear the entire transaction log. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        await self.config.guild(ctx.guild).ledger.set([])
        await ctx.send("Transaction log cleared.")

    @eddies.command(name="panel")
    async def eddies_panel(self, ctx: commands.Context):
        """Post a persistent Bank button in this channel. (GM only)"""
        if not await self._is_gm(ctx):
            await ctx.send("You don't have permission to do that.")
            return
        # Remove old panel message if it exists
        old_id = await self.config.guild(ctx.guild).bank_panel_message_id()
        if old_id:
            try:
                old_msg = await ctx.channel.fetch_message(old_id)
                await old_msg.delete()
            except discord.HTTPException:
                pass
        bank = await self._bank_name(ctx.guild)
        currency = await self._currency(ctx.guild)
        embed = discord.Embed(
            title=bank,
            description="Please enter the bank below.",
            color=discord.Color.gold(),
        )
        view = PersistentBankView(self)
        msg = await ctx.send(embed=embed, view=view)
        await self.config.guild(ctx.guild).bank_panel_message_id.set(msg.id)

    @eddies.command(name="setmanager")
    async def eddies_setmanager(self, ctx: commands.Context, role: discord.Role):
        """Set the manager role. (GM only)"""
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("Only the bot owner can set the manager role.")
            return
        await self.config.guild(ctx.guild).manager_role_id.set(role.id)
        await ctx.send(f"Manager role set to **{role.name}**.")

    @eddies.command(name="clearmanager")
    async def eddies_clearmanager(self, ctx: commands.Context):
        """Remove the manager role. (GM only)"""
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("Only the bot owner can clear the manager role.")
            return
        await self.config.guild(ctx.guild).manager_role_id.set(None)
        await ctx.send("Manager role cleared.")

    @eddies.command(name="reset")
    async def eddies_reset(self, ctx: commands.Context):
        """Wipe ALL bank data for this server. (Owner only)"""
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("Only the bot owner can reset all bank data.")
            return
        await ctx.send("This will **permanently delete** all accounts, balances, the party fund, and the transaction log. Type **Yes Maki** to confirm.")

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("Reset cancelled (timed out).")
            return

        if reply.content.strip() != "Yes Maki":
            await ctx.send("Reset cancelled.")
            return

        await self.config.guild(ctx.guild).accounts.set({})
        await self.config.guild(ctx.guild).party_account.set({"balance": 0})
        await self.config.guild(ctx.guild).ledger.set([])
        await ctx.send("All bank data has been wiped.")
