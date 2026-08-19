import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

MODEL = "gemini-3.6-flash"

QUESTIONS_PER_RUN = 16

# Generate extra candidates so that failed validation
# does not force us to accept bad questions.
CANDIDATES_PER_RUN = 24


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
# APPROVED SOURCE POLICY
# ============================================================

# Wikipedia is intentionally absent.

APPROVED_DOMAINS = {
    # Indian government / institutions
    "gov.in",
    "nic.in",
    "pib.gov.in",
    "india.gov.in",
    "indiacode.nic.in",
    "sansad.in",
    "rbi.org.in",
    "eci.gov.in",
    "isro.gov.in",
    "asi.nic.in",
    "culture.gov.in",
    "indiaculture.gov.in",

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

    # Sports organizations
    "icc-cricket.com",
    "olympics.com",
    "fifa.com",
    "uefa.com",
    "worldathletics.org",
    "formula1.com",

    # High-quality reference / news
    "britannica.com",
    "reuters.com",
    "apnews.com"
}


# ============================================================
# CATEGORY ROTATION
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
# SOURCE CHECKING
# ============================================================

def hostname_is_approved(url):

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


def is_wikipedia(url):

    try:
        hostname = (urlparse(url).hostname or "").lower()

        return (
            hostname == "wikipedia.org"
            or hostname.endswith(".wikipedia.org")
            or hostname == "wikimedia.org"
            or hostname.endswith(".wikimedia.org")
        )

    except Exception:
        return False


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

    rows = response.json()

    return {
        normalize_text(row["question"])
        for row in rows
        if row.get("question")
    }


def normalize_text(text):

    text = str(text).strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ============================================================
# CATEGORY PLAN
# ============================================================

def build_category_plan():

    """
    Rotate categories using the calendar day.

    Current Affairs always gets priority.
    Maharashtra / Maratha topics receive regular coverage.
    Other categories rotate so the pool stays broad.
    """

    day_number = datetime.now(
        timezone.utc
    ).timetuple().tm_yday

    rotating = CATEGORIES[1:]

    offset = day_number % len(rotating)

    rotated = (
        rotating[offset:]
        + rotating[:offset]
    )

    plan = [
        "Current Affairs",
        "Current Affairs",

        rotated[0],
        rotated[1],
        rotated[2],
        rotated[3],
        rotated[4],
        rotated[5],
        rotated[6],
        rotated[7],
        rotated[8],
        rotated[9],
        rotated[10],
        rotated[11],
        rotated[12],
        rotated[13]
    ]

    return plan


# ============================================================
# RESEARCH WITH GOOGLE SEARCH
# ============================================================

def research_facts():

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    category_plan = build_category_plan()

    plan_text = "\n".join(
        f"{i + 1}. {category}"
        for i, category in enumerate(category_plan)
    )

    prompt = f"""
You are the research stage of a high-accuracy Marathi
quiz system.

Today:
{today}

We need factual research for 16 quiz questions.

The final questions will be:
- Marathi
- Intermediate to Difficult
- 4 answer choices
- exactly 1 correct answer
- factually verifiable

IMPORTANT SOURCE POLICY:

Wikipedia is STRICTLY FORBIDDEN.

Do not use:
- Wikipedia
- Wikidata
- random quiz websites
- GK blogs
- anonymous blogs
- social media
- unsourced pages
- AI-generated websites

Prefer:
1. Official government sources
2. Official institutional sources
3. Primary organizations
4. Reputable reference sources
5. Reuters/AP where appropriate for current affairs

The source must actually support the fact.

Do not rely on your memory for a factual claim
when a reliable web source can verify it.

CATEGORY PLAN:

{plan_text}

For each category, research a strong, non-trivial fact
suitable for an Intermediate/Difficult quiz question.

Avoid:
- trivial facts
- ambiguous facts
- disputed claims
- facts with multiple possible answers
- questions whose answer depends on interpretation
- obsolete current-affairs information

For historical questions, prefer authoritative
institutional or reference sources.

For current affairs, prefer recent information.

Return a research dossier.

For each item provide:

CATEGORY:
FACT:
WHY_IT_IS_UNAMBIGUOUS:
SOURCE_TITLE:
SOURCE_URL:

Do not invent URLs.
Use only URLs actually returned by Google Search.

The final question writer will receive your research dossier
and will NOT be allowed to introduce facts that are not
supported by this dossier.
"""

    interaction = client.interactions.create(
        model=MODEL,
        input=prompt,
        tools=[
            {
                "type": "google_search"
            }
        ]
    )

    return interaction


