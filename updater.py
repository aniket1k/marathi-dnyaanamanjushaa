import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from google import genai


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

# Free-tier-friendly model
MODEL = "gemini-2.5-flash-lite"

QUESTIONS_PER_RUN = 16

# We deliberately ask for a few extra candidates.
# Invalid/ambiguous questions are discarded.
CANDIDATES_PER_RUN = 22


# ============================================================
# CLIENTS
# ============================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)

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
# APPROVED SOURCES
# ============================================================

APPROVED_DOMAINS = {
    # Government / official India
    "gov.in",
    "nic.in",
    "pib.gov.in",
    "india.gov.in",
    "sansad.in",
    "rbi.org.in",
    "eci.gov.in",
    "isro.gov.in",
    "asi.nic.in",
    "culture.gov.in",

    # Maharashtra
    "maharashtra.gov.in",
    "maharashtratourism.gov.in",
    "mtdc.co",

    # International institutions
    "un.org",
    "unesco.org",
    "who.int",
    "worldbank.org",
    "imf.org",
    "nasa.gov",
    "nobelprize.org",

    # Sports
    "icc-cricket.com",
    "olympics.com",
    "fifa.com",
    "uefa.com",
    "worldathletics.org",
    "formula1.com",

    # Strong reference/news sources
    "britannica.com",
    "reuters.com",
    "apnews.com"
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
# BASIC HELPERS
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


def hostname_is_approved(url):

    try:

        parsed = urlparse(url)

        if parsed.scheme not in (
            "http",
            "https"
        ):
            return False

        hostname = (
            parsed.hostname
            or ""
        ).lower()

        if not hostname:
            return False

        if is_wikipedia(url):
            return False

        for domain in APPROVED_DOMAINS:

            if (
                hostname == domain
                or hostname.endswith(
                    "." + domain
                )
            ):
                return True

        return False

    except Exception:
        return False


# ============================================================
# SUPABASE
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

    rows = response.json()

    return {
        normalize_text(row["question"])
        for row in rows
        if row.get("question")
    }


# ============================================================
# CATEGORY ROTATION
# ============================================================

def build_category_plan():

    day_number = datetime.now(
        timezone.utc
    ).timetuple().tm_yday

    rotating = CATEGORIES[1:]

    offset = day_number % len(
        rotating
    )

    rotated = (
        rotating[offset:]
        + rotating[:offset]
    )

    plan = [
        "Current Affairs",
        "Current Affairs"
    ]

    plan.extend(
        rotated[:14]
    )

    return plan


# ============================================================
# RESEARCH + QUESTION GENERATION
# ============================================================

def generate_questions():

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    category_plan = (
        build_category_plan()
    )

    category_text = "\n".join(
        f"{i + 1}. {category}"
        for i, category
        in enumerate(category_plan)
    )

    prompt = f"""
You are the research and question-generation engine
for a high-accuracy Marathi quiz.

TODAY:
{today}

Generate up to {CANDIDATES_PER_RUN}
candidate questions.

The final database should receive up to
{QUESTIONS_PER_RUN} verified questions.

LANGUAGE:
Marathi.

DIFFICULTY:
Intermediate or Difficult.

EVERY QUESTION MUST HAVE:
- exactly 4 options
- exactly 1 correct option
- clear wording
- no ambiguity
- factual answer
- short Marathi explanation

============================================================
ABSOLUTE SOURCE RULE
============================================================

Wikipedia is STRICTLY FORBIDDEN.

Never use:
- Wikipedia
- Wikidata
- Wikimedia
- random quiz sites
- GK blogs
- anonymous blogs
- social media
- unsourced websites
- AI-generated websites

Prefer these sources:

1. Indian government websites
2. Maharashtra government websites
3. Official institutional websites
4. Official international organizations
5. Official sports organizations
6. Britannica
7. Reuters
8. Associated Press

A source must actually support the answer.

DO NOT INVENT SOURCE URLs.

============================================================
RESEARCH RULE
============================================================

Use Google Search grounding.

Search for reliable sources BEFORE deciding
on the question.

For historical questions, prefer authoritative
institutional/reference sources.

For current affairs, prefer recent official
or highly reputable sources.

If you cannot find a trustworthy source,
DO NOT create the question.

============================================================
CATEGORY PLAN
============================================================

{category_text}

Try to cover the categories in the plan.

Current Affairs should be emphasized.

Maratha History should appear regularly.

============================================================
QUESTION QUALITY
============================================================

Avoid:
- very easy questions
- disputed historical claims
- vague dates
- questions with multiple correct answers
- subjective questions
- opinion questions
- trick questions
- questions where two options could reasonably
  be accepted

For every question, the source must clearly
support the correct answer.

============================================================
SOURCE FIELD
============================================================

The source field MUST contain the exact URL
of the source used.

Do not manufacture URLs.

============================================================
OUTPUT
============================================================

Return JSON only.

Schema:

{{
  "questions": [
    {{
      "question": "मराठी प्रश्न",
      "option_a": "पर्याय अ",
      "option_b": "पर्याय ब",
      "option_c": "पर्याय क",
      "option_d": "पर्याय ड",
      "correct_answer": 0,
      "category": "Current Affairs",
      "difficulty": "Intermediate",
      "explanation": "मराठी स्पष्टीकरण",
      "source": "https://real-source-url.example",
      "source_date": "{today}"
    }}
  ]
}}

correct_answer MUST be:
0 = option_a
1 = option_b
2 = option_c
3 = option_d

If reliable questions cannot be produced,
return fewer questions.

NEVER sacrifice accuracy to reach 16.

============================================================
IMPORTANT
============================================================

The source URL must come from the actual
Google Search-grounded research.

Do not use Wikipedia under any circumstances.
"""

    response = client.models.generate_content(
        model=MODEL,
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
                                "question": {
                                    "type": "STRING"
                                },
                                "option_a": {
                                    "type": "STRING"
                                },
                                "option_b": {
                                    "type": "STRING"
                                },
                                "option_c": {
                                    "type": "STRING"
                                },
                                "option_d": {
                                    "type": "STRING"
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
                                "option_a",
                                "option_b",
                                "option_c",
                                "option_d",
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
            },

            # Google Search grounding
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }
    )

    return json.loads(
        response.text
    ).get(
        "questions",
        []
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_question(q):

    required = [
        "question",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_answer",
        "category",
        "difficulty",
        "explanation",
        "source",
        "source_date"
    ]

    if not isinstance(
        q,
        dict
    ):
        return False

    for field in required:

        if field not in q:
            print(
                f"Rejected: missing {field}"
            )
            return False

    question = str(
        q["question"]
    ).strip()

    options = [
        str(q["option_a"]).strip(),
        str(q["option_b"]).strip(),
        str(q["option_c"]).strip(),
        str(q["option_d"]).strip()
    ]

    if not question:
        return False

    if any(
        not option
        for option in options
    ):
        return False

    normalized_options = [
        normalize_text(option)
        for option in options
    ]

    if len(
        set(normalized_options)
    ) != 4:

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

        print(
            "Rejected: invalid correct_answer"
        )

        return False

    if q["category"] not in CATEGORIES:

        print(
            "Rejected: invalid category"
        )

        return False

    if q["difficulty"] not in [
        "Intermediate",
        "Difficult"
    ]:

        print(
            "Rejected: invalid difficulty"
        )

        return False

    if not str(
        q["explanation"]
    ).strip():

        return False

    source = str(
        q["source"]
    ).strip()

    if not source.startswith(
        (
            "https://",
            "http://"
        )
    ):

        print(
            "Rejected: invalid source"
        )

        return False

    if is_wikipedia(source):

        print(
            "Rejected: Wikipedia"
        )

        return False

    if not hostname_is_approved(
        source
    ):

        print(
            "Rejected: unapproved source"
        )

        return False

    return True


# ============================================================
# SOURCE REACHABILITY
# ============================================================

def source_is_reachable(url):

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent":
                    "MarathiQuizUpdater/1.0"
            },
            timeout=15,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return False

        final_url = response.url

        if is_wikipedia(
            final_url
        ):
            return False

        return hostname_is_approved(
            final_url
        )

    except Exception as exc:

        print(
            "Source check failed:",
            exc
        )

        return False


