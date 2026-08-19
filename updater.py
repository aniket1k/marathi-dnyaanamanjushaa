import os
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import feedparser
from google import genai
from google.genai import types


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

QUESTIONS_PER_RUN = 16

MODEL = "gemini-3.6-flash"

HEADERS = {
    "User-Agent": "MarathiQuizUpdater/2.0"
}


# ============================================================
# APPROVED SOURCES
# ============================================================
#
# Wikipedia is intentionally NOT included anywhere.
#
# We begin with official/authoritative sources.
# More sources can be added after testing.
#

PIB_FEED = (
    "https://pib.gov.in/RssMain.aspx"
    "?ModId=6&Lang=1&Regid=3"
)

APPROVED_DOMAINS = {
    "pib.gov.in",
    "gov.in",
    "nic.in",
    "isro.gov.in",
    "rbi.org.in",
    "eci.gov.in",
    "sansad.in",
    "indiacode.nic.in",
    "maharashtra.gov.in",
    "mahakosh.gov.in",
    "mpsc.gov.in",
    "asi.nic.in",
    "unesco.org",
    "un.org",
    "who.int",
    "nasa.gov",
    "nobelprize.org",
    "icc-cricket.com",
    "olympics.com",
    "fifa.com",
}


# ============================================================
# GEMINI
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# SUPABASE
# ============================================================

REST_URL = f"{SUPABASE_URL.rstrip('/')}/rest/v1/questions"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


# ============================================================
# FETCH PIB
# ============================================================

def fetch_pib_articles():

    feed = feedparser.parse(PIB_FEED)

    articles = []

    for item in feed.entries[:30]:

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


# ============================================================
# EXISTING QUESTIONS
# ============================================================