# ============================================================
# EXTRACT SEARCH CITATIONS
# ============================================================

def extract_citations(interaction):

    citations = []

    for step in getattr(
        interaction,
        "steps",
        []
    ):

        if getattr(
            step,
            "type",
            None
        ) != "model_output":
            continue

        for block in getattr(
            step,
            "content",
            []
        ):

            if getattr(
                block,
                "type",
                None
            ) != "text":
                continue

            text = getattr(
                block,
                "text",
                ""
            )

            annotations = getattr(
                block,
                "annotations",
                None
            ) or []

            for annotation in annotations:

                if getattr(
                    annotation,
                    "type",
                    None
                ) != "url_citation":
                    continue

                url = getattr(
                    annotation,
                    "url",
                    ""
                )

                title = getattr(
                    annotation,
                    "title",
                    ""
                )

                start = getattr(
                    annotation,
                    "start_index",
                    0
                )

                end = getattr(
                    annotation,
                    "end_index",
                    0
                )

                cited_text = text[
                    start:end
                ]

                if not url:
                    continue

                if is_wikipedia(url):
                    continue

                if not hostname_is_approved(url):
                    continue

                citations.append({
                    "url": url,
                    "title": title,
                    "evidence": cited_text
                })

    # Remove duplicates
    unique = {}

    for item in citations:

        unique[item["url"]] = item

    return list(
        unique.values()
    )


# ============================================================
# CREATE EVIDENCE PACKET
# ============================================================

def build_evidence_packet(
    interaction,
    citations
):

    research_text = getattr(
        interaction,
        "output_text",
        ""
    )

    lines = []

    lines.append(
        "RESEARCH DOSSIER"
    )

    lines.append(
        research_text
    )

    lines.append(
        "\nVERIFIED SEARCH CITATIONS"
    )

    for i, citation in enumerate(
        citations
    ):

        lines.append(
            f"""
[EVIDENCE {i}]
TITLE: {citation["title"]}
URL: {citation["url"]}
CITED EVIDENCE:
{citation["evidence"]}
"""
        )

    return "\n".join(lines)


# ============================================================
# QUESTION GENERATION
# ============================================================

