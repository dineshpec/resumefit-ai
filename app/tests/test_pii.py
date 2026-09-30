import pytest

from resumefit.guardrails.pii import redact


def test_email_phone_url_and_address_become_placeholders():
    text = (
        "Asha Example\n"
        "asha.example@example.com | +91 98765 43210 | https://example.com/portfolio\n"
        "221B Baker Street, London"
    )

    result = redact(text)

    assert result.text == ("Asha Example\n[EMAIL] | [PHONE] | [URL]\n[ADDRESS], London")
    assert result.counts == {"email": 1, "phone": 1, "url": 1, "address": 1}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Call +91 98765 43210 today", "Call [PHONE] today"),
        ("Call +91-98765-43210.", "Call [PHONE]."),
        ("Mobile: 9876543210", "Mobile: [PHONE]"),
        ("Tel 098765 43210", "Tel [PHONE]"),
        ("Phone: +1 (555) 010-4477", "Phone: [PHONE]"),
        ("Office (555) 010-4477", "Office [PHONE]"),
        ("London +44 20 7946 0958", "London [PHONE]"),
        ("Desk 020-5550-1234", "Desk [PHONE]"),
    ],
)
def test_international_and_indian_phone_numbers_are_redacted(text, expected):
    assert redact(text).text == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See https://example.com/a?b=1.", "See [URL]."),
        ("See http://example.org", "See [URL]"),
        ("Site www.example-portfolio.com/work", "Site [URL]"),
        ("linkedin.com/in/asha-example-000", "[URL]"),
        ("Code: github.com/ravi-sample-000.", "Code: [URL]."),
    ],
)
def test_urls_with_and_without_scheme_are_redacted(text, expected):
    assert redact(text).text == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Flat 4B, 12 MG Road, Pune", "Flat 4B, [ADDRESS], Pune"),
        ("45 Gandhi Nagar, Jaipur", "[ADDRESS], Jaipur"),
        ("7 Old Mill Lane", "[ADDRESS]"),
        ("1600 Example Avenue", "[ADDRESS]"),
        ("Pune, PIN 411001", "Pune, PIN [ADDRESS]"),
        ("Pincode: 560 001", "Pincode: [ADDRESS]"),
    ],
)
def test_street_addresses_and_labelled_pin_codes_are_redacted(text, expected):
    assert redact(text).text == expected


@pytest.mark.parametrize(
    "text",
    [
        "Worked at Example Ltd (2019-2023) and 2015 - 2019.",
        "Jan 2019 – Mar 2023",
        "Improved accuracy by 12% and cut costs by 7.5%.",
        "Python 3.11, Kubernetes 1.29, Terraform 0.12, v2.3.1",
        "Handled 4,000 transactions per second across 120 services.",
        "Led 3 teams across the road network project.",
        "Built services on ASP.NET and Node.js.",
        "Scored 411001 points; batch 560001 shipped.",
        "CGPA 8.4/10, 2024 or 2025",
    ],
)
def test_years_ranges_percentages_and_versions_are_untouched(text):
    result = redact(text)

    assert result.text == text
    assert sum(result.counts.values()) == 0


def test_counts_every_replacement():
    text = "a@example.com b@example.org 9876543210 www.example.com"

    assert redact(text).counts == {"email": 2, "phone": 1, "url": 1, "address": 0}
