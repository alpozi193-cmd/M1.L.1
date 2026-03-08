"""
🎮 MEGA DISCORD BOT - TÜM ÖZELLİKLER
Seviye • Müzik • Oyunlar • RPG • Ticket • Hava • Kripto • Meme
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import aiohttp
import json
import random
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re
import yt_dlp

# ==================== KONFIGÜRASYON ====================
TOKEN = 'token here'
PREFIX = '!'
DB_FILE = 'megabot.db'

# API Keys - GEREKSİZ!
# Hava durumu ve kripto için hiçbir API key gerekmiyor!

# ==================== INTENTS ====================
intents = discord.Intents.default()
intents.message_content = True  # Mesaj içeriğini okumak için (XP, komutlar)
intents.members = True          # Üye olayları ve profil komutları için
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ==================== MÜZİK KUYRUK SİSTEMİ ====================
music_queues = {}  # {guild_id: deque([url, url, ...])}
now_playing = {}   # {guild_id: {'title': ..., 'url': ...}}
loop_mode = {}     # {guild_id: 'off'/'song'/'queue'}

# ==================== VERİTABANI ====================
def init_db():
    """Veritabanı oluştur"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Seviye sistemi
    c.execute('''CREATE TABLE IF NOT EXISTS levels 
                 (user_id TEXT PRIMARY KEY, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, messages INTEGER DEFAULT 0)''')
    
    # Ekonomi
    c.execute('''CREATE TABLE IF NOT EXISTS economy 
                 (user_id TEXT PRIMARY KEY, coins INTEGER DEFAULT 100, bank INTEGER DEFAULT 0)''')
    
    # RPG sistemi
    c.execute('''CREATE TABLE IF NOT EXISTS rpg 
                 (user_id TEXT PRIMARY KEY, 
                  hp INTEGER DEFAULT 100, 
                  max_hp INTEGER DEFAULT 100,
                  attack INTEGER DEFAULT 10,
                  defense INTEGER DEFAULT 5,
                  gold INTEGER DEFAULT 100,
                  inventory TEXT DEFAULT '{}',
                  equipped TEXT DEFAULT '{}',
                  location TEXT DEFAULT 'village')''')
    
    # Hoşgeldin ayarları
    c.execute('''CREATE TABLE IF NOT EXISTS welcome 
                 (guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, role_id TEXT)''')
    
    # Ticket ayarları
    c.execute('''CREATE TABLE IF NOT EXISTS tickets 
                 (guild_id TEXT PRIMARY KEY, category_id TEXT, support_role_id TEXT)''')
    
    conn.commit()
    conn.close()

# ==================== SEVIYE SISTEMI ====================
xp_cooldown = {}  # Anti-spam için

def calculate_level(xp):
    """XP'den level hesapla"""
    return int((xp / 100) ** 0.5) + 1

def xp_for_next_level(level):
    """Sonraki level için gereken XP"""
    return ((level) ** 2) * 100

def add_xp(user_id, amount=15):
    """XP ekle ve level kontrolü"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT xp, level, messages FROM levels WHERE user_id=?", (str(user_id),))
    result = c.fetchone()
    
    if result:
        old_xp, old_level, msgs = result
        new_xp = old_xp + amount
        new_level = calculate_level(new_xp)
        c.execute("UPDATE levels SET xp=?, level=?, messages=? WHERE user_id=?",
                  (new_xp, new_level, msgs + 1, str(user_id)))
    else:
        new_xp, new_level, msgs = amount, 1, 1
        c.execute("INSERT INTO levels VALUES (?, ?, ?, ?)",
                  (str(user_id), new_xp, new_level, 1))
    
    conn.commit()
    conn.close()
    
    leveled_up = result and new_level > old_level
    return new_level if leveled_up else None

@bot.event
async def on_message(message):
    """Her mesajda XP ver"""
    if message.author.bot:
        return
    
    # XP cooldown (spam önleme)
    user_id = message.author.id
    now = datetime.now().timestamp()
    
    if user_id not in xp_cooldown or now - xp_cooldown[user_id] > 60:  # 60 saniye cooldown
        xp_cooldown[user_id] = now
        
        new_level = add_xp(user_id)
        if new_level:
            embed = discord.Embed(
                title="🎉 LEVEL UP!",
                description=f"{message.author.mention} **Level {new_level}** oldu!",
                color=0xffd700
            )
            await message.channel.send(embed=embed, delete_after=5)
    
    await bot.process_commands(message)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    """Seviye ve XP göster"""
    member = member or ctx.author
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT xp, level, messages FROM levels WHERE user_id=?", (str(member.id),))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return await ctx.send(f"❌ {member.display_name} henüz mesaj atmamış!")
    
    xp, level, msgs = result
    
    # Sıralama hesapla
    c.execute("SELECT COUNT(*) FROM levels WHERE xp > ?", (xp,))
    rank_pos = c.fetchone()[0] + 1
    conn.close()
    
    next_level_xp = xp_for_next_level(level)
    current_level_xp = xp_for_next_level(level - 1) if level > 1 else 0
    progress = xp - current_level_xp
    needed = next_level_xp - current_level_xp
    
    # Progress bar
    bar_length = 20
    filled = int((progress / needed) * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed = discord.Embed(
        title=f"📊 {member.display_name}",
        color=member.color or 0x00ff00
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="🏆 Sıralama", value=f"#{rank_pos}", inline=True)
    embed.add_field(name="⭐ Level", value=str(level), inline=True)
    embed.add_field(name="📝 Mesaj", value=str(msgs), inline=True)
    embed.add_field(name="✨ XP", value=f"{xp:,}", inline=True)
    embed.add_field(name="🎯 Sonraki Level", value=f"{progress}/{needed}\n{bar}", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx):
    """Seviye sıralaması"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, xp, level FROM levels ORDER BY xp DESC LIMIT 10")
    results = c.fetchall()
    conn.close()
    
    if not results:
        return await ctx.send("❌ Henüz kimse mesaj atmamış!")
    
    embed = discord.Embed(
        title="🏆 Seviye Sıralaması",
        color=0xffd700
    )
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, xp, level) in enumerate(results, 1):
        user = bot.get_user(int(user_id))
        name = user.name if user else "Bilinmeyen"
        medal = medals[i-1] if i <= 3 else f"#{i}"
        
        embed.add_field(
            name=f"{medal} {name}",
            value=f"Level **{level}** • {xp:,} XP",
            inline=False
        )
    
    await ctx.send(embed=embed)

