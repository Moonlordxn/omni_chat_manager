import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)

from config import BOT_TOKEN, BOT_NAME, RANK_NAMES, RANK_REQUIRED
from db import (
    init_db, upsert_user, upsert_chat,
    get_admin_rank, set_admin_rank, remove_admin, list_admins,
    add_warn, get_warns_count, remove_last_warn, clear_warns,
    set_mute, remove_mute,
)

# ============================================================
#                      ИНИЦИАЛИЗАЦИЯ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
#                    ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def get_target(message: types.Message) -> types.User | None:
    """Возвращает пользователя, на чьё сообщение ответили."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


def parse_duration(text: str) -> timedelta | None:
    """Парсит '30м', '1ч', '2д', '10с'."""
    if not text:
        return None
    text = text.lower().strip()
    units = {
        "с": "seconds", "сек": "seconds",
        "м": "minutes", "мин": "minutes",
        "ч": "hours",   "час": "hours",
        "д": "days",    "дн": "days",
    }
    for suffix, unit in units.items():
        if text.endswith(suffix):
            num_part = text[: -len(suffix)].strip()
            if num_part.isdigit():
                return timedelta(**{unit: int(num_part)})
    return None


async def get_effective_rank(chat_id: int, user_id: int) -> int:
    """
    Возвращает эффективный ранг:
    - 5, если владелец чата
    - ранг из БД
    - 0, если не админ
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status == "creator":
            return 5
    except Exception:
        pass
    rank = await get_admin_rank(chat_id, user_id)
    return rank or 0


async def can_do(chat_id: int, user_id: int, action: str) -> bool:
    required = RANK_REQUIRED.get(action, 99)
    rank = await get_effective_rank(chat_id, user_id)
    return rank >= required


# ============================================================
#                    КЛАВИАТУРЫ
# ============================================================

def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👢 Кикнуть",        callback_data="adm_kick"),
                InlineKeyboardButton(text="🔇 Замутить",       callback_data="adm_mute"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Предупреждение", callback_data="adm_warn"),
                InlineKeyboardButton(text="🚫 Забанить",        callback_data="adm_ban"),
            ],
            [
                InlineKeyboardButton(text="📋 Список админов",  callback_data="adm_list"),
                InlineKeyboardButton(text="⚙️ Настройки",       callback_data="adm_settings"),
            ],
        ]
    )


# ============================================================
#                    РЕГИСТРАЦИЯ КОМАНД
# ============================================================

async def set_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="help",  description="📖 Список команд"),
    ])


# ============================================================
#                    БАЗОВЫЕ КОМАНДЫ
# ============================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"Я — <b>{BOT_NAME}</b>.\n"
        f"Помогаю следить за порядком в чате. 🛡️\n\n"
        f"В группе напиши <b>админ</b>, чтобы открыть панель."
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды Omni:</b>\n\n"
        "🔹 /start — запуск\n"
        "🔹 /help — помощь\n"
        "🔹 <b>пинг</b> — проверка связи\n"
        "🔹 <b>!админы</b> — список администраторов\n"
        "🔹 <b>мой ранг</b> — узнать свой ранг\n\n"
        "🛡️ <b>Модерация (по реплаю):</b>\n"
        "🔸 <b>варн</b>, <b>снять варн</b>, <b>варны</b> — ранг 1+\n"
        "🔸 <b>мут</b>, <b>мут 30м</b>, <b>размут</b> — ранг 1+\n"
        "🔸 <b>кик</b> — ранг 2+\n"
        "🔸 <b>бан</b>, <b>разбан</b> — ранг 3+\n\n"
        "👑 <b>Управление админами (ранг 5):</b>\n"
        "🔸 <b>повысить</b>, <b>понизить</b>, <b>снять</b>\n"
        "🔸 <b>назначить 3</b> — назначить конкретный ранг"
    )


@dp.message(F.text.lower().strip() == "пинг")
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Понг! Бот на связи.")


