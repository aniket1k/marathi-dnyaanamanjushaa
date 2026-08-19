import os
import json
import hashlib
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import feedparser
from google import genai


# -----------------------------
# CONFIG
# -----------------------------

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

# Official PIB RSS feed
PIB_FEED = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"

# Generate only a small number each day
QUESTIONS_PER_RUN = 5

HEADERS = {
    "User-Agent": "MarathiQuizUpdater/1.0"
}


# -----------------------------
# GEMINI
# -----------------------------

client = genai.Client(api_key=GEMINI_API_KEY)


# -----------------------------
# SUPABASE
# -----------------------------

REST_URL = f"{SUPABASE_URL.rstrip('/')}/rest/v1/questions"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


# -----------------------------
# FETCH OFFICIAL NEWS
# -----------------------------

def fetch_news():

    feed = feedparser.parse(PIB_FEED)

    articles = []

    for item in feed.entries[:15]:

        title = item.get("title", "").strip()
        summary = item.get("summary", "").strip()
        link = item.get("link", "").strip()

        if not title or not link:
            continue

        articles.append({
            "title": title,
            "summary": summary,
            "link": link
        })

    return articles


# -----------------------------
# GET EXISTING QUESTIONS
# -----------------------------

def get_existing_questions():

    params = {
        "select": "question",
        "limit": "5000"
    }

    response = requests.get(
        REST_URL,
        headers=SUPABASE_HEADERS,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return {
        row["question"].strip().lower()
        for row in response.json()
        if row.get("question")
    }


# -----------------------------
# GENERATE QUESTIONS
# -----------------------------

def generate_questions(articles):

    today = datetime.now(timezone.utc).date().isoformat()

    source_text = json.dumps(
        articles,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
तुम्ही एक अत्यंत काळजीपूर्वक fact-checking quiz editor आहात.

खाली Press Information Bureau (PIB) च्या
अधिकृत RSS feed मधील ताज्या releases दिल्या आहेत.

फक्त खाली दिलेल्या माहितीवर आधारित प्रश्न तयार करा.
स्वतःहून तथ्य बनवू नका.

भाषा:
मराठी.

एकूण:
{QUESTIONS_PER_RUN} प्रश्न.

स्तर:
Intermediate ते Difficult.

विषय:
Current Affairs.

नियम:

1. प्रत्येक प्रश्नाला 4 पर्याय असावेत.
2. फक्त एकच पर्याय बरोबर असावा.
3. correct_answer हा 0,1,2,3 पैकी integer असावा.
4. प्रश्न तथ्यात्मक आणि स्पष्ट असावा.
5. ambiguous प्रश्न देऊ नका.
6. अतिशय सोपे प्रश्न टाळा.
7. उत्तरासाठी source article मध्ये स्पष्ट आधार असावा.
8. प्रत्येक प्रश्नासाठी 1-2 वाक्यांचे मराठी explanation द्या.
9. Source मध्ये दिलेली article URL वापरा.
10. काल्पनिक source तयार करू नका.
11. जुन्या सामान्यज्ञानावरून प्रश्न तयार करू नका; या feed मधील current information वापरा.
12. प्रश्नात "PIB नुसार" असे आवश्यक नसल्यास लिहू नका.
13. प्रश्नांमध्ये वेगवेगळ्या मंत्रालये/घडामोडी cover करण्याचा प्रयत्न करा.

आजची तारीख:
{today}

खालील JSON structure मध्येच उत्तर द्या:

{{
  "questions": [
    {{
      "question": "मराठी प्रश्न",
      "options": [
        "पर्याय 1",
        "पर्याय 2",
        "पर्याय 3",
        "पर्याय 4"
      ],
      "correct_answer": 0,
      "category": "Current Affairs",
      "difficulty": "Intermediate",
      "explanation": "मराठीत थोडक्यात स्पष्टीकरण.",
      "source": "पूर्ण article URL",
      "source_date": "{today}"
    }}
  ]
}}

महत्त्वाचे:
जर दिलेल्या articles मधून विश्वासार्ह प्रश्न तयार होत नसतील,
तर चुकीचा प्रश्न बनवण्याऐवजी कमी प्रश्न द्या.

SOURCE ARTICLES:
{source_text}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "questions": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "question": {"type": "STRING"},
                                "options": {
                                    "type": "ARRAY",
                                    "items": {"type": "STRING"}
                                },
                                "correct_answer": {"type": "INTEGER"},
                                "category": {"type": "STRING"},
                                "difficulty": {"type": "STRING"},
                                "explanation": {"type": "STRING"},
                                "source": {"type": "STRING"},
                                "source_date": {"type": "STRING"}
                            },
                            "required": [
                                "question",
                                "options",
                                "correct_answer",
                                "category",
                                "difficulty",
                                "explanation",
                                "source",
                                "source_date"
                            ]
                        }
                    }
                },
                "required": ["questions"]
            }
        }
    )

    return json.loads(response.text)["questions"]


# -----------------------------
# BASIC VALIDATION
# -----------------------------

def validate_question(q):

    if not isinstance(q, dict):
        return False

    required = [
        "question",
        "options",
        "correct_answer",
        "category",
        "difficulty",
        "explanation",
        "source",
        "source_date"
    ]

    if any(field not in q for field in required):
        return False

    if not isinstance(q["options"], list):
        return False

    if len(q["options"]) != 4:
        return False

    if q["correct_answer"] not in [0, 1, 2, 3]:
        return False

    if q["category"] != "Current Affairs":
        return False

    if q["difficulty"] not in ["Intermediate", "Difficult"]:
        return False

    if not q["question"].strip():
        return False

    if not q["source"].startswith("http"):
        return False

    return True


# -----------------------------
# SAVE TO SUPABASE
# -----------------------------

def save_questions(questions, existing):

    inserted = 0

    for q in questions:

        if not validate_question(q):
            print("Skipped invalid question")
            continue

        normalized = q["question"].strip().lower()

        if normalized in existing:
            print("Duplicate skipped")
            continue

        response = requests.post(
            REST_URL,
            headers=SUPABASE_HEADERS,
            json=q,
            timeout=30
        )

        if response.status_code >= 300:
            print("Supabase error:", response.text)
            continue

        existing.add(normalized)

        inserted += 1

        print("Inserted:", q["question"])

    return inserted


# -----------------------------
# MAIN
# -----------------------------

def main():

    print("Starting Marathi Quiz automatic updater...")

    articles = fetch_news()

    if not articles:
        print("No official news found.")
        return

    print(f"Found {len(articles)} PIB articles.")

    existing = get_existing_questions()

    print(f"Existing questions: {len(existing)}")

    questions = generate_questions(articles)

    print(f"Generated: {len(questions)}")

    inserted = save_questions(
        questions,
        existing
    )

    print(f"Successfully inserted: {inserted}")

    print("Updater finished.")


if __name__ == "__main__":
    main()
