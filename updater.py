import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import feedparser
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

MODEL = "gemini-3.5-flash-lite"

QUESTIONS_PER_RUN = 16
CANDIDATES_PER_RUN = 22

USER_AGENT = "MarathiQuizUpdater/1.0"


# ============================================================
# GEMINI
# ============================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# SUPABASE
# ============================================================

REST_URL = (
    f"{SUPABASE_URL.rstrip('/')}"
    "/rest/v1/questions"
)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


# ============================================================
# TRUSTED RSS SOURCES
# ============================================================

RSS_SOURCES = [
    {
        "name": "Press Information Bureau",
        "url": (
            "https://pib.gov.in/"
            "RssMain.aspx?"
            "ModId=6&Lang=1&Regid=1"
        ),
        "categories": [
            "Current Affairs",
            "Indian Polity",
            "Economy",
            "Science",
            "Environment",
            "Awards"
        ]
    }
]


# ============================================================
# TRUSTED DIRECT SOURCES
# ============================================================

DIRECT_SOURCES = [

    {
        "name": "Encyclopaedia Britannica - Maratha Empire",
        "url": (
            "https://www.britannica.com/"
            "place/Maratha-Empire"
        ),
        "categories": [
            "Maratha History",
            "Indian History"
        ]
    },

    {
        "name": "Encyclopaedia Britannica - Shivaji",
        "url": (
            "https://www.britannica.com/"
            "biography/Shivaji"
        ),
        "categories": [
            "Maratha History",
            "Indian History"
        ]
    },

    {
        "name": "Encyclopaedia Britannica - India",
        "url": (
            "https://www.britannica.com/"
            "place/India"
        ),
        "categories": [
            "Indian History",
            "Geography",
            "Indian Culture"
        ]
    },

    {
        "name": "Encyclopaedia Britannica - Maharashtra",
        "url": (
            "https://www.britannica.com/"
            "place/Maharashtra"
        ),
        "categories": [
            "Maharashtra History",
            "Geography",
            "Maharashtra Culture"
        ]
    },

    {
        "name": "NASA",
        "url": "https://www.nasa.gov/news/",
        "categories": [
            "Science",
            "Space & Technology"
        ]
    },

    {
        "name": "ISRO",
        "url": "https://www.isro.gov.in/",
        "categories": [
            "Science",
            "Space & Technology",
            "Current Affairs"
        ]
    },

    {
        "name": "RBI",
        "url": "https://www.rbi.org.in/",
        "categories": [
            "Economy",
            "Current Affairs"
        ]
    },

    {
        "name": "UNESCO",
        "url": "https://www.unesco.org/en",
        "categories": [
            "World History",
            "Indian Culture",
            "International Affairs",
            "Environment"
        ]
    },

    {
        "name": "WHO",
        "url": "https://www.who.int/news",
        "categories": [
            "Science",
            "Environment",
            "International Affairs"
        ]
    },

    {
        "name": "Nobel Prize",
        "url": "https://www.nobelprize.org/",
        "categories": [
            "Awards",
            "Science",
            "Current Affairs"
        ]
    },

    {
        "name": "Olympics",
        "url": "https://olympics.com/en/news",
        "categories": [
            "Sports",
            "Current Affairs"
        ]
    }
]


# ============================================================
# APPROVED DOMAINS
# ============================================================

APPROVED_DOMAINS = {
    "pib.gov.in",
    "gov.in",
    "nic.in",
    "rbi.org.in",
    "isro.gov.in",
    "nasa.gov",
    "unesco.org",
    "who.int",
    "nobelprize.org",
    "olympics.com",
    "britannica.com",
    "maharashtra.gov.in",
    "maharashtratourism.gov.in"
}


# ============================================================
# CATEGORIES
# ============================================================

CATEGORIES = [
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
]


# ============================================================
# HELPERS
# ============================================================

