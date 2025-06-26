#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IST-Optimized Auto Story Bot
Version: 2.1
Author: Saidul M.
"""

import os
import time
import gspread
import requests
import schedule
import random
import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential

# -------------------- কনফিগারেশন -------------------- #
os.environ['TZ'] = 'Asia/Kolkata'
time.tzset()

# লগিং সেটআপ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# এনভায়রনমেন্ট ভেরিয়েবল
CONFIG = {
    "SHEET_ID": os.environ['SHEET_ID'],
    "BOT_TOKEN": os.environ['BOT_TOKEN'],
    "CHANNEL_NAME": os.environ['CHANNEL_NAME'],
    "CREDS_FILE": 'credentials.json'
}

# -------------------- ডেটা সোর্স -------------------- #

TRUSTED_SOURCES = {
    "english": [
        {"url": "https://www.gutenberg.org/ebooks/search/?query=short+stories", "parser": "p"},
        {"url": "https://www.freechildrenstories.com/", "parser": ".entry-content"},
        {"url": "https://americanliterature.com/short-short-stories", "parser": "article"}
    ],
    "bengali": [
        {"url": "https://www.bangla-gobol.com/", "parser": ".story-content"},
        {"url": "https://www.bangla-kobita.com/golpo/", "parser": ".post-content"}
    ],
    "hindi": [
        {"url": "https://hindikahaniyan.com/", "parser": ".entry-content"},
        {"url": "https://kavitakosh.org/", "parser": ".poem"}
    ]
}

BLACKLIST_WORDS = [
    "adult", "porn", "xxx", "sex", "nude",
    "অশ্লীল", "যৌন", "পর্ণ", "নগ্ন",
    "अश्लील", "यौन", "पोर्न", "नग्न"
]

# -------------------- ইউটিলিটি ফাংশন -------------------- #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def auth_gspread():
    """গুগল শিট অথেন্টিকেশন (রিট্রি মেকানিজম সহ)"""
    try:
        creds = Credentials.from_service_account_file(CONFIG['CREDS_FILE'])
        return gspread.authorize(creds)
    except Exception as e:
        logging.error(f"Auth Error: {e}")
        raise

def is_valid_content(text):
    """কন্টেন্ট ভ্যালিডেশন চেক"""
    text = text.lower()
    return (
        100 <= len(text.split()) <= 500 and
        not any(word in text for word in BLACKLIST_WORDS) and
        not any(url in text for url in ["http://", "https://"])
    )

# -------------------- মূল ফাংশনালিটি -------------------- #

async def fetch_stories(language):
    """ওয়েব থেকে গল্প সংগ্রহ"""
    try:
        sources = TRUSTED_SOURCES.get(language, [])
        if not sources:
            logging.warning(f"No sources found for {language}")
            return None

        for source in random.sample(sources, len(sources)):
            try:
                response = requests.get(source['url'], timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                elements = soup.select(source['parser'])
                
                stories = [el.get_text().strip() for el in elements if is_valid_content(el.get_text())]
                
                if stories:
                    return random.choice(stories)
                    
            except Exception as e:
                logging.warning(f"Source Error ({source['url']}): {e}")
                continue

        return None
    except Exception as e:
        logging.error(f"Fetch Error ({language}): {e}")
        return None

async def update_sheet(story_data):
    """গুগল শিট আপডেট"""
    try:
        gc = auth_gspread()
        sheet = gc.open_by_key(CONFIG['SHEET_ID'])
        worksheet = sheet.worksheet(story_data['language'].capitalize())
        
        worksheet.append_row([
            story_data['title'],
            story_data['content'],
            story_data['category'],
            story_data['source'],
            "✗",
            "",
            story_data['emoji']
        ])
        return True
    except Exception as e:
        logging.error(f"Sheet Update Error: {e}")
        return False

async def post_to_telegram():
    """টেলিগ্রামে পোস্ট পাঠানো"""
    try:
        bot = Bot(token=CONFIG['BOT_TOKEN'])
        languages = ['english', 'bengali', 'hindi']
        
        for language in random.sample(languages, len(languages)):
            try:
                story = await fetch_stories(language)
                if not story:
                    continue
                
                categories = {
                    "english": ["Fairy Tale", "Adventure", "Sci-Fi"],
                    "bengali": ["পরীর গল্প", "অ্যাডভেঞ্চার", "বিজ্ঞান কল্পকাহিনী"],
                    "hindi": ["परी कथा", "रोमांच", "विज्ञान कथा"]
                }
                
                emoji_map = {
                    "Fairy Tale": "🧚", "Adventure": "🏞️", "Sci-Fi": "🚀",
                    "পরীর গল্প": "🧚", "অ্যাডভেঞ্চার": "🏞️", "বিজ্ঞান কল্পকাহিনী": "🚀",
                    "परी कथा": "🧚", "रोमांच": "🏞️", "विज्ञान कथा": "🚀"
                }
                
                category = random.choice(categories[language])
                emoji = emoji_map.get(category, "📖")
                title = f"{category} {random.randint(1, 100)}"
                
                story_data = {
                    'title': title,
                    'content': story,
                    'category': category,
                    'source': random.choice(TRUSTED_SOURCES[language])['url'],
                    'language': language,
                    'emoji': emoji
                }
                
                if await update_sheet(story_data):
                    message = f"{emoji} *{title}*\n\n{story}\n\n#{category.replace(' ', '_')}"
                    await bot.send_message(
                        chat_id=CONFIG['CHANNEL_NAME'],
                        text=message,
                        parse_mode="MarkdownV2"
                    )
                    logging.info(f"Posted {language} story: {title}")
                    return
                    
            except Exception as e:
                logging.error(f"Language Processing Error ({language}): {e}")
                continue
                
        logging.warning("No valid stories found to post!")
    except Exception as e:
        logging.error(f"Telegram Post Error: {e}")

# -------------------- শিডিউলিং -------------------- #

def setup_scheduler():
    """IST সময় অনুযায়ী শিডিউলার সেটআপ"""
    ist_times = [
        "00:00", "02:00", "04:00", "06:00", "08:00",
        "10:00", "12:00", "14:00", "16:00", "18:00",
        "20:00", "22:00"
    ]
    
    for time_str in ist_times:
        schedule.every().day.at(time_str).do(
            lambda: asyncio.run(post_to_telegram())
        )  # এই বন্ধনীটি যোগ করুন
    
    # প্রতি ৬ ঘণ্টায় ডেটা রিফ্রেশ
    schedule.every(3).hours.do(
        lambda: asyncio.run(fetch_stories(random.choice(['english', 'bengali', 'hindi'])))
    )
# -------------------- মেইন এক্সিকিউশন -------------------- #

if __name__ == "__main__":
    try:
        setup_scheduler()
        logging.info("🤖 Bot Started Successfully (IST Timezone)")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    except KeyboardInterrupt:
        logging.info("🛑 Bot Stopped Manually")
    except Exception as e:
        logging.critical(f"💥 Fatal Error: {e}")