def generate_questions(
    evidence_packet
):

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    schema = {
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
                        "evidence_number": {
                            "type": "INTEGER"
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
                        "evidence_number"
                    ]
                }
            }
        },
        "required": [
            "questions"
        ]
    }

    prompt = f"""
You are the final question editor for a
high-accuracy Marathi quiz.

Today:
{today}

Create up to {CANDIDATES_PER_RUN} candidate questions.

FINAL REQUIREMENTS:

Language:
Marathi.

Difficulty:
Intermediate or Difficult only.

Each question:
- exactly 4 answer options
- exactly 1 correct option
- no ambiguity
- no trick wording
- no unsupported claim
- natural Marathi
- meaningful explanation

SOURCE RULE:

You may ONLY use facts explicitly supported by
the evidence packet below.

Do NOT use your general knowledge to fill gaps.

The source URL for each question MUST be exactly
one of the URLs listed in the evidence packet.

Do NOT invent or modify URLs.

Wikipedia is forbidden.

The evidence_number must identify the exact evidence
used for the question.

A question must be rejected if:
- evidence does not clearly support the answer
- two options could reasonably be correct
- the source is weak
- the fact is disputed
- the question is too easy
- the Marathi wording changes the factual meaning

OPTION RULE:

The four options must be genuinely distinct.

Only one option may be correct.

Do not create a distractor that is partly correct.

CATEGORY:

Use the category supported by the evidence.

The categories include:

Current Affairs
Maratha History
Maharashtra History
Indian History
World History
Indian Polity
Geography
Science
Space & Technology
Environment
Economy
Sports
Maharashtra Culture
Marathi Literature
Indian Culture
Awards
International Affairs
General Knowledge

Return JSON only.

EVIDENCE PACKET:

{evidence_packet}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema
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

def validate_question(
    q,
    citations
):

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
        "evidence_number"
    ]

    if not isinstance(q, dict):
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

    # Exactly four unique options
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

    # Correct answer must be 0-3
    if q["correct_answer"] not in [
        0,
        1,
        2,
        3
    ]:
        print(
            "Rejected: invalid answer index"
        )
        return False

    # Categories
    if q["category"] not in CATEGORIES:
        print(
            "Rejected: invalid category"
        )
        return False

    # Difficulty
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
        ("http://", "https://")
    ):
        print(
            "Rejected: invalid source URL"
        )
        return False

    if is_wikipedia(source):
        print(
            "Rejected: Wikipedia source"
        )
        return False

    if not hostname_is_approved(source):
        print(
            "Rejected: source domain not approved"
        )
        return False

    # Source MUST correspond to evidence.
    evidence_number = q[
        "evidence_number"
    ]

    if not isinstance(
        evidence_number,
        int
    ):
        print(
            "Rejected: invalid evidence number"
        )
        return False

    if evidence_number < 0:
        return False

    if evidence_number >= len(
        citations
    ):
        print(
            "Rejected: nonexistent evidence"
        )
        return False

    evidence_url = citations[
        evidence_number
    ]["url"]

    if source.rstrip("/") != evidence_url.rstrip("/"):
        print(
            "Rejected: source does not match evidence"
        )
        return False

    return True


# ============================================================
# OPTIONAL SOURCE RE-CHECK
# ============================================================

def source_is_reachable(url):

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent":
                    "MarathiQuizUpdater/3.0"
            },
            timeout=15,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return False

        final_url = response.url

        if is_wikipedia(final_url):
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
# SAVE TO SUPABASE
# ============================================================

def save_questions(
    questions,
    existing,
    citations
):

    inserted = 0

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    for q in questions:

        if inserted >= QUESTIONS_PER_RUN:
            break

        if not validate_question(
            q,
            citations
        ):
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

        # Re-check source availability.
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

            # This is the date on which the question
            # passed our automated verification pipeline.
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
        f"Target: {QUESTIONS_PER_RUN} questions"
    )

    print(
        "Difficulty: Intermediate -> Difficult"
    )

    print(
        "Language: Marathi"
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

    interaction = research_facts()

    citations = extract_citations(
        interaction
    )

    print(
        f"Approved search citations found: "
        f"{len(citations)}"
    )

    if len(citations) < 8:

        raise RuntimeError(
            "Too few approved source citations. "
            "Questions will not be generated."
        )

    evidence_packet = build_evidence_packet(
        interaction,
        citations
    )

    print(
        "Generating candidate questions..."
    )

    questions = generate_questions(
        evidence_packet
    )

    print(
        f"Candidate questions generated: "
        f"{len(questions)}"
    )

    inserted = save_questions(
        questions,
        existing,
        citations
    )

    print()
    print("=" * 60)
    print(
        f"FINAL RESULT: {inserted}/"
        f"{QUESTIONS_PER_RUN} inserted"
    )
    print("=" * 60)

    if inserted < QUESTIONS_PER_RUN:

        print(
            "WARNING: Daily target was not reached."
        )

        print(
            "No unverified questions were inserted."
        )

    else:

        print(
            "SUCCESS: Daily target reached."
        )


if __name__ == "__main__":
    main()