def normalize_text(text):

    text = str(text).strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def is_wikipedia(url):

    try:

        hostname = (
            urlparse(url).hostname
            or ""
        ).lower()

        return (
            hostname == "wikipedia.org"
            or hostname.endswith(".wikipedia.org")
            or hostname == "wikimedia.org"
            or hostname.endswith(".wikimedia.org")
        )

    except Exception:

        return False


def approved_domain(url):

    try:

        hostname = (
            urlparse(url).hostname
            or ""
        ).lower()

        if not hostname:
            return False

        if is_wikipedia(url):
            return False

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
# FETCH RSS
# ============================================================

def fetch_rss_sources():

    articles = []

    for source in RSS_SOURCES:

        try:

            print(
                "Fetching:",
                source["name"]
            )

            feed = feedparser.parse(
                source["url"]
            )

            for entry in feed.entries[:20]:

                title = (
                    entry.get(
                        "title",
                        ""
                    ).strip()
                )

                summary = (
                    entry.get(
                        "summary",
                        ""
                    ).strip()
                )

                link = (
                    entry.get(
                        "link",
                        ""
                    ).strip()
                )

                if not title or not link:
                    continue

                if is_wikipedia(link):
                    continue

                if not approved_domain(link):
                    continue

                articles.append({

                    "title": title,

                    "summary": summary,

                    "source": source["name"],

                    "url": link,

                    "categories":
                        source["categories"]

                })

        except Exception as exc:

            print(
                "RSS error:",
                source["name"],
                exc
            )

    return articles


# ============================================================
# FETCH DIRECT SOURCES
# ============================================================

def fetch_direct_sources():

    documents = []

    for source in DIRECT_SOURCES:

        try:

            print(
                "Fetching:",
                source["name"]
            )

            response = requests.get(
                source["url"],
                headers={
                    "User-Agent": USER_AGENT
                },
                timeout=20
            )

            if response.status_code >= 400:

                print(
                    "Skipped:",
                    response.status_code
                )

                continue

            text = response.text

            text = re.sub(
                r"<script.*?</script>",
                " ",
                text,
                flags=re.S | re.I
            )

            text = re.sub(
                r"<style.*?</style>",
                " ",
                text,
                flags=re.S | re.I
            )

            text = re.sub(
                r"<[^>]+>",
                " ",
                text
            )

            text = re.sub(
                r"\s+",
                " ",
                text
            ).strip()

            text = text[:30000]

            if len(text) < 500:
                continue

            documents.append({

                "source": source["name"],

                "url": source["url"],

                "categories":
                    source["categories"],

                "text": text

            })

        except Exception as exc:

            print(
                "Direct source error:",
                source["name"],
                exc
            )

    return documents


# ============================================================
# GET EXISTING QUESTIONS
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

        normalize_text(
            row["question"]
        )

        for row in response.json()

        if row.get("question")

    }


# ============================================================
# BUILD RESEARCH PACKET
# ============================================================

def build_research_packet():

    rss_articles = fetch_rss_sources()

    direct_documents = fetch_direct_sources()

    return {

        "rss_articles":
            rss_articles,

        "reference_documents":
            direct_documents

    }


# ============================================================
# GENERATE QUESTIONS
# ============================================================