@dp.message(F.text.lower().strip() == "!админы")
async def cmd_admin_list(message: types.Message):
    if message.chat.type == "private":
        await message.reply("ℹ️ Только для групп.")
        return

    await upsert_chat(message.chat.id, message.chat.title or "")

    try:
        admins = await bot.get_chat_administrators(message.chat.id)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        return

    creator = None
    admins_lines = []

    for member in admins:
        user = member.user
        if user.is_bot:
            continue
        username = f" (@{user.username})" if user.username else ""
        if member.status == "creator":
            creator = f"• <b>{user.full_name}</b>{username} — 👑 Владелец"
        else:
            db_rank = await get_admin_rank(message.chat.id, user.id)
            rank_text = RANK_NAMES.get(db_rank, "🛡️ Админ Telegram")
            admins_lines.append(f"• <b>{user.full_name}</b>{username} — {rank_text}")

    text = f"🛡️ <b>АДМИНИСТРАЦИЯ ЧАТА</b>\n<i>{message.chat.title}</i>\n\n"
    if creator:
        text += f"👑 <b>Владелец:</b>\n{creator}\n\n"
    if admins_lines:
        text += f"⭐ <b>Администраторы ({len(admins_lines)}):</b>\n" + "\n".join(admins_lines)
    else:
        text += "⭐ <i>Кроме владельца, администраторов нет.</i>"

    await message.reply(text)


@dp.message(F.text.lower().strip() == "мой ранг")
async def cmd_my_rank(message: types.Message):
    if message.chat.type == "private":
        await message.reply("ℹ️ Только для групп.")
        return
    rank = await get_effective_rank(message.chat.id, message.from_user.id)
    if rank == 0:
        await message.reply("👤 Ты не администратор этого чата.")
    elif rank == 5:
        await message.reply("👑 Ты — <b>владелец</b> чата (высший ранг).")
    else:
        await message.reply(f"🛡️ Твой ранг: <b>{RANK_NAMES[rank]}</b> ({rank}/5)")


# ============================================================
#                    ПАНЕЛЬ АДМИНА
# ============================================================

@dp.message(F.text.lower().strip() == "админ")
async def cmd_admin_panel(message: types.Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ Только для групп.")
        return

    rank = await get_effective_rank(message.chat.id, message.from_user.id)
    if rank == 0:
        warn = await message.reply("⛔ Нет прав администратора.")
        await asyncio.sleep(5)
        try:
            await warn.delete()
            await message.delete()
        except Exception:
            pass
        return

    try:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=(
                f"🛡️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n"
                f"Чат: <b>{message.chat.title}</b>\n"
                f"Твой ранг: <b>{RANK_NAMES.get(rank, '?')}</b>\n\n"
                f"Выберите действие:"
            ),
            reply_markup=admin_panel_kb(),
        )
        note = await message.reply("✅ Панель отправлена в личку.")
        await asyncio.sleep(5)
        try:
            await note.delete()
        except Exception:
            pass
    except Exception:
        await message.reply(
            "⚠️ Не могу написать в личку.\n"
            "Напишите мне <b>/start</b> и попробуйте снова."
        )


@dp.callback_query(F.data.startswith("adm_"))
async def handle_admin_buttons(callback: CallbackQuery):
    action = callback.data
    texts = {
        "adm_kick":     "👢 Ответьте реплаем на сообщение нарушителя и напишите <code>кик</code>.",
        "adm_mute":     "🔇 Ответьте реплаем и напишите <code>мут</code> или <code>мут 30м</code>.",
        "adm_warn":     "⚠️ Ответьте реплаем и напишите <code>варн</code>.",
        "adm_ban":      "🚫 Ответьте реплаем и напишите <code>бан</code>.",
        "adm_list":     "📋 В группе напишите <code>!админы</code>.",
        "adm_settings": "⚙️ <i>Раздел в разработке.</i>",
    }
    await callback.answer()
    await callback.message.edit_text(
        texts.get(action, "❓ Неизвестно"),
        reply_markup=admin_panel_kb(),
    )