# ==================== HAVA DURUMU (API KEY GEREKSİZ!) ====================
@bot.command()
async def weather(ctx, *, city: str):
    """Hava durumu (wttr.in - ücretsiz, API key gereksiz)"""
    try:
        # wttr.in API kullan (ücretsiz, key gereksiz!)
        url = f"https://wttr.in/{city}?format=j1"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.send(f"❌ Şehir bulunamadı: {city}")
                
                data = await response.json()
        
        # Mevcut durum
        current = data['current_condition'][0]
        temp = current['temp_C']
        feels_like = current['FeelsLikeC']
        humidity = current['humidity']
        description = current['weatherDesc'][0]['value']
        wind_speed = current['windspeedKmph']
        
        # Hava ikonu emoji
        weather_code = current['weatherCode']
        weather_emoji = {
            '113': '☀️',  # Güneşli
            '116': '⛅',  # Parçalı bulutlu
            '119': '☁️',  # Bulutlu
            '122': '☁️',  # Çok bulutlu
            '143': '🌫️',  # Sisli
            '176': '🌦️',  # Hafif yağmur
            '179': '🌨️',  # Hafif kar
            '182': '🌧️',  # Sağanak
            '185': '🌧️',  # Dondurucu yağmur
            '200': '⛈️',  # Gök gürültülü fırtına
            '227': '❄️',  # Kar fırtınası
            '230': '❄️',  # Tipi
            '248': '🌫️',  # Yoğun sis
            '260': '🌫️',  # Dondurucu sis
            '263': '🌧️',  # Çiseleyen yağmur
            '266': '🌧️',  # Hafif çiseleme
            '281': '🌧️',  # Dondurucu çiseleme
            '284': '🌧️',  # Yoğun dondurucu çiseleme
            '293': '🌧️',  # Hafif yağmur
            '296': '🌧️',  # Yağmur
            '299': '🌧️',  # Orta şiddetli yağmur
            '302': '🌧️',  # Şiddetli yağmur
            '305': '⛈️',  # Çok şiddetli yağmur
            '308': '⛈️',  # Sağanak yağmur
            '311': '🌧️',  # Dondurucu yağmur
            '314': '🌧️',  # Şiddetli dondurucu yağmur
            '317': '🌨️',  # Hafif kar
            '320': '🌨️',  # Orta şiddetli kar
            '323': '🌨️',  # Kar
            '326': '❄️',  # Şiddetli kar
            '329': '❄️',  # Yoğun kar
            '332': '🌨️',  # Hafif kar yağışı
            '335': '❄️',  # Orta kar yağışı
            '338': '❄️',  # Şiddetli kar yağışı
            '350': '🌨️',  # Dolu
            '353': '🌦️',  # Hafif sağanak
            '356': '⛈️',  # Orta/şiddetli sağanak
            '359': '⛈️',  # Şiddetli sağanak
            '362': '🌧️',  # Hafif karla karışık yağmur
            '365': '🌧️',  # Orta/şiddetli karla karışık yağmur
            '368': '🌨️',  # Hafif kar yağışı
            '371': '❄️',  # Orta/şiddetli kar yağışı
            '374': '🌨️',  # Hafif dolu yağışı
            '377': '🌨️',  # Orta/şiddetli dolu
            '386': '⛈️',  # Hafif gök gürültülü fırtına
            '389': '⛈️',  # Orta/şiddetli gök gürültülü fırtına
            '392': '⛈️',  # Hafif kar fırtınası
            '395': '⛈️'   # Orta/şiddetli kar fırtınası
        }.get(weather_code, '🌤️')
        
        embed = discord.Embed(
            title=f"{weather_emoji} {city.title()} Hava Durumu",
            description=description,
            color=0x00bfff
        )
        embed.add_field(name="🌡️ Sıcaklık", value=f"{temp}°C", inline=True)
        embed.add_field(name="🤔 Hissedilen", value=f"{feels_like}°C", inline=True)
        embed.add_field(name="💧 Nem", value=f"{humidity}%", inline=True)
        embed.add_field(name="💨 Rüzgar", value=f"{wind_speed} km/h", inline=True)
        embed.set_footer(text="Kaynak: wttr.in (API key gereksiz!)")
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}\nŞehir adını İngilizce dene (örn: istanbul, ankara, izmir)")


# ==================== KRİPTO FİYATLARI ====================
@bot.command()
async def crypto(ctx, symbol: str = "bitcoin"):
    """Kripto para fiyatı (CoinGecko API)"""
    try:
        symbol = symbol.lower()
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd,try&include_24hr_change=true"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.send(f"❌ Kripto bulunamadı: {symbol}")
                
                data = await response.json()
        
        if symbol not in data:
            return await ctx.send(f"❌ Kripto bulunamadı: {symbol}\nÖrnek: bitcoin, ethereum, dogecoin")
        
        usd = data[symbol]['usd']
        try_price = data[symbol]['try']
        change = data[symbol].get('usd_24h_change', 0)
        
        emoji = "📈" if change > 0 else "📉"
        color = 0x00ff00 if change > 0 else 0xff0000
        
        embed = discord.Embed(
            title=f"💰 {symbol.upper()}",
            color=color
        )
        embed.add_field(name="💵 USD", value=f"${usd:,.2f}", inline=True)
        embed.add_field(name="🇹🇷 TRY", value=f"₺{try_price:,.2f}", inline=True)
        embed.add_field(name=f"{emoji} 24h Değişim", value=f"{change:+.2f}%", inline=True)
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}")

