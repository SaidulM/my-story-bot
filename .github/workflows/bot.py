import os
import gspread
from google.oauth2.service_account import Credentials
import requests
from bs4 import BeautifulSoup
import random
import schedule
import time
from datetime import datetime
import re
from telegram import Bot

# Google Sheets API সেটআপ
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
CREDS_FILE = 'credentials.json'

# এনভায়রনমেন্ট ভেরিয়েবল থেকে মান নিন
SPREADSHEET_ID = os.environ.get('SHEET_ID', '1RWlfyfZjP8TZukX_nzNCg1KTHKvNm4SQy_yfomqYhcs')
TELEGRAM_TOKEN = os.environ.get('BOT_TOKEN', 'default_token')
CHANNEL_NAME = os.environ.get('CHANNEL_NAME', '@default_channel')

# বিশ্বস্ত ওপেন সোর্স ওয়েবসাইট (সমস্যা অনুযায়ী আপডেট করা)
TRUSTED_SOURCES = {
    "english": [
        "https://www.gutenberg.org/ebooks/search/?query=short+stories",
        "https://www.freechildrenstories.com/",
        "https://americanliterature.com/short-short-stories"
    ],
    "bengali": [
        "https://www.bangla-gobol.com/",
        "https://www.bangla-kobita.com/golpo/",
        "https://www.rokomari.com/book/category/1"
    ],
    "hindi": [
        "https://hindikahaniyan.com/",
        "https://kavitakosh.org/",
        "https://www.hindishayari.in/"
    ]
}

# ক্যাটাগরি ম্যাপিং
CATEGORIES = {
    "english": ["Fairy Tale", "Adventure", "Science Fiction", "Mystery", "Poetry"],
    "bengali": ["পরীর গল্প", "অ্যাডভেঞ্চার", "বিজ্ঞান কল্পকাহিনী", "রহস্য", "কবিতা"],
    "hindi": ["परी कथा", "रोमांच", "विज्ञान कथा", "रहस्य", "कविता"]
}

# ইমোজি ম্যাপিং
EMOJI_MAP = {
    "Fairy Tale": "🧚", 
    "Adventure": "🏞️",
    "Science Fiction": "🚀",
    "Mystery": "🔍",
    "Poetry": "📜",
    "পরীর গল্প": "🧚",
    "অ্যাডভেঞ্চার": "🏞️",
    "বিজ্ঞান কল্পকাহিনী": "🚀",
    "রহস্য": "🔍",
    "কবিতা": "📜",
    "परी कथा": "🧚",
    "रोमांच": "🏞️",
    "विज्ञान कथा": "🚀",
    "रहस्य": "🔍",
    "कविता": "📜"
}

# নিষিদ্ধ বিষয়বস্তুর শব্দতালিকা (সমস্ত ভাষার জন্য)
BLACKLIST_WORDS = [
    "adult", "explicit", "porn", "xxx", "sex", "nude",
    "অশ্লীল", "যৌন", "পর্ণ", "নগ্ন", "মাদক",
    "अश्लील", "यौन", "पोर्न", "नग्न", "मादक"
]

def get_google_sheet(sheet_name):
    """গুগল শিট অ্যাক্সেস করার ফাংশন"""
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)
    return sheet.worksheet(sheet_name)

def is_adult_content(text):
    """বয়স-অনুপযুক্ত কন্টেন্ট চেক করার ফাংশন"""
    text_lower = text.lower()
    return any(word in text_lower for word in BLACKLIST_WORDS)