def get_existing_questions():

    params = {
        "select": "question",
        "limit": "10000"
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


# ============================================================
# URL CHECK
# ============================================================

def is_approved_source(url):

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname

        if not hostname:
            return False

        hostname = hostname.lower()

        for domain in APPROVED_DOMAINS:

            if (
                hostname == domain
                or hostname.endswith("." + domain)
            ):
                return True

        return False

    except Exception:
        return False


# ============================================================
# GENERATE QUESTIONS
# ============================================================

def generate_questions(articles):

    today = datetime.now(timezone.utc).date().isoformat()

    source_text = json.dumps(
        articles,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
तुम्ही अत्यंत कठोर fact-checking करणारे
मराठी quiz editor आहात.

हे KBC/KHK शैलीचे सामान्यज्ञान quiz आहे.

महत्त्वाचे:
Wikipedia चा कोणत्याही कारणासाठी वापर करू नका.

आजची तारीख:
{today}

आम्हाला एकूण {QUESTIONS_PER_RUN} उच्च-गुणवत्तेचे प्रश्न हवेत.

स्तर:
Intermediate ते Difficult.

भाषा:
नैसर्गिक, स्पष्ट आणि शुद्ध मराठी.

प्रत्येक प्रश्नासाठी:

- प्रश्न मराठीत
- नेमके 4 पर्याय
- फक्त 1 बरोबर उत्तर
- correct_answer = 0, 1, 2 किंवा 3
- category
- difficulty
- मराठीत explanation
- source URL
- source date

============================================================
ACCURACY RULES
============================================================

1. कोणतेही तथ्य स्वतःहून बनवू नका.

2. उत्तराला विश्वसनीय स्रोतामध्ये स्पष्ट आधार असणे आवश्यक आहे.

3. स्रोत उपलब्ध नसेल किंवा तथ्य अस्पष्ट असेल तर प्रश्न देऊ नका.

4. दोन पर्याय काही अर्थाने बरोबर असतील असा प्रश्न देऊ नका.

5. प्रश्नातील प्रत्येक महत्त्वाचा दावा source मध्ये समर्थित असावा.

6. चार पर्याय एकमेकांपासून स्पष्टपणे वेगळे असावेत.

7. फक्त एकच पर्याय योग्य असावा.

8. चुकीचे distractors देखील तथ्यात्मकदृष्ट्या
   अशा प्रकारे लिहा की ते प्रश्नाचे उत्तर ठरू नयेत.

9. अतिशय सोपे प्रश्न टाळा.

10. अस्पष्ट, विवादित किंवा संदिग्ध तथ्यांवर प्रश्न बनवू नका.

11. source URL काल्पनिक बनवू नका.

12. दिलेल्या source material बाहेरील तथ्य वापरायचे असल्यास
    Google Search grounding वापरा.

13. Wikipedia वापरू नका.

14. फक्त विश्वासार्ह / अधिकृत / प्राथमिक स्रोतांना प्राधान्य द्या.

============================================================
CATEGORY MIX
============================================================

प्रश्नांमध्ये शक्य तितका विविध category mix ठेवा:

- Current Affairs
- Maratha History
- Maharashtra History
- Indian History
- World History
- Indian Polity
- Geography
- Science
- Space & Technology
- Environment
- Economy
- Sports
- Maharashtra Culture
- Marathi Literature
- Indian Culture
- Awards
- International Affairs
- General Knowledge

Current Affairs साठी ताजी माहिती वापरा.

Maratha History आणि historical categories साठी
विश्वसनीय अधिकृत/संस्थात्मक स्रोत वापरा.

एकाच विषयावर अनेक प्रश्न देणे टाळा.

============================================================
MARATHI QUALITY
============================================================

प्रश्न नैसर्गिक मराठीत लिहा.

अर्थ बदलणारे machine-like translation टाळा.

ऐतिहासिक व्यक्ती, ठिकाणे, संस्था आणि तांत्रिक संज्ञांची
प्रचलित मराठी नावे वापरा.

============================================================
IMPORTANT
============================================================

जर 16 उच्च-गुणवत्तेचे आणि पूर्णपणे समर्थित प्रश्न
तयार होत नसतील, तर चुकीचे प्रश्न तयार करून संख्या पूर्ण करू नका.

कमी प्रश्न देणे हे चुकीची माहिती देण्यापेक्षा चांगले आहे.

SOURCE MATERIAL:

{source_text}
"""

    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[grounding_tool],

            response_mime_type="application/json",

            response_schema={
                "type": "OBJECT",
                "properties": {
                    "questions": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "question": {
                                    "type": "STRING"
                                },
                                "options": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "STRING"
                                    }
                                },
                                "correct_answer": {
                                    "type": "INTEGER"
                                },
                                "category": {
                                    "type": "STRING"
                                },
                                "difficulty": {
                                    "type": "STRING"
                                },
                                "explanation": {
                                    "type": "STRING"
                                },
                                "source": {
                                    "type": "STRING"
                                },
                                "source_date": {
                                    "type": "STRING"
                                }
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
        )
    )

    return json.loads(response.text)["questions"]


# ============================================================
# QUESTION VALIDATION
# ============================================================

def validate_question(q, allowed_article_urls):

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

    question = q["question"].strip()
    options = q["options"]

    if not question:
        return False

    if not isinstance(options, list):
        return False

    if len(options) != 4:
        return False

    if any(
        not isinstance(option, str)
        or not option.strip()
        for option in options
    ):
        return False

    if len(set(
        option.strip().lower()
        for option in options
    )) != 4:
        return False

    if q["correct_answer"] not in [0, 1, 2, 3]:
        return False

    if q["difficulty"] not in [
        "Intermediate",
        "Difficult"
    ]:
        return False

    allowed_categories = {
        "Current Affairs",
        "Maratha History",
        "Maharashtra History",
        "Indian History",
        "World History",
        "Indian Polity",
        "Geography",
        "Science",
        "Space & Technology",
        "Environment",
        "Economy",
        "Sports",
        "Maharashtra Culture",
        "Marathi Literature",
        "Indian Culture",
        "Awards",
        "International Affairs",
        "General Knowledge"
    }

    if q["category"] not in allowed_categories:
        return False

    source = q["source"].strip()

    if not source.startswith(("http://", "https://")):
        return False

    if not is_approved_source(source):
        print("Rejected: unapproved source")
        return False

    # IMPORTANT:
    # The source must actually be one of the source URLs
    # supplied to the model for the initial PIB material.
    #
    # This prevents a hallucinated URL from being accepted.
    #
    normalized_source = source.rstrip("/")

    normalized_allowed = {
        url.rstrip("/")
        for url in allowed_article_urls
    }

    if normalized_source not in normalized_allowed:
        print("Rejected: source not in supplied source material")
        return False

    if not q["explanation"].strip():
        return False

    return True


# ============================================================
# SAVE TO SUPABASE
# ============================================================

def save_questions(questions, existing, allowed_article_urls):

    inserted = 0

    for q in questions:

        if not validate_question(
            q,
            allowed_article_urls
        ):
            print("Skipped invalid/unverified question")
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

            print(
                "Supabase error:",
                response.status_code,
                response.text
            )

            continue

        existing.add(normalized)

        inserted += 1

        print(
            f"Inserted {inserted}: "
            f"{q['question']}"
        )

    return inserted


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting Marathi Quiz "
        "automatic updater..."
    )

    articles = fetch_pib_articles()

    if not articles:
        print("No official PIB articles found.")
        return

    print(
        f"Found {len(articles)} PIB articles."
    )

    allowed_article_urls = [
        article["link"]
        for article in articles
    ]

    existing = get_existing_questions()

    print(
        f"Existing questions: "
        f"{len(existing)}"
    )

    questions = generate_questions(
        articles
    )

    print(
        f"Generated candidates: "
        f"{len(questions)}"
    )

    inserted = save_questions(
        questions,
        existing,
        allowed_article_urls
    )

    print(
        f"Successfully inserted: "
        f"{inserted}"
    )

    if inserted < QUESTIONS_PER_RUN:

        print(
            "WARNING: Daily target was not "
            "reached because insufficient "
            "questions passed validation."
        )

    print("Updater finished.")


if __name__ == "__main__":
    main()
