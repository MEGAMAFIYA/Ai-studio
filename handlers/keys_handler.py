import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_ID
from services import key_store
from services.ai_providers import PROVIDERS, PRIORITY_ORDER

logger = logging.getLogger(__name__)


def _build_main_menu() -> InlineKeyboardMarkup:
    rows = []
    for provider_id in PRIORITY_ORDER:
        count = len(key_store.get_keys(provider_id))
        label = PROVIDERS[provider_id]["label"]
        mark = f"✅ ({count})" if count > 0 else "➖"
        rows.append([InlineKeyboardButton(f"{label} {mark}", callback_data=f"keys_view_{provider_id}")])
    rows.append([InlineKeyboardButton("➕ Yangi kalit qo'shish", callback_data="keys_add")])
    return InlineKeyboardMarkup(rows)


def _build_provider_picker() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for provider_id in PRIORITY_ORDER:
        row.append(InlineKeyboardButton(PROVIDERS[provider_id]["label"], callback_data=f"keys_pick_{provider_id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="keys_menu")])
    return InlineKeyboardMarkup(rows)


def _build_provider_view(provider_id: str) -> InlineKeyboardMarkup:
    rows = []
    for idx, key in enumerate(key_store.get_keys(provider_id)):
        rows.append([InlineKeyboardButton(
            f"🗑 {key_store.mask_key(key)}", callback_data=f"keys_del_{provider_id}_{idx}"
        )])
    rows.append([InlineKeyboardButton("➕ Shu provayderga kalit qo'shish", callback_data=f"keys_pick_{provider_id}")])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="keys_menu")])
    return InlineKeyboardMarkup(rows)


async def keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data.pop('awaiting_key_for', None)
    await update.message.reply_text(
        "🔑 <b>AI provayder kalitlari</b>\n\n"
        "Tarjima uchun bir nechta provayder ulashingiz mumkin — biri ishlamasa "
        "(limit, xato), navbatdagisiga avtomatik o'tiladi.\n\n"
        "⚠️ Eslatma: agar Render'da doimiy disk ulanmagan bo'lsa, bu yerga "
        "qo'shilgan kalitlar har qayta deploy qilinganda o'chib ketadi.",
        parse_mode="HTML",
        reply_markup=_build_main_menu()
    )


async def keys_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer()
        return

    await query.answer()
    data = query.data

    if data == "keys_menu":
        context.user_data.pop('awaiting_key_for', None)
        await query.edit_message_text(
            "🔑 <b>AI provayder kalitlari</b>",
            parse_mode="HTML",
            reply_markup=_build_main_menu()
        )

    elif data == "keys_add":
        await query.edit_message_text(
            "Qaysi AI turi uchun kalit qo'shmoqchisiz?",
            reply_markup=_build_provider_picker()
        )

    elif data.startswith("keys_pick_"):
        provider_id = data[len("keys_pick_"):]
        cfg = PROVIDERS.get(provider_id)
        if not cfg:
            return
        context.user_data['awaiting_key_for'] = provider_id
        note = f"\n\n⚠️ {cfg['note']}" if cfg.get("note") else ""
        await query.edit_message_text(
            f"🔹 <b>{cfg['label']}</b> uchun kalit yuboring.\n\n"
            f"Bepul kalit olish: {cfg['signup_url']}{note}\n\n"
            f"Kalitni shu chatga oddiy xabar sifatida yuboring.",
            parse_mode="HTML"
        )

    elif data.startswith("keys_view_"):
        provider_id = data[len("keys_view_"):]
        cfg = PROVIDERS.get(provider_id)
        if not cfg:
            return
        count = len(key_store.get_keys(provider_id))
        await query.edit_message_text(
            f"🔹 <b>{cfg['label']}</b> — {count} ta kalit saqlangan.\n\n"
            f"O'chirish uchun kalitni bosing:",
            parse_mode="HTML",
            reply_markup=_build_provider_view(provider_id)
        )

    elif data.startswith("keys_del_"):
        rest = data[len("keys_del_"):]
        provider_id, idx_str = rest.rsplit("_", 1)
        key_store.remove_key(provider_id, int(idx_str))
        cfg = PROVIDERS.get(provider_id, {})
        count = len(key_store.get_keys(provider_id))
        await query.edit_message_text(
            f"🔹 <b>{cfg.get('label', provider_id)}</b> — {count} ta kalit saqlangan.",
            parse_mode="HTML",
            reply_markup=_build_provider_view(provider_id)
        )


async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Agar admin hozir kalit yuborishni kutayotgan bo'lsa, xabarni kalit
    sifatida saqlaydi va True qaytaradi. Aks holda False qaytaradi —
    shunda xabar boshqa handler'larga o'tadi.
    """
    if update.effective_user.id != ADMIN_ID:
        return False

    provider_id = context.user_data.get('awaiting_key_for')
    if not provider_id:
        return False

    api_key = update.message.text.strip()
    key_store.add_key(provider_id, api_key)
    context.user_data.pop('awaiting_key_for', None)

    cfg = PROVIDERS.get(provider_id, {})
    try:
        await update.message.delete()  # kalitni chatda ochiq qoldirmaslik uchun
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ {cfg.get('label', provider_id)} uchun kalit saqlandi.",
    )
    return True