# ==================== MEME/HAYVAN FOTOĞRAFLARI ====================
@bot.command()
async def meme(ctx):
    """Random meme"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme") as response:
                data = await response.json()
        
        embed = discord.Embed(
            title=data['title'],
            color=0xff4500
        )
        embed.set_image(url=data['url'])
        embed.set_footer(text=f"👍 {data['ups']} • r/{data['subreddit']}")
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}")

@bot.command()
async def dog(ctx):
    """Random köpek fotosu"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://dog.ceo/api/breeds/image/random") as response:
                data = await response.json()
        
        embed = discord.Embed(title="🐕 Random Köpek", color=0x8B4513)
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}")

@bot.command()
async def cat(ctx):
    """Random kedi fotosu"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.thecatapi.com/v1/images/search") as response:
                data = await response.json()
        
        embed = discord.Embed(title="🐱 Random Kedi", color=0xFFA500)
        embed.set_image(url=data[0]['url'])
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}")

# ==================== OYUNLAR ====================
@bot.command(aliases=['rps'])
async def taşkağıtmakas(ctx, choice: str):
    """Taş-Kağıt-Makas"""
    choices = {'taş': '🪨', 'kağıt': '📄', 'makas': '✂️', 
               'tas': '🪨', 'kagit': '📄'}
    
    choice = choice.lower()
    if choice not in choices and choice not in ['rock', 'paper', 'scissors']:
        return await ctx.send("❌ Seçenekler: taş, kağıt, makas")
    
    # İngilizce çevir
    translate = {'rock': 'taş', 'paper': 'kağıt', 'scissors': 'makas'}
    if choice in translate:
        choice = translate[choice]
    if choice == 'tas':
        choice = 'taş'
    if choice == 'kagit':
        choice = 'kağıt'
    
    bot_choice = random.choice(['taş', 'kağıt', 'makas'])
    
    # Kazanan belirleme
    wins = {
        ('taş', 'makas'): True,
        ('kağıt', 'taş'): True,
        ('makas', 'kağıt'): True
    }
    
    if choice == bot_choice:
        result = "🤝 BERABERE!"
        color = 0xffff00
        reward = 0
    elif wins.get((choice, bot_choice)):
        result = "🎉 KAZANDIN!"
        color = 0x00ff00
        reward = 50
        # Ekonomi ekle
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO economy (user_id, coins) VALUES (?, COALESCE((SELECT coins FROM economy WHERE user_id=?), 0) + ?)",
                  (str(ctx.author.id), str(ctx.author.id), reward))
        conn.commit()
        conn.close()
    else:
        result = "💸 KAYBETTİN!"
        color = 0xff0000
        reward = 0
    
    embed = discord.Embed(
        title="🎮 Taş-Kağıt-Makas",
        description=f"Sen: {choices[choice]} **{choice.upper()}**\nBot: {choices[bot_choice]} **{bot_choice.upper()}**\n\n{result}",
        color=color
    )
    if reward:
        embed.set_footer(text=f"+{reward} coin kazandın!")
    
    await ctx.send(embed=embed)

@bot.command(name='8ball')
async def eightball(ctx, *, question: str):
    """Sihirli 8-ball"""
    responses = [
        "✅ Kesinlikle evet!",
        "✅ Evet!",
        "🤔 Belki...",
        "🤔 Tekrar sor",
        "❌ Hayır",
        "❌ Kesinlikle hayır!",
        "🎲 Şansını dene",
        "💭 Şimdi söyleyemem",
        "🔮 Gelecek parlak görünüyor",
        "⚠️ Şüpheli...",
        "🌟 Kesinlikle!",
        "❌ Pek sanmıyorum"
    ]
    
    embed = discord.Embed(
        title="🎱 Sihirli 8-Ball",
        description=f"**Soru:** {question}\n**Cevap:** {random.choice(responses)}",
        color=0x000000
    )
    await ctx.send(embed=embed)

# ==================== TICKET SİSTEMİ ====================
@bot.command()
@commands.has_permissions(administrator=True)
async def ticketsetup(ctx):
    """Ticket sistemini kur (ADMIN)"""
    guild = ctx.guild
    
    # Ticket kategorisi oluştur
    category = await guild.create_category("🎫 TICKETS")
    
    # Support role (yoksa oluştur)
    support_role = discord.utils.get(guild.roles, name="Support")
    if not support_role:
        support_role = await guild.create_role(name="Support", color=0x00ff00)
    
    # DB'ye kaydet
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tickets VALUES (?, ?, ?)",
              (str(guild.id), str(category.id), str(support_role.id)))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(
        title="✅ Ticket Sistemi Kuruldu!",
        description=f"Kategori: {category.mention}\nDestek Rolü: {support_role.mention}\n\nKullanıcılar `!ticket` yazarak destek talebi açabilir.",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
async def ticket(ctx):
    """Destek talebi aç"""
    guild = ctx.guild
    
    # Ayarları kontrol et
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT category_id, support_role_id FROM tickets WHERE guild_id=?", (str(guild.id),))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return await ctx.send("❌ Ticket sistemi kurulmamış! Admin `!ticketsetup` yazmalı.")
    
    category_id, support_role_id = result
    category = guild.get_channel(int(category_id))
    support_role = guild.get_role(int(support_role_id))
    
    if not category:
        return await ctx.send("❌ Ticket kategorisi silinmiş! Admin tekrar `!ticketsetup` yapmalı.")
    
    # Zaten açık ticket var mı kontrol et
    for channel in category.channels:
        if str(ctx.author.id) in channel.name:
            return await ctx.send(f"❌ Zaten açık bir ticketın var: {channel.mention}")
    
    # Yeni ticket kanalı oluştur
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    channel = await category.create_text_channel(
        name=f"ticket-{ctx.author.name}",
        overwrites=overwrites
    )
    
    embed = discord.Embed(
        title="🎫 Destek Talebi",
        description=f"{ctx.author.mention} destek ekibi kısa süre içinde size yardımcı olacak.\n\nTalebi kapatmak için: `!close`",
        color=0x00ff00
    )
    embed.set_footer(text=f"Açan: {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    
    await channel.send(f"{ctx.author.mention} {support_role.mention if support_role else ''}", embed=embed)
    await ctx.send(f"✅ Ticket açıldı: {channel.mention}")

@bot.command()
async def close(ctx):
    """Ticket'ı kapat"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.send("❌ Bu sadece ticket kanallarında kullanılabilir!")
    
    embed = discord.Embed(
        title="🔒 Ticket Kapatılıyor",
        description="Kanal 5 saniye içinde silinecek...",
        color=0xff0000
    )
    await ctx.send(embed=embed)
    
    await asyncio.sleep(5)
    await ctx.channel.delete()