# ============================================================
#                    УПРАВЛЕНИЕ РАНГАМИ
# ============================================================

async def _require_rank5(message: types.Message) -> bool:
    rank = await get_effective_rank(message.chat.id, message.from_user.id)
    if rank < 5:
        await message.reply("⛔ Только главный админ (ранг 5).")
        return False
    return True


@dp.message(F.text.lower().strip() == "повысить")
async def cmd_promote(message: types.Message):
    if message.chat.type == "private":
        return
    if not await _require_rank5(message):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем на сообщение.")
        return
    if target.id == message.from_user.id:
        await message.reply("🙃 Себя повышать нельзя.")
        return

    current = await get_admin_rank(message.chat.id, target.id) or 0
    if current >= 5:
        await message.reply("👑 Уже максимальный ранг.")
        return
    new_rank = current + 1
    await upsert_user(target.id, target.username, target.full_name)
    await set_admin_rank(message.chat.id, target.id, new_rank, message.from_user.id)
    await message.reply(
        f"⬆️ <b>{target.full_name}</b> → <b>{RANK_NAMES[new_rank]}</b> ({new_rank}/5)"
    )


@dp.message(F.text.lower().strip() == "понизить")
async def cmd_demote(message: types.Message):
    if message.chat.type == "private":
        return
    if not await _require_rank5(message):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if target.id == message.from_user.id:
        await message.reply("🙃 Себя понижать нельзя.")
        return

    current = await get_admin_rank(message.chat.id, target.id)
    if current is None:
        await message.reply("ℹ️ Этот пользователь не назначался через бота.")
        return
    if current <= 1:
        await message.reply("ℹ️ Минимальный ранг. Используйте <b>снять</b>.")
        return
    new_rank = current - 1
    await set_admin_rank(message.chat.id, target.id, new_rank, message.from_user.id)
    await message.reply(
        f"⬇️ <b>{target.full_name}</b> → <b>{RANK_NAMES[new_rank]}</b> ({new_rank}/5)"
    )


@dp.message(F.text.lower().strip() == "снять")
async def cmd_dismiss(message: types.Message):
    if message.chat.type == "private":
        return
    if not await _require_rank5(message):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if target.id == message.from_user.id:
        await message.reply("🙃 Себя снять нельзя.")
        return

    current = await get_admin_rank(message.chat.id, target.id)
    if current is None:
        await message.reply("ℹ️ Он и так не админ (в БД).")
        return
    await remove_admin(message.chat.id, target.id)
    await message.reply(f"❌ <b>{target.full_name}</b> снят с должности.")


@dp.message(F.text.lower().startswith("назначить "))
async def cmd_appoint(message: types.Message):
    if message.chat.type == "private":
        return
    if not await _require_rank5(message):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply("⚠️ Формат: <code>назначить 3</code> реплаем.")
        return
    rank = int(parts[1])
    if rank not in RANK_NAMES:
        await message.reply("⚠️ Ранг от 1 до 5.")
        return
    await upsert_user(target.id, target.username, target.full_name)
    await set_admin_rank(message.chat.id, target.id, rank, message.from_user.id)
    await message.reply(
        f"✅ <b>{target.full_name}</b> → <b>{RANK_NAMES[rank]}</b> ({rank}/5)"
    )


# ============================================================
#                    МОДЕРАЦИЯ
# ============================================================

async def check_action(message: types.Message, action: str) -> bool:
    if not await can_do(message.chat.id, message.from_user.id, action):
        await message.reply("⛔ Недостаточно прав.")
        return False
    return True


async def check_target(message: types.Message, target: types.User) -> bool:
    if target.id == bot.id:
        await message.reply("🤖 Меня наказывать нельзя!")
        return False
    my_rank = await get_effective_rank(message.chat.id, message.from_user.id)
    target_rank = await get_effective_rank(message.chat.id, target.id)
    if target_rank >= my_rank and target_rank > 0:
        await message.reply("🛡️ Нельзя наказать админа равного или высшего ранга.")
        return False
    return True