def fetch_stories(language):
    """গল্প সংগ্রহ করার ফাংশন"""
    try:
        worksheet = get_google_sheet(language.capitalize())
        sources = TRUSTED_SOURCES[language]
        category = random.choice(CATEGORIES[language])
        
        for source in sources:
            try:
                print(f"Fetching from {source} for {language}")
                response = requests.get(source, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # গল্প নির্বাচন
                stories = []
                if "gutenberg.org" in source:
                    stories = [p.get_text().strip() for p in soup.select('p') if len(p.get_text().split()) > 50]
                elif "bangla-gobol.com" in source:
                    stories = [div.get_text().strip() for div in soup.select('.story-content')]
                elif "hindikahaniyan.com" in source:
                    stories = [article.get_text().strip() for article in soup.select('.entry-content')]
                else:
                    stories = [p.get_text().strip() for p in soup.find_all('p') if len(p.get_text().split()) > 50]
                
                # গল্প ফিল্টারিং
                valid_stories = []
                for story in stories:
                    words = story.split()
                    word_count = len(words)
                    if (100 <= word_count <= 500 and 
                        not is_adult_content(story) and 
                        not any(url in story for url in ["http://", "https://"])):
                        valid_stories.append(story)
                
                if valid_stories:
                    selected_story = random.choice(valid_stories)
                    title = f"{category} গল্প {random.randint(1, 100)}"[:50]
                    
                    # ডুপ্লিকেট চেক (হেডার বাদ দিন)
                    existing_titles = worksheet.col_values(1)[1:]  
                    if title not in existing_titles:
                        emoji = EMOJI_MAP.get(category, "📖")
                        worksheet.append_row([
                            title,
                            selected_story,
                            category,
                            source,
                            "✗",
                            "",
                            emoji
                        ])
                        print(f"Added new {language} story: {title}")
                        return True
            except Exception as e:
                print(f"Error fetching from {source}: {str(e)}")
    except Exception as e:
        print(f"Error in fetch_stories for {language}: {str(e)}")
    return False

def post_to_telegram():
    """টেলিগ্রামে গল্প পোস্ট করার ফাংশন"""
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        
        for language in ["English", "Bengali", "Hindi"]:
            try:
                worksheet = get_google_sheet(language)
                records = worksheet.get_all_records()
                
                for record in records:
                    if record.get('Posted') == "✗":
                        title = record['Title']
                        content = record['Content']
                        category = record['Category']
                        emoji = record['Emoji']
                        
                        message = (
                            f"{emoji} *{title}* {emoji}\n\n"
                            f"{content}\n\n"
                            f"{emoji} #{category.replace(' ', '_')}"
                        )
                        
                        # 4096 ক্যারেক্টারের বেশি হলে ভাগ করে পোস্ট করুন
                        if len(message) > 4096:
                            part1 = message[:4000]
                            last_newline = part1.rfind('\n')
                            if last_newline != -1:
                                part1 = message[:last_newline]
                            
                            bot.send_message(chat_id=CHANNEL_NAME, text=part1, parse_mode="Markdown")
                            bot.send_message(chat_id=CHANNEL_NAME, text=message[last_newline:], parse_mode="Markdown")
                        else:
                            bot.send_message(chat_id=CHANNEL_NAME, text=message, parse_mode="Markdown")
                        
                        # পোস্ট স্ট্যাটাস আপডেট করুন
                        cell = worksheet.find(title, in_column=1)
                        worksheet.update_cell(cell.row, 5, "✓")
                        worksheet.update_cell(cell.row, 6, datetime.now().strftime("%Y-%m-%d %H:%M"))
                        print(f"Posted {language} story: {title}")
                        return
            except Exception as e:
                print(f"Error posting {language} story: {str(e)}")
    except Exception as e:
        print(f"Error in post_to_telegram: {str(e)}")

def main():
    """মেইন ফাংশন"""
    # বাংলাদেশ সময় UTC+6, তাই UTC সময়ে শিডিউল সেট করুন
    post_times = ["00:00", "02:00", "04:00", "06:00", "08:00", "10:00", "12:00", "14:00", "16:00"]
    
    for time_str in post_times:
        schedule.every().day.at(time_str).do(post_to_telegram)
    
    # প্রতি ৬ ঘণ্টায় নতুন গল্প সংগ্রহ
    schedule.every(6).hours.do(lambda: fetch_stories("english"))
    schedule.every(6).hours.do(lambda: fetch_stories("bengali"))
    schedule.every(6).hours.do(lambda: fetch_stories("hindi"))
    
    print("Bot started successfully! Waiting for scheduled tasks...")
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
