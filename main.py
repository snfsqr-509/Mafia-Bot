import asyncio
import os
import re
from pathlib import Path

import discord
from discord import app_commands

GUILD = discord.Object(id=int(os.environ["DISCORD_GUILD_ID"]))
GANG = "المافيا الروسية"
RANKS = ("مستجد", "عضو", "مسؤول", "نائب", "زعيم")
ROLE_NAMES = {rank: f"{rank} | {GANG}" for rank in RANKS}
ROOM_NAMES = {
    "التقديم": "الـتـقـديـم⠀•⠀Mafia",
    "الترحيب": "الـتـرحـيـب⠀•⠀Mafia",
    "الحضور": "الـحـضـور⠀•⠀Mafia",
    "القوانين": "الـقـوانـيـن⠀•⠀Mafia",
    "الإعلانات": "الإعـلانـات⠀•⠀Mafia",
    "الدردشة": "الـدردشـة⠀•⠀Mafia",
    "الاجتماعات": "الاجـتـمـاعـات⠀•⠀Mafia",
    "الطلبات": "الـطـلـبـات⠀•⠀Mafia",
    "الصوت": "الـصـوت • Mafia",
}
LOCK = asyncio.Lock()
NO_PINGS = discord.AllowedMentions.none()


def role(guild, rank):
    return discord.utils.get(guild.roles, name=ROLE_NAMES[rank])


def category(guild):
    return max((group for group in guild.categories if group.name == GANG), key=lambda group: group.id, default=None)


def find_room(channels, key):
    name = ROOM_NAMES[key]
    # Discord can lowercase text channel names.
    return next((channel for channel in channels if channel.name.casefold() == name.casefold()), None) or discord.utils.get(channels, name=key)


def review_channel(guild):
    group = category(guild)
    return find_room(group.text_channels, "الطلبات") if group else None