# ---------- ВАРН ----------
@dp.message(F.text.lower().strip() == "варн")
async def cmd_warn(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "warn"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if not await check_target(message, target):
        return

    count = await add_warn(message.chat.id, target.id, message.from_user.id)
    if count >= 3:
        until = datetime.now() + timedelta(hours=1)
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await set_mute(message.chat.id, target.id, message.from_user.id, until.isoformat())
            await clear_warns(message.chat.id, target.id)
            await message.reply(
                f"⚠️ <b>{target.full_name}</b> получил 3/3 варна и замучен на 1 час."
            )
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")
    else:
        await message.reply(f"⚠️ <b>{target.full_name}</b> — предупреждение <b>{count}/3</b>")


@dp.message(F.text.lower().strip() == "снять варн")
async def cmd_unwarn(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "warn"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if await remove_last_warn(message.chat.id, target.id):
        count = await get_warns_count(message.chat.id, target.id)
        await message.reply(f"✅ Снят 1 варн с <b>{target.full_name}</b>. Осталось: <b>{count}/3</b>")
    else:
        await message.reply(f"ℹ️ У <b>{target.full_name}</b> нет варнов.")


@dp.message(F.text.lower().strip() == "варны")
async def cmd_warns(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "warn"):
        return
    target = get_target(message) or message.from_user
    count = await get_warns_count(message.chat.id, target.id)
    await message.reply(f"📋 <b>{target.full_name}</b> — варнов: <b>{count}/3</b>")


# ---------- МУТ ----------
@dp.message(F.text.lower().startswith("мут"))
async def cmd_mute(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "mute"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if not await check_target(message, target):
        return

    parts = message.text.lower().strip().split(maxsplit=1)
    duration = parse_duration(parts[1]) if len(parts) > 1 else timedelta(hours=1)
    if duration is None:
        await message.reply("⚠️ Формат: <code>мут 30м</code>, <code>мут 2ч</code>, <code>мут 1д</code>")
        return

    until = datetime.now() + duration
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await set_mute(message.chat.id, target.id, message.from_user.id, until.isoformat())
        await message.reply(
            f"🔇 <b>{target.full_name}</b> замучен до <b>{until.strftime('%H:%M %d.%m.%Y')}</b>."
        )
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@dp.message(F.text.lower().strip() == "размут")
async def cmd_unmute(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "unmute"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await remove_mute(message.chat.id, target.id)
        await message.reply(f"🔊 <b>{target.full_name}</b> размучен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# ---------- КИК ----------
@dp.message(F.text.lower().strip() == "кик")
async def cmd_kick(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "kick"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if not await check_target(message, target):
        return
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.reply(f"👢 <b>{target.full_name}</b> выкинут.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# ---------- БАН ----------
@dp.message(F.text.lower().strip() == "бан")
async def cmd_ban(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "ban"):
        return
    target = get_target(message)
    if not target:
        await message.reply("⚠️ Ответьте реплаем.")
        return
    if not await check_target(message, target):
        return
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.reply(f"🚫 <b>{target.full_name}</b> забанен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@dp.message(F.text.lower().strip() == "разбан")
async def cmd_unban(message: types.Message):
    if message.chat.type == "private":
        return
    if not await check_action(message, "unban"):
        return
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
            await message.reply("⚠️ Ответьте реплаем или укажите ID: <code>разбан 123456789</code>")
            return
        target_id = int(parts[1].strip())
    try:
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.reply(f"✅ ID <code>{target_id}</code> разбанен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# ============================================================
#                    ЗАПУСК
# ============================================================

async def main():
    print(f"🤖 {BOT_NAME} запускается...")
    await init_db()
    await set_commands(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Бот остановлен.")
