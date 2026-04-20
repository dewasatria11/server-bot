import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json

# ── KONFIGURASI ──────────────────────────────────────────────
TOKEN        = "8009319057:AAHGaZIOU1hnAC_tkVWFwBxAiqnnIAewZW8"
ANTIGRAVITY_URL = "http://127.0.0.1:8045"
API_KEY      = "sk-70af98ff75ef4b90909d61dbc678619e"
MAX_HISTORY  = 8

SYSTEM_PROMPT = (
    "Kamu AI serba bisa (mas_dewa_bot). Jawab informatif, padat, natural. "
    "Bahas apa saja (sains, sejarah, dll) menyesuaikan gaya bahasa user. "
    "PENTING: Jawab Teks Biasa TANPA markdown (*bold*, _italic_, #) sama sekali. "
    "Jika tidak tahu, jujur saja. Jangan kepanjangan."
)

AVAILABLE_MODELS = {
    "gemini-3-flash": "⚡ Gemini 3 Flash",
    "gemini-3.1-pro-high": "🚀 Gemini 3.1 Pro High",
    "claude-sonnet-4-6": "🧠 Claude Sonnet 4.6",
    "claude-opus-4-6-thinking": "💡 Claude Opus 4.6 (Thinking)",
    "gpt-oss-120b-medium": "🌐 GPT OSS 120B"
}
DEFAULT_MODEL = "gemini-3-flash"

# ── STATE ───────────────────────────────────────────────────
chat_histories = {}   # { chat_id: [ {role, content}, ... ] }
user_models = {}      # { chat_id: "model_name" }

bot = telebot.TeleBot(TOKEN)

def get_history(chat_id):
    return chat_histories.setdefault(chat_id, [])

def trim_history(chat_id):
    h = chat_histories.get(chat_id, [])
    if len(h) > MAX_HISTORY:
        chat_histories[chat_id] = h[-MAX_HISTORY:]

def ask_ai(chat_id, user_text, user_name="User"):
    history = get_history(chat_id)
    history.append({"role": "user", "content": user_text})
    trim_history(chat_id)

    model_id = user_models.get(chat_id, DEFAULT_MODEL)
    
    dynamic_system = SYSTEM_PROMPT + f"\n[PENTING: User ini bernama '{user_name}'. Sapa atau sebut namanya sesekali agar akrab.]"

    payload = {
        "model":      model_id,
        "max_tokens": 600,
        "system":     dynamic_system,
        "messages":   history
    }

    try:
        res = requests.post(
            f"{ANTIGRAVITY_URL}/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json=payload,
            timeout=80  # tambah timeout karena model thinking butuh waktu lama
        )
        data = res.json()

        if not res.ok or data.get("type") == "error":
            err = data.get("error", {}).get("message") or data.get("message") or f"Status {res.status_code}"
            return f"⚠ Error dari server AI: {err}"

        content_blocks = data.get("content", [])
        
        # Ekstrak konten thinking (jika user milih Claude Opus Thinking)
        thinking_block = next((c for c in content_blocks if c.get("type") == "thinking"), None)
        thinking_text = thinking_block.get("thinking") if thinking_block else None
            
        # Ekstrak text utama
        text_block = next((c for c in content_blocks if c.get("type") == "text"), None)
        reply = text_block.get("text") if text_block else None
        
        if not reply and not thinking_text:
            return "⚠ Model tidak mengembalikan respons teks. Coba ganti model lain."

        # Simpan state history
        history.append({"role": "assistant", "content": reply or f"(Thinking: {thinking_text})"})
        
        # Tampilkan hanya teks utama, sembunyikan proses thinking dari tampilan Telegram
        final_reply = reply.replace("**", "").replace("*", "") if reply else None
        
        if not final_reply:
             final_reply = "⚠ (Model hanya memproses secara internal, tidak ada jawaban berbentuk teks)"
             
        return final_reply

    except requests.exceptions.ConnectionError:
        return (
            "⚠ Tidak bisa terhubung ke Antigravity Tools.\n\n"
            "Pastikan server sudah berjalan:\n"
            "  antigravity start\n\n"
            f"Server harus aktif di: {ANTIGRAVITY_URL}"
        )
    except requests.exceptions.Timeout:
        return "⚠ Waktu tunggu habis. Server terlalu lama merespons. Jika pakai model Thinking, coba tunggu lebih sabar."
    except Exception as e:
        return f"⚠ Terjadi kesalahan: {str(e)}"

# ── KEYBOARD MAKER ───────────────────────────────────────────
def make_model_keyboard():
    markup = InlineKeyboardMarkup()
    for model_id, model_name in AVAILABLE_MODELS.items():
        # Tambahkan tiap tombol ke baris baru
        markup.add(InlineKeyboardButton(text=model_name, callback_data=f"setmodel_{model_id}"))
    return markup


# ── HANDLERS ─────────────────────────────────────────────────
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    chat_histories[message.chat.id] = []   # reset history tiap kali /start
    
    first_name = message.from_user.first_name or "Pengguna"
    
    txt = (
        f"Halo {first_name}! Saya mas_dewa — asisten AI kamu!\n\n"
        "Silakan pilih otak (model) AI di bawah ini untuk memulai percakapan:\n"
    )
    bot.reply_to(message, txt, reply_markup=make_model_keyboard())


@bot.message_handler(commands=["reset"])
def cmd_reset(message):
    chat_histories[message.chat.id] = []
    bot.reply_to(message, "✅ Riwayat percakapan telah direset. Mulai percakapan baru!")


@bot.message_handler(commands=["model"])
def cmd_model(message):
    current_model = user_models.get(message.chat.id, DEFAULT_MODEL)
    current_name = AVAILABLE_MODELS.get(current_model, current_model)
    
    txt = (
        f"🤖 Model saat ini: {current_name}\n\n"
        "Ingin mengganti model? Pilih opsi di bawah:"
    )
    bot.reply_to(message, txt, reply_markup=make_model_keyboard())


@bot.callback_query_handler(func=lambda call: call.data.startswith("setmodel_"))
def callback_set_model(call):
    chat_id = call.message.chat.id
    new_model = call.data.replace("setmodel_", "")
    
    # 1. Simpan model preferensi user ke memory
    user_models[chat_id] = new_model
    model_name = AVAILABLE_MODELS.get(new_model, new_model)
    
    # 2. Reset history biar ga ada context collision model
    chat_histories[chat_id] = []
    
    # 3. Notification ke telegram UI
    bot.answer_callback_query(call.id, f"Model diubah ke {model_name}")
    
    # 4. Ganti teks isi pesan tombolnya
    bot.edit_message_text(
        text=f"✅ Model AI diatur ke: {model_name}!\n\nRiwayat mereset otomatis. Silakan ketik pertanyaanmu.",
        chat_id=chat_id,
        message_id=call.message.message_id
    )


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    if not message.text:
        bot.reply_to(message, "Maaf, saya hanya bisa memproses pesan teks.")
        return

    # Tampilkan indikator "sedang mengetik..."
    bot.send_chat_action(message.chat.id, "typing")
    
    first_name = message.from_user.first_name or "Pengguna"
    reply = ask_ai(message.chat.id, message.text, first_name)
    bot.reply_to(message, reply)

# ── START ─────────────────────────────────────────────────────
print(f"✅ mas_dewa_bot berjalan dengan fitur Multi-Model UI...")
print(f"   Antigravity URL : {ANTIGRAVITY_URL}")
print("   Tekan Ctrl+C untuk berhenti.\n")
bot.infinity_polling()
