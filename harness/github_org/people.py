"""The DSS26 Bank engineering organisation: teams and the people in them.

The Cards Platform names come from the Confluence space
(``harness/stubs/_kb_pages.py``) - same logins, same roles, same dates - so a
commit the agent finds on GitHub and a page it reads in Confluence describe
the same people. Everyone else fills out the rest of a mid-size European
retail bank.

These are commit-author personas, not GitHub accounts. Their addresses sit on
a reserved ``.example`` domain so GitHub never links them to a real profile.
"""

from __future__ import annotations

from model import Person, Team

# Tribes (parent teams) and squads (child teams), the usual shape of a bank's
# engineering org. GitHub nests child teams under their parent.
TEAMS: tuple[Team, ...] = (
    # --- tribes -----------------------------------------------------------
    Team("cards-payments", "Cards & Payments",
         "Tribe: card acquiring, issuing, authorisation, clearing and settlement."),
    Team("financial-crime-risk", "Financial Crime & Risk",
         "Tribe: fraud, AML, sanctions and KYC."),
    Team("customer-channels", "Customer & Channels",
         "Tribe: customer data, consent, mobile and web banking."),
    Team("core-technology", "Core Technology",
         "Tribe: core banking integration, payment rails and engineering platforms."),
    # --- squads -----------------------------------------------------------
    Team("payments-edge", "Payments Edge",
         "Merchant and acquirer edge - owns merchant-gateway and the producer side "
         "of cards.authorisation.requested.v1.", parent="cards-payments"),
    Team("cards-platform", "Cards Platform",
         "Authorisation, fraud decisioning and ledger posting on the cards Kafka "
         "clusters. On-call via PagerDuty (Cards Platform - Primary).",
         parent="cards-payments"),
    Team("cards-servicing", "Cards Servicing",
         "Card lifecycle, disputes, refunds and statements.", parent="cards-payments"),
    Team("clearing-settlement", "Clearing & Settlement",
         "Scheme clearing files, settlement batches and interchange.",
         parent="cards-payments"),
    Team("risk-platform", "Risk Platform",
         "Fraud case management, risk limits and fraud scoring models.",
         parent="financial-crime-risk"),
    Team("compliance-platform", "Compliance Platform",
         "AML transaction screening, sanctions screening and KYC.",
         parent="financial-crime-risk"),
    Team("customer-platform", "Customer Platform",
         "Customer profile, accounts and consent.", parent="customer-channels"),
    Team("digital-channels", "Digital Channels",
         "Mobile and internet banking.", parent="customer-channels"),
    Team("core-banking", "Core Banking",
         "Core banking adapter and the SEPA / SWIFT payments hub.",
         parent="core-technology"),
    Team("platform-engineering", "Platform Engineering",
         "Kafka platform, CI templates, golden paths and developer tooling.",
         parent="core-technology"),
)

TEAM_SLUGS = frozenset(t.slug for t in TEAMS)

PEOPLE: tuple[Person, ...] = (
    # --- cards-platform (names and roles from the Confluence space) --------
    Person("lena.fischer", "Lena Fischer", "cards-platform",
           "Engineering Manager, Cards Platform", "2021-09-01"),
    Person("alex.chen", "Alex Chen", "cards-platform",
           "Tech Lead, fraud decisioning", "2021-11-15"),
    Person("priya.r", "Priya Raman", "cards-platform",
           "Senior Engineer, event schemas", "2021-06-01"),
    Person("jordan.k", "Jordan Kim", "cards-platform",
           "Software Engineer", "2023-01-09"),
    Person("dana.v", "Dana Vasquez", "cards-platform",
           "Staff Engineer, Kafka Connect & GitOps", "2022-02-01"),
    Person("sam.okafor", "Sam Okafor", "cards-platform",
           "Software Engineer, Kafka Connect", "2023-09-04"),
    Person("tomasz.nowak", "Tomasz Nowak", "cards-platform",
           "SRE Lead", "2020-03-02", left="2025-02-14"),
    # --- payments-edge ------------------------------------------------------
    Person("marta.silva", "Marta Silva", "payments-edge",
           "Tech Lead, Payments Edge", "2020-10-05"),
    Person("ravi.iyer", "Ravi Iyer", "payments-edge",
           "Senior Software Engineer", "2022-04-11"),
    Person("noah.becker", "Noah Becker", "payments-edge",
           "Software Engineer", "2024-02-19"),
    # --- cards-servicing ----------------------------------------------------
    Person("chloe.dubois", "Chloé Dubois", "cards-servicing",
           "Tech Lead, Cards Servicing", "2021-03-01"),
    Person("mateo.rossi", "Mateo Rossi", "cards-servicing",
           "Software Engineer", "2023-05-15"),
    # --- clearing-settlement ------------------------------------------------
    Person("henrik.larsen", "Henrik Larsen", "clearing-settlement",
           "Senior Software Engineer", "2020-08-17"),
    Person("amara.nwosu", "Amara Nwosu", "clearing-settlement",
           "Software Engineer", "2024-06-03"),
    # --- risk-platform ------------------------------------------------------
    Person("ines.duarte", "Inês Duarte", "risk-platform",
           "Tech Lead, Risk Platform", "2021-01-11"),
    Person("yusuf.demir", "Yusuf Demir", "risk-platform",
           "ML Engineer", "2022-09-05"),
    # --- compliance-platform ------------------------------------------------
    Person("hannah.berg", "Hannah Berg", "compliance-platform",
           "Tech Lead, Compliance Platform", "2020-11-02"),
    Person("kwame.mensah", "Kwame Mensah", "compliance-platform",
           "Software Engineer", "2023-03-20"),
    Person("claire.martin", "Claire Martin", "compliance-platform",
           "Compliance Partner (SOX, PCI DSS)", "2019-05-06"),
    # --- customer-platform --------------------------------------------------
    Person("lucas.moreau", "Lucas Moreau", "customer-platform",
           "Tech Lead, Customer Platform", "2021-07-12"),
    Person("aiko.tanaka", "Aiko Tanaka", "customer-platform",
           "Software Engineer", "2023-10-02"),
    # --- digital-channels ---------------------------------------------------
    Person("zara.ahmed", "Zara Ahmed", "digital-channels",
           "Tech Lead, Digital Channels", "2020-06-08"),
    Person("olivia.grant", "Olivia Grant", "digital-channels",
           "Mobile Engineer", "2022-11-14"),
    # --- core-banking -------------------------------------------------------
    Person("pieter.devries", "Pieter de Vries", "core-banking",
           "Principal Engineer, Core Banking", "2018-02-05"),
    Person("giulia.conti", "Giulia Conti", "core-banking",
           "Software Engineer, Payment Rails", "2022-01-17"),
    # --- platform-engineering -----------------------------------------------
    Person("erik.lindqvist", "Erik Lindqvist", "platform-engineering",
           "Tech Lead, Platform Engineering", "2020-01-13"),
    Person("fatima.benali", "Fatima Benali", "platform-engineering",
           "Platform Engineer", "2023-06-26"),
    # --- automation ---------------------------------------------------------
    # The bank's own dependency-update bot. Deliberately not GitHub's
    # dependabot identity: a seeded commit must never claim to be from a real
    # GitHub account.
    Person("platform-bot", "dss26-platform-bot", "platform-engineering",
           "Automated dependency updates", "2019-01-01"),
)

BY_LOGIN: dict[str, Person] = {p.login: p for p in PEOPLE}


def person(login: str) -> Person:
    try:
        return BY_LOGIN[login]
    except KeyError:
        raise KeyError(f"unknown persona {login!r} - add it to people.PEOPLE") from None