# ============================================================
# SAVE
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
            continue

        normalized = normalize_text(
            q["question"]
        )

        if normalized in existing:

            print(
                "Duplicate skipped:",
                q["question"]
            )

            continue

        source = q["source"].strip()

        if not source_is_reachable(
            source
        ):

            print(
                "Source unreachable; skipped:",
                source
            )

            continue

        payload = {
            "question":
                q["question"].strip(),

            "option_a":
                q["option_a"].strip(),

            "option_b":
                q["option_b"].strip(),

            "option_c":
                q["option_c"].strip(),

            "option_d":
                q["option_d"].strip(),

            "correct_answer":
                int(q["correct_answer"]),

            "category":
                q["category"],

            "difficulty":
                q["difficulty"],

            "explanation":
                q["explanation"].strip(),

            "source":
                source,

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
                "Supabase error:",
                response.status_code,
                response.text
            )

            continue

        existing.add(
            normalized
        )

        inserted += 1

        print(
            f"INSERTED {inserted}/"
            f"{QUESTIONS_PER_RUN}: "
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

    print()

    existing = get_existing_questions()

    print(
        f"Existing questions: "
        f"{len(existing)}"
    )

    print()

    print(
        "Researching trusted sources..."
    )

    questions = generate_questions()

    print(
        f"Candidates generated: "
        f"{len(questions)}"
    )

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

    if inserted < QUESTIONS_PER_RUN:

        print(
            "WARNING: Target not reached."
        )

        print(
            "Unverified questions were NOT inserted."
        )

    else:

        print(
            "SUCCESS: Daily target reached."
        )


if __name__ == "__main__":
    main()