# ==================== HOŞGELDİN SİSTEMİ ====================
@bot.command()
@commands.has_permissions(administrator=True)
async def welcomesetup(ctx, channel: discord.TextChannel, *, message: str = None):
    """Hoşgeldin mesajı ayarla (ADMIN)
    Kullanım: !welcomesetup #kanal Hoşgeldin {user}! {server} sunucusuna katıldın!
    {user} = kullanıcı mention
    {server} = sunucu adı
    {count} = toplam üye sayısı
    """
    if not message:
        message = "👋 Hoşgeldin {user}! **{server}** sunucusuna katıldın! (#{count} üye)"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO welcome VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), str(channel.id), message, None))
    conn.commit()
    conn.close()
    
    # Test mesajı
    test_msg = message.replace('{user}', ctx.author.mention).replace('{server}', ctx.guild.name).replace('{count}', str(ctx.guild.member_count))
    
    embed = discord.Embed(
        title="✅ Hoşgeldin Mesajı Ayarlandı!",
        description=f"**Kanal:** {channel.mention}\n**Mesaj Önizleme:**\n{test_msg}",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.event
async def on_member_join(member):
    """Yeni üye katıldığında"""
    guild = member.guild
    
    # Hoşgeldin ayarlarını al
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT channel_id, message FROM welcome WHERE guild_id=?", (str(guild.id),))
    result = c.fetchone()
    conn.close()
    
    if result:
        channel_id, message = result
        channel = guild.get_channel(int(channel_id))
        
        if channel:
            final_msg = message.replace('{user}', member.mention).replace('{server}', guild.name).replace('{count}', str(guild.member_count))
            
            embed = discord.Embed(
                description=final_msg,
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            await channel.send(embed=embed)

# ==================== RPG SİSTEMİ ====================
RPG_ITEMS = {
    # Silahlar
    'wooden_sword': {'name': 'Tahta Kılıç', 'type': 'weapon', 'attack': 5, 'price': 50},
    'iron_sword': {'name': 'Demir Kılıç', 'type': 'weapon', 'attack': 15, 'price': 200},
    'steel_sword': {'name': 'Çelik Kılıç', 'type': 'weapon', 'attack': 30, 'price': 500},
    'mythril_sword': {'name': '✨ Mithril Kılıç', 'type': 'weapon', 'attack': 50, 'price': 1200},
    # Zırhlar
    'leather_armor': {'name': 'Deri Zırh', 'type': 'armor', 'defense': 5, 'price': 75},
    'iron_armor': {'name': 'Demir Zırh', 'type': 'armor', 'defense': 15, 'price': 250},
    'dragon_scale_armor': {'name': '🐉 Ejderha Pulu Zırh', 'type': 'armor', 'defense': 30, 'price': 1500},
    # Tüketilebilir
    'health_potion': {'name': 'Can İksiri', 'type': 'consumable', 'heal': 50, 'price': 30},
    'super_health_potion': {'name': 'Süper Can İksiri', 'type': 'consumable', 'heal': 100, 'price': 70}
}

RPG_ENEMIES = {
    'slime': {'name': '🟢 Slime', 'hp': 30, 'attack': 5, 'gold': 20, 'xp': 15},
    'goblin': {'name': '👺 Goblin', 'hp': 50, 'attack': 10, 'gold': 40, 'xp': 30},
    'skeleton': {'name': '💀 İskelet', 'hp': 70, 'attack': 15, 'gold': 50, 'xp': 45},
    'giant_spider': {'name': '🕷️ Dev Örümcek', 'hp': 80, 'attack': 18, 'gold': 60, 'xp': 50},
    'orc': {'name': '🧟 Orc', 'hp': 100, 'attack': 20, 'gold': 80, 'xp': 60},
    'wizard': {'name': '🧙 Büyücü', 'hp': 60, 'attack': 30, 'gold': 100, 'xp': 75},
    'dragon': {'name': '🐉 Ejderha', 'hp': 300, 'attack': 50, 'gold': 500, 'xp': 200}
}

def get_rpg_profile(user_id):
    """RPG profilini al"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM rpg WHERE user_id=?", (str(user_id),))
    result = c.fetchone()
    
    if not result:
        c.execute("INSERT INTO rpg (user_id) VALUES (?)", (str(user_id),))
        conn.commit()
        c.execute("SELECT * FROM rpg WHERE user_id=?", (str(user_id),))
        result = c.fetchone()
    
    conn.close()
    
    return {
        'user_id': result[0],
        'hp': result[1],
        'max_hp': result[2],
        'attack': result[3],
        'defense': result[4],
        'gold': result[5],
        'inventory': json.loads(result[6]),
        'equipped': json.loads(result[7]),
        'location': result[8]
    }

def update_rpg_profile(user_id, profile):
    """RPG profilini güncelle"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""UPDATE rpg SET hp=?, max_hp=?, attack=?, defense=?, gold=?, inventory=?, equipped=?, location=?
                 WHERE user_id=?""",
              (profile['hp'], profile['max_hp'], profile['attack'], profile['defense'], 
               profile['gold'], json.dumps(profile['inventory']), json.dumps(profile['equipped']), 
               profile['location'], str(user_id)))
    conn.commit()
    conn.close()

@bot.command()
async def profile(ctx):
    """RPG profilini göster"""
    profile = get_rpg_profile(ctx.author.id)
    
    # Ekipman bonusları
    total_attack = profile['attack']
    total_defense = profile['defense']
    
    if profile['equipped'].get('weapon'):
        item = RPG_ITEMS.get(profile['equipped']['weapon'])
        if item:
            total_attack += item['attack']
    
    if profile['equipped'].get('armor'):
        item = RPG_ITEMS.get(profile['equipped']['armor'])
        if item:
            total_defense += item['defense']
    
    embed = discord.Embed(
        title=f"⚔️ {ctx.author.name} - RPG Profil",
        color=0x8B0000
    )
    embed.add_field(name="❤️ Can", value=f"{profile['hp']}/{profile['max_hp']}", inline=True)
    embed.add_field(name="⚔️ Saldırı", value=str(total_attack), inline=True)
    embed.add_field(name="🛡️ Savunma", value=str(total_defense), inline=True)
    embed.add_field(name="💰 Altın", value=str(profile['gold']), inline=True)
    embed.add_field(name="📍 Konum", value=profile['location'].title(), inline=True)
    
    # Ekipman
    weapon = profile['equipped'].get('weapon', 'Yok')
    armor = profile['equipped'].get('armor', 'Yok')
    if weapon != 'Yok':
        weapon = RPG_ITEMS[weapon]['name']
    if armor != 'Yok':
        armor = RPG_ITEMS[armor]['name']
    
    embed.add_field(name="🗡️ Ekipman", value=f"Silah: {weapon}\nZırh: {armor}", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def adventure(ctx):
    """Maceraya çık!"""
    profile = get_rpg_profile(ctx.author.id)
    
    if profile['hp'] <= 0:
        return await ctx.send("❌ Canın bitmiş! `!heal` kullan.")
    
    # Random düşman
    enemy_key = random.choice(list(RPG_ENEMIES.keys()))
    enemy = RPG_ENEMIES[enemy_key].copy()
    
    # Ekipman bonusları
    total_attack = profile['attack']
    total_defense = profile['defense']
    
    if profile['equipped'].get('weapon'):
        item = RPG_ITEMS.get(profile['equipped']['weapon'])
        if item:
            total_attack += item['attack']
    
    if profile['equipped'].get('armor'):
        item = RPG_ITEMS.get(profile['equipped']['armor'])
        if item:
            total_defense += item['defense']
    
    # Savaş simülasyonu
    player_hp = profile['hp']
    enemy_hp = enemy['hp']
    
    battle_log = f"⚔️ **Savaş Başladı: {enemy['name']}**\n\n"
    
    turn = 0
    while player_hp > 0 and enemy_hp > 0 and turn < 20:
        turn += 1
        
        # Oyuncu saldırısı
        damage = max(1, total_attack - random.randint(0, 5))
        enemy_hp -= damage
        battle_log += f"➡️ {damage} hasar verdin! ({enemy['name']} HP: {max(0, enemy_hp)})\n"
        
        if enemy_hp <= 0:
            break
        
        # Düşman saldırısı
        enemy_damage = max(1, enemy['attack'] - total_defense)
        player_hp -= enemy_damage
        battle_log += f"⬅️ {enemy_damage} hasar aldın! (HP: {max(0, player_hp)})\n"
    
    # Sonuç
    if player_hp > 0:
        # Kazandın!
        profile['hp'] = player_hp
        profile['gold'] += enemy['gold']
        
        # XP ekle
        add_xp(ctx.author.id, enemy['xp'])
        
        # Random item düşmesi (%30 şans)
        loot = ""
        if random.random() < 0.3:
            item_key = random.choice(list(RPG_ITEMS.keys()))
            if item_key in profile['inventory']:
                profile['inventory'][item_key] += 1
            else:
                profile['inventory'][item_key] = 1
            loot = f"\n🎁 **{RPG_ITEMS[item_key]['name']}** buldun!"
        
        embed = discord.Embed(
            title="🎉 Zafer!",
            description=battle_log + f"\n✅ **Kazandın!**\n💰 +{enemy['gold']} altın\n✨ +{enemy['xp']} XP{loot}",
            color=0x00ff00
        )
    else:
        # Kaybettin
        profile['hp'] = 0
        lost_gold = min(profile['gold'], enemy['gold'])
        profile['gold'] -= lost_gold
        
        embed = discord.Embed(
            title="💀 Yenildin!",
            description=battle_log + f"\n❌ **Kaybettin!**\n💸 -{lost_gold} altın kaybettin\n❤️ Canın bitti!",
            color=0xff0000
        )
    
    update_rpg_profile(ctx.author.id, profile)
    await ctx.send(embed=embed)

@bot.command()
async def shop(ctx):
    """RPG dükkanı"""
    embed = discord.Embed(
        title="🏪 RPG Dükkanı",
        description="Eşya satın almak için: `!buy item_adı`",
        color=0xffd700
    )
    
    for item_key, item in RPG_ITEMS.items():
        stats = ""
        if 'attack' in item:
            stats += f"⚔️ +{item['attack']} Saldırı"
        if 'defense' in item:
            stats += f"🛡️ +{item['defense']} Savunma"
        if 'heal' in item:
            stats += f"❤️ +{item['heal']} Can"
        
        embed.add_field(
            name=f"{item['name']} - 💰 {item['price']} altın",
            value=f"`{item_key}` • {stats}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command()
async def buy(ctx, item_key: str):
    """Dükkanından eşya al"""
    if item_key not in RPG_ITEMS:
        return await ctx.send(f"❌ Bu eşya yok! `!shop` ile bak.")
    
    item = RPG_ITEMS[item_key]
    profile = get_rpg_profile(ctx.author.id)
    
    if profile['gold'] < item['price']:
        return await ctx.send(f"❌ Yetersiz altın! Gereken: {item['price']}, Var: {profile['gold']}")
    
    # Satın al
    profile['gold'] -= item['price']
    if item_key in profile['inventory']:
        profile['inventory'][item_key] += 1
    else:
        profile['inventory'][item_key] = 1
    
    update_rpg_profile(ctx.author.id, profile)
    
    embed = discord.Embed(
        title="✅ Satın Alındı!",
        description=f"**{item['name']}** satın aldın!\n💰 Kalan altın: {profile['gold']}",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
async def inventory(ctx):
    """Envanterini göster"""
    profile = get_rpg_profile(ctx.author.id)
    
    if not profile['inventory']:
        return await ctx.send("❌ Envanterın boş! `!shop` ile eşya satın al.")
    
    embed = discord.Embed(
        title=f"🎒 {ctx.author.name} - Envanter",
        color=0x8B4513
    )
    
    for item_key, count in profile['inventory'].items():
        if item_key in RPG_ITEMS:
            item = RPG_ITEMS[item_key]
            embed.add_field(
                name=f"{item['name']} x{count}",
                value=f"`!equip {item_key}` veya `!use {item_key}`",
                inline=False
            )
    
    await ctx.send(embed=embed)

@bot.command()
async def equip(ctx, item_key: str):
    """Eşya kuşan"""
    profile = get_rpg_profile(ctx.author.id)
    
    if item_key not in profile['inventory'] or profile['inventory'][item_key] <= 0:
        return await ctx.send("❌ Bu eşya envanterinde yok!")
    
    if item_key not in RPG_ITEMS:
        return await ctx.send("❌ Bu eşya kuşanılamaz!")
    
    item = RPG_ITEMS[item_key]
    
    if item['type'] == 'weapon':
        profile['equipped']['weapon'] = item_key
        await ctx.send(f"⚔️ **{item['name']}** kuşandın! (+{item['attack']} saldırı)")
    elif item['type'] == 'armor':
        profile['equipped']['armor'] = item_key
        await ctx.send(f"🛡️ **{item['name']}** kuşandın! (+{item['defense']} savunma)")
    else:
        return await ctx.send("❌ Bu eşya kuşanılamaz! `!use` dene.")
    
    update_rpg_profile(ctx.author.id, profile)

@bot.command()
async def use(ctx, item_key: str):
    """Eşya kullan (iksir vs)"""
    profile = get_rpg_profile(ctx.author.id)
    
    if item_key not in profile['inventory'] or profile['inventory'][item_key] <= 0:
        return await ctx.send("❌ Bu eşya envanterinde yok!")
    
    if item_key not in RPG_ITEMS:
        return await ctx.send("❌ Bilinmeyen eşya!")
    
    item = RPG_ITEMS[item_key]
    
    if item['type'] != 'consumable':
        return await ctx.send("❌ Bu eşya kullanılamaz! Kuşanılabilir eşya için `!equip` kullan.")
    
    # İksir kullan
    if 'heal' in item:
        old_hp = profile['hp']
        profile['hp'] = min(profile['max_hp'], profile['hp'] + item['heal'])
        healed = profile['hp'] - old_hp
        
        profile['inventory'][item_key] -= 1
        if profile['inventory'][item_key] == 0:
            del profile['inventory'][item_key]
        
        update_rpg_profile(ctx.author.id, profile)
        await ctx.send(f"❤️ **{item['name']}** kullandın! +{healed} can (HP: {profile['hp']}/{profile['max_hp']})")

@bot.command()
async def heal(ctx):
    """Canını tamamen iyileştir (50 altın)"""
    profile = get_rpg_profile(ctx.author.id)
    
    if profile['hp'] >= profile['max_hp']:
        return await ctx.send("❤️ Canın zaten dolu!")
    
    cost = 50
    if profile['gold'] < cost:
        return await ctx.send(f"❌ Yetersiz altın! Gereken: {cost}, Var: {profile['gold']}")
    
    profile['hp'] = profile['max_hp']
    profile['gold'] -= cost
    
    update_rpg_profile(ctx.author.id, profile)
    await ctx.send(f"❤️ Canın tamamen iyileşti! ({profile['max_hp']}/{profile['max_hp']}) -50 altın")

# ==================== GELİŞMİŞ MÜZİK SİSTEMİ ====================
# NOT: FFmpeg ve yt-dlp kurulumu gerekli! (Rehbere bakın)

try:
    ytdl_format_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }
    
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }
    
    ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
    
    class YTDLSource(discord.PCMVolumeTransformer):
        def __init__(self, source, *, data, volume=0.5):
            super().__init__(source, volume)
            self.data = data
            self.title = data.get('title')
            self.url = data.get('url')
            self.webpage_url = data.get('webpage_url')
        
        @classmethod
        async def from_url(cls, url, *, loop=None):
            loop = loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            filename = data['url']
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
    
    MUSIC_ENABLED = True

except ImportError:
    MUSIC_ENABLED = False
    print("⚠️ yt-dlp bulunamadı! Müzik özellikleri devre dışı.")
    print("Kurulum: pip install yt-dlp PyNaCl")

@bot.command()
async def join(ctx):
    """Sesli kanala katıl"""
    if not ctx.author.voice:
        return await ctx.send("❌ Önce bir sesli kanala katıl!")
    
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    await ctx.send(f"✅ {channel.name} kanalına katıldım!")

@bot.command()
async def leave(ctx):
    """Sesli kanaldan ayrıl"""
    if ctx.voice_client:
        guild_id = ctx.guild.id
        music_queues.pop(guild_id, None)
        now_playing.pop(guild_id, None)
        loop_mode.pop(guild_id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Sesli kanaldan ayrıldım!")
    else:
        await ctx.send("❌ Zaten sesli kanalda değilim!")

if MUSIC_ENABLED:
    async def play_music(ctx):
        """Sıradaki şarkıyı çalan ve kuyruğu yöneten ana fonksiyon"""
        guild_id = ctx.guild.id
        if guild_id in music_queues and music_queues[guild_id]:
            try:
                # Loop modu kontrolü
                if loop_mode.get(guild_id) == 'song' and guild_id in now_playing:
                    music_queues[guild_id].appendleft(now_playing[guild_id]['url'])
                elif loop_mode.get(guild_id) == 'queue' and guild_id in now_playing:
                    music_queues[guild_id].append(now_playing[guild_id]['url'])

                url = music_queues[guild_id].popleft()
                player = await YTDLSource.from_url(url, loop=bot.loop)
                now_playing[guild_id] = {'title': player.title, 'url': url}

                # Şarkı bittiğinde bu fonksiyonu tekrar çağırmak için 'after' callback'i
                ctx.voice_client.play(player, after=lambda e: bot.loop.create_task(play_music(ctx)))

                embed = discord.Embed(title="🎵 Şimdi Çalıyor", description=f"**{player.title}**", color=0x00ff00)
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"❌ Şarkı çalınırken hata: {e}")
                await play_music(ctx)  # Hata olursa sıradaki şarkıyı dene
        else:
            # Kuyruk boşaldı
            now_playing.pop(guild_id, None)

    @bot.command()
    async def play(ctx, *, url):
        """Müzik çal - YouTube URL veya arama"""
        if not MUSIC_ENABLED:
            return await ctx.send("❌ Müzik sistemi devre dışı! yt-dlp ve FFmpeg kur.")

        if not ctx.author.voice:
            return await ctx.send("❌ Önce sesli kanala katıl!")

        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()

        guild_id = ctx.guild.id

        async with ctx.typing():
            try:
                # Arama terimi veya URL'den şarkı bilgilerini al
                info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{url}", download=False)['entries'][0])
                title = info.get('title', 'Bilinmeyen Şarkı')
                webpage_url = info.get('webpage_url', url)

                if guild_id not in music_queues:
                    music_queues[guild_id] = deque()
                music_queues[guild_id].append(webpage_url)

                if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                    embed = discord.Embed(
                        title="➕ Kuyruğa Eklendi",
                        description=f"**{title}**\nSıra: {len(music_queues[guild_id])}",
                        color=0x00ff00
                    )
                    await ctx.send(embed=embed)
                else:
                    # Çalan bir şey yoksa, kuyruğu başlat
                    await play_music(ctx)
            except Exception as e:
                await ctx.send(f"❌ Hata: Şarkı bulunamadı veya yüklenemedi.\n`{e}`")

    @bot.command()
    async def skip(ctx):
        """Şarkıyı atla"""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ Şu an müzik çalmıyor!")
        
        ctx.voice_client.stop()
        await ctx.send("⏭️ Şarkı atlandı!")
    
    @bot.command()
    async def pause(ctx):
        """Müziği duraklat"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Duraklatıldı")
        else:
            await ctx.send("❌ Şu an müzik çalmıyor!")
    
    @bot.command()
    async def resume(ctx):
        """Müziği devam ettir"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Devam ediyor")
        else:
            await ctx.send("❌ Müzik duraklı değil!")
    
    @bot.command()
    async def stop(ctx):
        """Müziği durdur ve kuyruğu temizle"""
        if ctx.voice_client:
            guild_id = ctx.guild.id
            music_queues.pop(guild_id, None)
            now_playing.pop(guild_id, None)
            ctx.voice_client.stop()
            await ctx.send("⏹️ Durduruldu ve kuyruk temizlendi")
    
    @bot.command()
    async def queue(ctx):
        """Müzik kuyruğunu göster"""
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues or len(music_queues[guild_id]) == 0:
            if guild_id in now_playing:
                embed = discord.Embed(
                    title="🎵 Şimdi Çalıyor",
                    description=f"**{now_playing[guild_id]['title']}**\n\nKuyruk boş",
                    color=0x00ff00
                )
                return await ctx.send(embed=embed)
            else:
                return await ctx.send("❌ Kuyruk boş!")
        
        embed = discord.Embed(
            title="📜 Müzik Kuyruğu",
            color=0x00ff00
        )
        
        if guild_id in now_playing:
            embed.add_field(
                name="🎵 Şimdi Çalıyor",
                value=now_playing[guild_id]['title'],
                inline=False
            )
        
        queue_list = ""
        for i, url in enumerate(list(music_queues[guild_id])[:10], 1):
            queue_list += f"{i}. Sıradaki şarkı\n"
        
        embed.add_field(
            name=f"📝 Kuyruk ({len(music_queues[guild_id])} şarkı)",
            value=queue_list or "Boş",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @bot.command()
    async def loop(ctx, mode: str = None):
        """Loop modu (off/song/queue)"""
        if not mode:
            return await ctx.send("❌ Kullanım: `!loop off/song/queue`\n**off** = Kapalı\n**song** = Şarkıyı tekrarla\n**queue** = Kuyruğu tekrarla")
        
        mode = mode.lower()
        if mode not in ['off', 'song', 'queue']:
            return await ctx.send("❌ Geçersiz mod! off/song/queue")
        
        guild_id = ctx.guild.id
        
        if mode == 'off':
            loop_mode.pop(guild_id, None)
            await ctx.send("🔁 Loop kapatıldı")
        else:
            loop_mode[guild_id] = mode
            if mode == 'song':
                await ctx.send("🔂 Şarkı tekrarlama açık")
            else:
                await ctx.send("🔁 Kuyruk tekrarlama açık")
    
    @bot.command()
    async def nowplaying(ctx):
        """Şu an çalan şarkı"""
        guild_id = ctx.guild.id
        
        if guild_id not in now_playing:
            return await ctx.send("❌ Şu an müzik çalmıyor!")
        
        embed = discord.Embed(
            title="🎵 Şimdi Çalıyor",
            description=f"**{now_playing[guild_id]['title']}**",
            color=0x00ff00
        )
        
        if guild_id in loop_mode:
            if loop_mode[guild_id] == 'song':
                embed.set_footer(text="🔂 Şarkı tekrarlama açık")
            elif loop_mode[guild_id] == 'queue':
                embed.set_footer(text="🔁 Kuyruk tekrarlama açık")
        
        await ctx.send(embed=embed)
    
    @bot.command()
    async def volume(ctx, vol: int):
        """Ses seviyesi (0-100)"""
        if not ctx.voice_client:
            return await ctx.send("❌ Bot sesli kanalda değil!")
        
        if not 0 <= vol <= 100:
            return await ctx.send("❌ 0-100 arası değer gir!")
        
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = vol / 100
            await ctx.send(f"🔊 Ses: **{vol}%**")
        else:
            await ctx.send("❌ Şu an müzik çalmıyor!")

# ==================== YARDIM KOMUTU ====================
@bot.command()
async def help(ctx):
    """Yardım menüsü"""
    embed = discord.Embed(
        title="🤖 MEGA BOT - Komutlar",
        description="Tüm özellikler ve komutlar",
        color=0x00ff00
    )
    
    embed.add_field(
        name="📊 Seviye Sistemi",
        value="`!rank [@kullanıcı]` - Seviye/XP\n`!leaderboard` - Sıralama",
        inline=False
    )
    
    embed.add_field(
        name="🌤️ Bilgi Komutları",
        value="`!weather şehir` - Hava durumu\n`!crypto bitcoin` - Kripto fiyat",
        inline=False
    )
    
    embed.add_field(
        name="😂 Eğlence",
        value="`!meme` - Random meme\n`!dog` - Random köpek\n`!cat` - Random kedi",
        inline=False
    )
    
    embed.add_field(
        name="🎮 Oyunlar",
        value="`!taşkağıtmakas taş/kağıt/makas` - RPS\n`!8ball soru` - Sihirli 8-ball",
        inline=False
    )
    
    embed.add_field(
        name="🎫 Ticket Sistemi (ADMIN)",
        value="`!ticketsetup` - Sistemi kur\n`!ticket` - Destek talebi aç\n`!close` - Ticket kapat",
        inline=False
    )
    
    embed.add_field(
        name="👋 Hoşgeldin (ADMIN)",
        value="`!welcomesetup #kanal mesaj` - Hoşgeldin ayarla",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ RPG Sistemi",
        value="`!profile` - Profilin\n`!adventure` - Macera!\n`!shop` - Dükkan\n`!buy item` - Satın al\n`!inventory` - Envanter\n`!equip item` - Kuşan\n`!use item` - Kullan\n`!heal` - İyileş",
        inline=False
    )
    
    if MUSIC_ENABLED:
        embed.add_field(
            name="🎵 Müzik",
            value="`!join` - Kanala katıl\n`!play url/arama` - Çal\n`!pause/resume` - Duraklat/Devam\n`!skip` - Atla\n`!stop` - Durdur\n`!queue` - Kuyruk\n`!loop off/song/queue` - Tekrarla\n`!nowplaying` - Şu an çalan\n`!volume 0-100` - Ses",
            inline=False
        )
    else:
        embed.add_field(
            name="🎵 Müzik (Devre Dışı)",
            value="yt-dlp ve FFmpeg kur!",
            inline=False
        )
    
    embed.set_footer(text=f"Prefix: {PREFIX} • Bot sürekli gelişiyor!")
    
    await ctx.send(embed=embed)

# ==================== BOT EVENTLER ====================
@bot.event
async def on_ready():
    """Bot başladığında"""
    init_db()
    print(f'🚀 MEGA BOT AKTİF!')
    print(f'📊 İsim: {bot.user.name}')
    print(f'🆔 ID: {bot.user.id}')
    print(f'🌐 {len(bot.guilds)} sunucuda')
    print('✅ Tüm sistemler çalışıyor!')
    
    if not MUSIC_ENABLED:
        print("⚠️ Müzik sistemi devre dışı! (yt-dlp kur)")
    
    # Slash komutları sync
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} slash komut yüklendi")
    except Exception as e:
        print(f"Slash sync hatası: {e}")
    
    # Status loop
    if not status_loop.is_running():
        status_loop.start()

@tasks.loop(minutes=5)
async def status_loop():
    """Bot durumunu değiştir"""
    statuses = [
        discord.Activity(type=discord.ActivityType.listening, name="🎵 Müzik"),
        discord.Activity(type=discord.ActivityType.playing, name="⚔️ RPG"),
        discord.Game(f"📊 {len(bot.guilds)} sunucu"),
        discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}help")
    ]
    await bot.change_presence(activity=random.choice(statuses))

@bot.event
async def on_command_error(ctx, error):
    """Hata yönetimi"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yetkin yok!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Eksik parametre! `{PREFIX}help` yaz")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Bilinmeyen komutları yoksay
    else:
        print(f"Hata: {error}")

# ==================== SLASH KOMUTLARI ====================
@bot.tree.command(name="ping", description="Bot gecikmesi")
async def ping_slash(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! **{latency}ms**")

@bot.tree.command(name="rank", description="Seviye ve XP göster")
async def rank_slash(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT xp, level FROM levels WHERE user_id=?", (str(interaction.user.id),))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await interaction.response.send_message("❌ Henüz mesaj atmamışsın!", ephemeral=True)
    else:
        xp, level = result
        await interaction.response.send_message(f"📊 Level **{level}** • {xp:,} XP")

# ==================== BOTU ÇALIŞTIR ====================
if __name__ == "__main__":
    print("🔄 MEGA BOT başlatılıyor...")
    print("=" * 50)
    try:
        bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("❌ HATA: Intentler kapalı! Discord Developer Portal'dan 'Message Content Intent' açmalısın.")
    except discord.errors.LoginFailure:
        print("❌ HATA: Token geçersiz! Token'ı kontrol et.")
    except Exception as e:
        print(f"❌ HATA: {e}")