class Application(discord.ui.Modal, title="تقديم المافيا الروسية"):
    character = discord.ui.TextInput(label="اسم شخصيتك داخل المدينة", max_length=80)
    story = discord.ui.TextInput(label="قصة شخصيتك وخبرتك في الرول بلاي", style=discord.TextStyle.paragraph, max_length=800)
    reason = discord.ui.TextInput(label="ليش تبي تنضم وش بتضيف للفريق؟", style=discord.TextStyle.paragraph, max_length=800)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = review_channel(interaction.guild)
        if not channel:
            await interaction.followup.send("روم المراجعة يحتاج إعداد من الإدارة.")
            return
        card = discord.Embed(title="📩 طلب انضمام للمافيا الروسية", color=0x9E172A)
        card.description = f"المتقدم <@{interaction.user.id}>"
        for field in (self.character, self.story, self.reason):
            card.add_field(name=field.label, value=field.value.strip() or "—", inline=False)
        card.set_footer(text=f"rc:pending:{interaction.user.id}")
        try:
            await channel.send(embed=card, view=Review(), allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            await interaction.followup.send("تعذر إرسال الطلب. تواصل مع الإدارة.")
            return
        await interaction.followup.send("✅ وصل طلبك للقيادة.")


class Apply(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تقديم المافيا الروسية", emoji="📩", custom_id="rc:apply", style=discord.ButtonStyle.danger)
    async def apply(self, interaction, button):
        if any(r.name in ROLE_NAMES.values() for r in interaction.user.roles):
            await interaction.response.send_message("أنت عضو في المافيا بالفعل.", ephemeral=True)
            return
        await interaction.response.send_modal(Application())


class Review(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def decide(self, interaction, accept):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        leader = any(r.name in (ROLE_NAMES["نائب"], ROLE_NAMES["زعيم"]) for r in interaction.user.roles)
        if not (leader or interaction.user.guild_permissions.administrator):
            await interaction.followup.send("المراجعة للقيادة فقط.")
            return
        if interaction.channel != review_channel(guild):
            await interaction.followup.send("راجع الطلب من روم الطلبات.")
            return
        async with LOCK:
            try:
                message = await interaction.channel.fetch_message(interaction.message.id)
                card = message.embeds[0]
                match = re.fullmatch(r"rc:pending:(\d+)", card.footer.text or "")
                if not match:
                    await interaction.followup.send("تمت مراجعة الطلب مسبقًا.")
                    return
                if accept:
                    member = await guild.fetch_member(int(match[1]))
                    recruit = role(guild, "مستجد")
                    if recruit is None or not recruit.is_assignable():
                        await interaction.followup.send("تأكد أن رتبة البوت فوق رتبة المستجد.")
                        return
                    if not any(r.name in ROLE_NAMES.values() for r in member.roles):
                        await member.add_roles(recruit, reason="Respect City application")
                result = "✅ مقبول" if accept else "❌ مرفوض"
                card.set_footer(text=f"{result} • المراجع {interaction.user.id}")
                await message.edit(embed=card, view=None)
            except discord.HTTPException:
                await interaction.followup.send("تعذرت المراجعة. تأكد من صلاحيات البوت ووجود المتقدم في السيرفر.")
                return
        await interaction.followup.send(result)

    @discord.ui.button(label="قبول", custom_id="rc:accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        await self.decide(interaction, True)

    @discord.ui.button(label="رفض", custom_id="rc:reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        await self.decide(interaction, False)


class City(discord.Client):
    async def setup_hook(self):
        self.add_view(Apply())
        self.add_view(Review())
        self.add_view(Duty())
        await tree.sync(guild=GUILD)


intents = discord.Intents.default()
intents.members = True
client = City(intents=intents, allowed_mentions=NO_PINGS)
tree = app_commands.CommandTree(client)


@tree.command(name="setup-mafia", description="استبدال كل رومات السيرفر برومات المافيا الروسية", guild=GUILD)
@app_commands.describe(confirm="اكتب حذف كل الرومات لتأكيد الحذف النهائي")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.default_permissions(administrator=True)
async def setup_mafia(interaction: discord.Interaction, confirm: str = ""):
    if confirm.strip() != "حذف كل الرومات":
        await interaction.response.send_message(
            "هذا الأمر يحذف كل الرومات القديمة ورسائلها نهائيًا. "
            "للمتابعة اكتب حذف كل الرومات في خانة confirm.",
            ephemeral=True,
        )
        return
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("حذف كل الرومات متاح لمالك السيرفر فقط.", ephemeral=True)
        return
    if LOCK.locked():
        await interaction.response.send_message("انتظر انتهاء العملية الحالية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    async with LOCK:
        try:
            old_channels = await guild.fetch_channels()
            ranks = {}
            for rank in RANKS:
                ranks[rank] = role(guild, rank) or await guild.create_role(
                    name=ROLE_NAMES[rank], colour=discord.Colour(0x9E172A)
                )
            group = await guild.create_category(GANG)
            everyone = guild.default_role
            bot = guild.me
            private = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                bot: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            public = {
                **private,
                everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
            }
            members = {**private, **{r: discord.PermissionOverwrite(view_channel=True) for r in ranks.values()}}
            leaders = {**private, **{ranks[k]: discord.PermissionOverwrite(view_channel=True) for k in ("نائب", "زعيم")}}
            rooms = {}
            for name, permissions in (
                ("التقديم", public), ("القوانين", public), ("الترحيب", public), ("الإعلانات", members),
                ("الدردشة", members), ("الاجتماعات", leaders), ("الطلبات", leaders),
            ):
                rooms[name] = await guild.create_text_channel(
                    ROOM_NAMES[name], category=group, overwrites=permissions
                )
            await guild.create_voice_channel(ROOM_NAMES["الصوت"], category=group, overwrites=members)
            panel = rooms["التقديم"]
            card = discord.Embed(
                title="🐺 تقديم المافيا الروسية",
                description=(
                    "🌃 **أول عصابة في ريسبكت سيتي**\n\n"
                    "🎭 عندك شخصية بقصة مميزة وتعرف تلعب مع فريق؟ قدّم للمافيا الروسية.\n\n"
                    "📋 **قبل التقديم**\n"
                    "📖 التزم بقوانين المدينة وحافظ على شخصيتك داخل السيناريو.\n"
                    "🤝 احترم اللاعبين حتى لو بينكم عداوة داخل القصة.\n"
                    "🎙️ تواصل مع الفريق وقت الاجتماعات والسيناريوهات.\n\n"
                    "📩 اضغط الزر وعرّفنا بشخصيتك، خبرتك، وليش تبي تنضم. "
                    "القيادة بتراجع طلبك، وإذا انقبلت تبدأ برتبة **مستجد**."
                ),
                color=0x9E172A,
            )
            card.set_footer(text="rc:panel")
            card.set_image(url="attachment://banner.png")
            await panel.send(embed=card, file=discord.File(Path(__file__).with_name("banner.png")), view=Apply())
        except (discord.HTTPException, OSError):
            await interaction.followup.send("تعذر تجهيز الرومات الجديدة. لم يبدأ حذف الرومات القديمة.")
            return

        failed = []
        for channel in sorted(old_channels, key=lambda channel: isinstance(channel, discord.CategoryChannel)):
            try:
                await channel.delete(reason=f"Respect City reset confirmed by owner {interaction.user.id}")
            except discord.NotFound:
                continue
            except discord.HTTPException:
                failed.append(channel.id)

    result = f"جهزت الرتب والرومات الجديدة ولوحة {panel.mention}."
    if failed:
        result += f" تعذر حذف {len(failed)} من الرومات أو الكاتيجوريات القديمة."
    else:
        result += " تم حذف كل الرومات والكاتيجوريات القديمة."
    await interaction.followup.send(result)


@setup_mafia.error
async def setup_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("الأمر للإدارة فقط.", ephemeral=True)
        return
    raise error


class RulesForm(discord.ui.Modal, title="قوانين المافيا الروسية"):
    rules = discord.ui.TextInput(
        label="اكتب القوانين هنا",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        placeholder="اكتب كل قانون في سطر مستقل",
    )

    async def on_submit(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("النشر للإدارة فقط.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        group = category(interaction.guild)
        channel = find_room(group.text_channels, "القوانين") if group else None
        if channel is None:
            await interaction.followup.send("شغّل /setup-mafia أول.")
            return
        rules = self.rules.value.strip()
        if not rules:
            await interaction.followup.send("اكتب قانونًا واحدًا على الأقل.")
            return
        card = discord.Embed(title="قوانين المافيا الروسية", description=rules, color=0x9E172A)
        card.set_image(url="attachment://banner.png")
        try:
            await channel.send(embed=card, file=discord.File(Path(__file__).with_name("banner.png")))
        except discord.HTTPException:
            await interaction.followup.send("تعذر النشر. تأكد من صلاحيات الإرسال والإيمبد وإرفاق الملفات.")
            return
        await interaction.followup.send(f"تم نشر القوانين في {channel.mention}.")


@tree.command(name="mafia-rules", description="كتابة ونشر قوانين المافيا الروسية", guild=GUILD)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.default_permissions(administrator=True)
async def mafia_rules(interaction: discord.Interaction):
    await interaction.response.send_modal(RulesForm())


mafia_rules.error(setup_error)


DUTY_ROLES = {True: "✓ مسجل الدخول", False: "✕ مسجل خروج"}


def gang_room(guild, key):
    group = category(guild)
    return find_room(group.text_channels, key) if group else None


def attachment(name):
    return discord.File(Path(__file__).with_name(name))


def mafia_card(title, description):
    card = discord.Embed(title=title, description=description, color=0x9E172A)
    card.set_image(url="attachment://banner.png")
    return card


async def welcome(member, channel, rules):
    card = mafia_card(
        "حيّاك في ريسبكت سيتي",
        f"يا هلا {member.mention}، نورت مقر المافيا الروسية!\n\n"
        f"قبل ما تبدأ رحلتك، مر على {rules.mention} واقرأ القوانين. "
        "إذا حاب تنضم للعصابة، توجّه لروم التقديم وعرّفنا بشخصيتك.",
    )
    await channel.send(
        content=member.mention,
        embed=card,
        file=attachment("banner.png"),
        allowed_mentions=discord.AllowedMentions(users=[member]),
    )


@client.event
async def on_member_join(member):
    if member.bot or member.guild.id != GUILD.id:
        return
    channel = gang_room(member.guild, "الترحيب")
    rules = gang_room(member.guild, "القوانين")
    if channel and rules:
        await welcome(member, channel, rules)


@tree.command(name="mafia-welcome", description="تجهيز روم الترحيب وإرسال تجربة", guild=GUILD)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def mafia_welcome(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    group = category(guild)
    rules = gang_room(guild, "القوانين")
    if not group or not rules:
        await interaction.followup.send("ما لقيت كاتيجوري المافيا وروم القوانين بالأسماء المعتمدة.")
        return
    try:
        channel = gang_room(guild, "الترحيب") or await guild.create_text_channel(
            ROOM_NAMES["الترحيب"], category=group, overwrites=rules.overwrites
        )
        await welcome(interaction.user, channel, rules)
    except discord.HTTPException:
        await interaction.followup.send("تعذر تجهيز الترحيب. تأكد من صلاحيات القنوات والإرسال والإرفاق.")
        return
    await interaction.followup.send(f"الترحيب جاهز في {channel.mention}.")


class Duty(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def set_status(self, interaction, active):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        icon = "check.png" if active else "cross.png"
        async with LOCK:
            try:
                member = await guild.fetch_member(interaction.user.id)
                if not any(r.name in ROLE_NAMES.values() for r in member.roles):
                    await interaction.followup.send("تسجيل الحضور لأعضاء المافيا.")
                    return
                chosen = discord.utils.get(guild.roles, name=DUTY_ROLES[active])
                other = discord.utils.get(guild.roles, name=DUTY_ROLES[not active])
                if not chosen or not other or not chosen.is_assignable() or not other.is_assignable():
                    await interaction.followup.send("تأكد أن رتبة البوت فوق رتبتي الحضور.")
                    return
                await member.add_roles(chosen, reason="Mafia duty status")
                if other in member.roles:
                    try:
                        await member.remove_roles(other, reason="Mafia duty status")
                    except discord.HTTPException:
                        if chosen not in member.roles:
                            await member.remove_roles(chosen, reason="Rollback duty status")
                        raise
            except discord.HTTPException:
                await interaction.followup.send("تعذر تبديل الرتبة. تأكد من صلاحية إدارة الرتب.")
                return
        card = mafia_card(DUTY_ROLES[active], "تم تحديث حالة حضورك في العصابة.")
        card.set_thumbnail(url=f"attachment://{icon}")
        await interaction.followup.send(embed=card, files=[attachment("banner.png"), attachment(icon)])

    @discord.ui.button(label="تسجيل دخول", custom_id="rc:duty:in", style=discord.ButtonStyle.success)
    async def check_in(self, interaction, button):
        await self.set_status(interaction, True)

    @discord.ui.button(label="تسجيل خروج", custom_id="rc:duty:out", style=discord.ButtonStyle.danger)
    async def check_out(self, interaction, button):
        await self.set_status(interaction, False)


@tree.command(name="gang-system", description="تجهيز لوحة تسجيل دخول وخروج العصابة", guild=GUILD)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def gang_system(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    group = category(guild)
    ranks = [item for item in guild.roles if item.name in ROLE_NAMES.values()]
    if not group or not ranks:
        await interaction.followup.send("لازم تكون كاتيجوري المافيا ورتبها موجودة أول.")
        return
    async with LOCK:
        try:
            for name in DUTY_ROLES.values():
                if not discord.utils.get(guild.roles, name=name):
                    await guild.create_role(name=name)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                **{r: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True) for r in ranks},
            }
            channel = gang_room(guild, "الحضور")
            if channel is None:
                channel = await guild.create_text_channel(ROOM_NAMES["الحضور"], category=group, overwrites=overwrites)
            else:
                await channel.edit(overwrites=overwrites)
            async for message in channel.history(limit=50):
                if message.author.id == client.user.id and any(e.title == "نظام حضور المافيا الروسية" for e in message.embeds):
                    break
            else:
                card = mafia_card("نظام حضور المافيا الروسية", "اضغط تسجيل دخول عند بدء حضورك، وتسجيل خروج عند انتهائك.")
                await channel.send(embed=card, file=attachment("banner.png"), view=Duty())
        except discord.HTTPException:
            await interaction.followup.send("تعذر تجهيز الحضور. تأكد من صلاحيات القنوات والرتب والإرفاق.")
            return
    await interaction.followup.send(f"لوحة الحضور جاهزة في {channel.mention}.")


@tree.command(name="mafia-stickers", description="إضافة ستيكرات الصح والإكس للسيرفر", guild=GUILD)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def mafia_stickers(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    try:
        async with LOCK:
            existing = {item.name for item in await guild.fetch_stickers()}
            for name, tag, icon in (("Mafia Check", "✅", "check.png"), ("Mafia Cross", "❌", "cross.png")):
                if name not in existing:
                    await guild.create_sticker(name=name, description=name, emoji=tag, file=attachment(icon))
    except discord.HTTPException:
        await interaction.followup.send("تعذر رفع بعض الستيكرات. تأكد من وجود خانات متاحة وصلاحية إنشاء تعبيرات السيرفر.")
        return
    card = mafia_card("ستيكرات المافيا الروسية", "صح وإكس جاهزة في قائمة ستيكرات السيرفر.")
    await interaction.followup.send(embed=card, file=attachment("banner.png"))


for command in (mafia_welcome, gang_system, mafia_stickers):
    command.error(setup_error)


client.run(os.environ["DISCORD_TOKEN"])