def generate_questions(packet):

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    packet_text = json.dumps(
        packet,
        ensure_ascii=False,
        indent=2
    )

    packet_text = packet_text[:120000]

    prompt = f"""
तुम्ही अत्यंत काटेकोर fact-checking quiz editor आहात.

तारीख:
{today}

खाली दिलेल्या TRUSTED SOURCE MATERIAL मधून
मराठीमध्ये बहुपर्यायी प्रश्न तयार करा.

Candidate questions:
{CANDIDATES_PER_RUN}

अंतिम उद्दिष्ट:
जास्तीत जास्त {QUESTIONS_PER_RUN} विश्वसनीय प्रश्न.

SOURCE RULES:

फक्त दिलेल्या source material वर आधारित प्रश्न तयार करा.

स्वतः इंटरनेटवर शोध घेऊ नका.

Wikipedia STRICTLY FORBIDDEN आहे.

Wikipedia, Wikidata किंवा Wikimedia वापरू नका.

दिलेल्या source material मध्ये माहिती नसल्यास
प्रश्न तयार करू नका.

स्वतःचे तथ्य, तारीख, व्यक्ती, संख्या,
पुरस्कार, पद किंवा घटना बनवू नका.

ACCURACY:

प्रत्येक प्रश्नासाठी source material मध्ये
उत्तराचा स्पष्ट आधार असणे आवश्यक आहे.

तथ्य ambiguous असल्यास प्रश्न वगळा.

दोन पर्याय बरोबर असण्याची शक्यता असल्यास
प्रश्न वगळा.

Source पुरेसा स्पष्ट नसेल तर प्रश्न वगळा.

16 प्रश्न पूर्ण करण्यासाठी accuracy चा
कधीही compromise करू नका.

भाषा:

सर्व प्रश्न, पर्याय आणि explanation मराठीत असावेत.

व्यक्तींची नावे, संस्थांची नावे आणि अधिकृत
संज्ञा आवश्यकतेनुसार मूळ स्वरूपात ठेवू शकता.

DIFFICULTY:

Intermediate ते Difficult.

अतिशय सोपे प्रश्न टाळा.

CATEGORIES:

{json.dumps(CATEGORIES, ensure_ascii=False)}

Current Affairs ला प्राधान्य द्या.

Maratha History आणि Maharashtra History
नियमितपणे समाविष्ट करा.

उपलब्ध source material नुसार इतर categories वापरा.

OPTIONS:

प्रत्येक प्रश्नाला exactly 4 options असावेत.

फक्त एक correct answer असावा.

correct_answer:

0 = पहिला पर्याय
1 = दुसरा पर्याय
2 = तिसरा पर्याय
3 = चौथा पर्याय

SOURCE:

source field मध्ये source material मधील
अचूक URL द्या.

URL बनवू नका.

Wikipedia URL देऊ नका.

OUTPUT:

फक्त JSON द्या.

Format:

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
      "source": "https://trusted-source.example/page",
      "source_date": "{today}"
    }}
  ]
}}

TRUSTED SOURCE MATERIAL:

{packet_text}
"""

    response = client.models.generate_content(

        model=MODEL,

        contents=prompt,

        config={

            "response_mime_type":
                "application/json",

            "response_schema": {

                "type": "OBJECT",

                "properties": {

                    "questions": {

                        "type": "ARRAY",

                        "items": {

                            "type": "OBJECT",

                            "properties": {

                                "question":
                                    {
                                        "type": "STRING"
                                    },

                                "options": {

                                    "type": "ARRAY",

                                    "items": {
                                        "type": "STRING"
                                    }

                                },

                                "correct_answer":
                                    {
                                        "type": "INTEGER"
                                    },

                                "category":
                                    {
                                        "type": "STRING"
                                    },

                                "difficulty":
                                    {
                                        "type": "STRING"
                                    },

                                "explanation":
                                    {
                                        "type": "STRING"
                                    },

                                "source":
                                    {
                                        "type": "STRING"
                                    },

                                "source_date":
                                    {
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

                "required": [
                    "questions"
                ]

            }

        }

    )

    data = json.loads(
        response.text
    )

    return data.get(
        "questions",
        []
    )


# ============================================================
# VALIDATE QUESTION
# ============================================================

def validate_question(q):

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

    if not isinstance(q, dict):
        return False

    for field in required:

        if field not in q:
            return False

    if not isinstance(
        q["options"],
        list
    ):
        return False

    if len(q["options"]) != 4:
        return False

    if any(
        not str(x).strip()
        for x in q["options"]
    ):
        return False

    normalized_options = [
        normalize_text(x)
        for x in q["options"]
    ]

    if len(set(normalized_options)) != 4:

        print(
            "Rejected: duplicate options"
        )

        return False

    if q["correct_answer"] not in [
        0,
        1,
        2,
        3
    ]:

        return False

    if q["category"] not in CATEGORIES:
        return False

    if q["difficulty"] not in [
        "Intermediate",
        "Difficult"
    ]:

        return False

    question = str(
        q["question"]
    ).strip()

    if not question:
        return False

    source = str(
        q["source"]
    ).strip()

    if not source.startswith(
        "https://"
    ):

        return False

    if is_wikipedia(source):

        print(
            "Rejected Wikipedia question"
        )

        return False

    if not approved_domain(source):

        print(
            "Rejected unapproved source:",
            source
        )

        return False

    if not str(
        q["explanation"]
    ).strip():

        return False

    return True


# ============================================================
# SAVE QUESTIONS
# ============================================================

def save_questions(
    questions,
    existing
):

    inserted = 0

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    for q in questions:

        if inserted >= QUESTIONS_PER_RUN:
            break

        if not validate_question(q):

            print(
                "Skipped invalid question"
            )

            continue

        normalized = normalize_text(
            q["question"]
        )

        if normalized in existing:

            print(
                "Duplicate skipped:"
            )

            print(
                q["question"]
            )

            continue

        # IMPORTANT:
        # Gemini returns one "options" array.
        # Supabase has four separate columns:
        # option_a, option_b, option_c, option_d.

        payload = {

            "question":
                q["question"].strip(),

            "option_a":
                str(q["options"][0]).strip(),

            "option_b":
                str(q["options"][1]).strip(),

            "option_c":
                str(q["options"][2]).strip(),

            "option_d":
                str(q["options"][3]).strip(),

            "correct_answer":
                int(q["correct_answer"]),

            "category":
                q["category"],

            "difficulty":
                q["difficulty"],

            "explanation":
                q["explanation"].strip(),

            "source":
                q["source"].strip(),

            "source_date":
                today

        }

        response = requests.post(

            REST_URL,

            headers=SUPABASE_HEADERS,

            json=payload,

            timeout=30

        )

        if response.status_code >= 300:

            print(
                "Supabase error:"
            )

            print(
                response.status_code
            )

            print(
                response.text
            )

            continue

        existing.add(
            normalized
        )

        inserted += 1

        print(
            f"INSERTED "
            f"{inserted}/{QUESTIONS_PER_RUN}: "
            f"{q['question']}"
        )

    return inserted


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "MARATHI QUIZ AUTOMATIC UPDATER"
    )

    print("=" * 60)

    print(
        f"Target: {QUESTIONS_PER_RUN}"
    )

    print(
        f"Model: {MODEL}"
    )

    print(
        "Language: Marathi"
    )

    print(
        "Difficulty: Intermediate -> Difficult"
    )

    print(
        "Wikipedia: FORBIDDEN"
    )

    print(
        "Google Search grounding: DISABLED"
    )

    print()

    existing = get_existing_questions()

    print(
        f"Existing questions: {len(existing)}"
    )

    print()

    print(
        "Fetching trusted source material..."
    )

    packet = build_research_packet()

    rss_count = len(
        packet["rss_articles"]
    )

    document_count = len(
        packet["reference_documents"]
    )

    print(
        f"RSS articles: {rss_count}"
    )

    print(
        f"Reference documents: {document_count}"
    )

    if (
        rss_count == 0
        and document_count == 0
    ):

        print(
            "ERROR: No trusted source material."
        )

        return

    print()

    print(
        "Generating Marathi questions..."
    )

    questions = generate_questions(packet)

    print(
        f"Candidates generated: {len(questions)}"
    )

    print()

    inserted = save_questions(
        questions,
        existing
    )

    print()

    print("=" * 60)

    print(
        f"FINAL RESULT: "
        f"{inserted}/{QUESTIONS_PER_RUN}"
    )

    print("=" * 60)

    if inserted == 0:

        raise RuntimeError(
            "No verified questions were inserted."
        )

    if inserted < QUESTIONS_PER_RUN:

        print(
            "WARNING: Daily target was not reached."
        )

        print(
            "This is intentional: "
            "unverified questions are never inserted."
        )

    else:

        print(
            "SUCCESS: 16 questions inserted."
        )


if __name__ == "__main__":

    main()
