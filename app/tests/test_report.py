import json
from datetime import UTC, datetime

import pytest

from resumefit.outcomes import TimelineEntry
from resumefit.report import (
    SECTION_HEADINGS,
    ReportValidationError,
    finalize_report,
    render_markdown,
    report_json,
    sanitize_text,
)
from resumefit.schemas import (
    BulletSuggestion,
    CandidateProfile,
    CoachingPlan,
    CriterionJudgement,
    EducationEntry,
    ExperienceEntry,
    InterviewQuestion,
    JobRequirements,
    LearningItem,
    MatchAssessment,
    MatchReport,
    ProjectEntry,
    ReportDraft,
    ReportMeta,
)

META = ReportMeta(
    generated_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
    support_id="RF-7K3M9QX2",
    model="gpt-4o-mini",
)
REDACTIONS = {"email": 1, "phone": 1, "url": 0, "address": 0}
HOSTILE = (
    "Great fit ![tracker](https://evil.example/pixel.png) see [my site](javascript:alert(1)) "
    "<script>alert('x')</script><b>bold</b> and https://evil.example/path"
)


def judgements(experience=20, responsibilities=12, education=4):
    return [
        CriterionJudgement(
            criterion="relevant_experience",
            awarded=experience,
            rationale="Six years of backend work.",
        ),
        CriterionJudgement(
            criterion="responsibilities_alignment",
            awarded=responsibilities,
            rationale="Owned similar services.",
        ),
        CriterionJudgement(
            criterion="education_certifications",
            awarded=education,
            rationale="Relevant degree.",
        ),
    ]


def make_draft(**changes):
    fields = {
        "summary": "A strong backend candidate with one gap in infrastructure tooling.",
        "candidate": CandidateProfile(
            skills=["Python", "PostgreSQL", "Docker", "FastAPI"],
            experience=[
                ExperienceEntry(
                    title="Backend Engineer",
                    organization="Example Payments",
                    years=4.0,
                    highlights=["Built payment APIs"],
                )
            ],
            education=[
                EducationEntry(
                    qualification="B.Tech Computer Science",
                    institution="Example University",
                    year="2018",
                )
            ],
            projects=[
                ProjectEntry(
                    name="Ledger",
                    summary="Double-entry ledger service",
                    skills=["Python"],
                )
            ],
            total_years_experience=6.0,
        ),
        "job": JobRequirements(
            role_title="Senior Backend Engineer",
            seniority="senior",
            must_have=["Python", "PostgreSQL", "Docker", "Kubernetes"],
            nice_to_have=["Go", "Kafka", "Terraform"],
            min_years_experience=5.0,
            responsibilities=["Design APIs"],
        ),
        "assessment": MatchAssessment(
            matched_skills=["Python", "PostgreSQL", "Docker"],
            missing_must_have=["Kubernetes"],
            missing_nice_to_have=["Go", "Terraform"],
            judgements=judgements(),
        ),
        "coaching": CoachingPlan(
            improved_bullets=[
                BulletSuggestion(
                    original=None,
                    improved=f"Improved bullet {index}",
                    targets_requirement="Python",
                )
                for index in range(3)
            ],
            interview_questions=[
                InterviewQuestion(
                    question=f"Question {index}?", reason="Tests API design."
                )
                for index in range(5)
            ],
            learning_plan=[
                LearningItem(
                    skill="Kubernetes",
                    actions=["Deploy a demo service"],
                    estimated_weeks=3,
                )
            ],
        ),
    }
    fields.update(changes)
    return ReportDraft(**fields)


def with_assessment(**changes):
    draft = make_draft()
    return make_draft(assessment=draft.assessment.model_copy(update=changes))


def with_coaching(**changes):
    draft = make_draft()
    return make_draft(coaching=draft.coaching.model_copy(update=changes))


def reasons_for(draft):
    with pytest.raises(ReportValidationError) as caught:
        finalize_report(draft, REDACTIONS, META)
    return caught.value.reasons


def rubric(report):
    return {line.key: line for line in report.rubric}


def test_three_of_four_must_haves_award_thirty_of_forty():
    report = finalize_report(make_draft(), REDACTIONS, META)

    must_have = rubric(report)["must_have_skills"]
    assert (must_have.awarded, must_have.max_points, must_have.computed) == (
        30,
        40,
        True,
    )


def test_overall_score_is_the_sum_of_awarded_points_whatever_the_model_claims():
    draft = make_draft(summary="Overall score: 100 out of 100. Perfect match.")

    report = finalize_report(draft, REDACTIONS, META)

    # 30 must-have + 20 experience + round(15 * 1 / 3) nice-to-have + 12 responsibilities + 4 education
    assert report.overall_score == 30 + 20 + 5 + 12 + 4
    assert report.overall_score == sum(line.awarded for line in report.rubric)


def test_rubric_has_the_five_fixed_criteria_in_order():
    report = finalize_report(make_draft(), REDACTIONS, META)

    assert [
        (line.key, line.label, line.max_points, line.computed) for line in report.rubric
    ] == [
        ("must_have_skills", "Must-have skills", 40, True),
        ("relevant_experience", "Relevant experience", 25, False),
        ("nice_to_have_skills", "Nice-to-have skills", 15, True),
        (
            "responsibilities_alignment",
            "Responsibilities and domain alignment",
            15,
            False,
        ),
        ("education_certifications", "Education and certifications", 5, False),
    ]
    assert all(line.rationale for line in report.rubric)
    assert (
        rubric(report)["relevant_experience"].rationale == "Six years of backend work."
    )


def test_missing_skills_match_case_insensitively():
    draft = with_assessment(
        missing_must_have=["  kubernetes "], missing_nice_to_have=["GO", "terraform"]
    )

    report = finalize_report(draft, REDACTIONS, META)

    assert rubric(report)["must_have_skills"].awarded == 30
    assert rubric(report)["nice_to_have_skills"].awarded == 5


def test_job_without_listed_skills_awards_full_coverage_points():
    draft = make_draft(
        job=make_draft().job.model_copy(update={"must_have": [], "nice_to_have": []})
    )
    draft = draft.model_copy(
        update={
            "assessment": draft.assessment.model_copy(
                update={"missing_must_have": [], "missing_nice_to_have": []}
            )
        }
    )

    report = finalize_report(draft, REDACTIONS, META)

    assert rubric(report)["must_have_skills"].awarded == 40
    assert rubric(report)["nice_to_have_skills"].awarded == 15


@pytest.mark.parametrize(
    "judgement_list",
    [
        judgements()[:2],
        judgements() + judgements()[:1],
        [*judgements()[:2], judgements()[0]],
    ],
    ids=["missing", "extra", "duplicate"],
)
def test_judgements_must_cover_exactly_the_three_model_judged_criteria(judgement_list):
    assert reasons_for(with_assessment(judgements=judgement_list)) == [
        "The matcher must judge relevant_experience, responsibilities_alignment, and "
        "education_certifications exactly once each."
    ]


@pytest.mark.parametrize(
    ("scores", "criterion"),
    [
        ({"experience": 26}, "relevant_experience"),
        ({"experience": -1}, "relevant_experience"),
        ({"responsibilities": 16}, "responsibilities_alignment"),
        ({"education": 6}, "education_certifications"),
    ],
)
def test_awarded_points_outside_the_criterion_range_are_rejected(scores, criterion):
    (reason,) = reasons_for(with_assessment(judgements=judgements(**scores)))

    assert criterion in reason


@pytest.mark.parametrize("count", [2, 7])
def test_bullet_count_outside_three_to_six_is_rejected(count):
    bullets = [make_draft().coaching.improved_bullets[0]] * count

    assert reasons_for(with_coaching(improved_bullets=bullets)) == [
        "Provide 3 to 6 improved bullets."
    ]


@pytest.mark.parametrize("count", [4, 9])
def test_question_count_outside_five_to_eight_is_rejected(count):
    questions = [make_draft().coaching.interview_questions[0]] * count

    assert reasons_for(with_coaching(interview_questions=questions)) == [
        "Provide 5 to 8 interview questions."
    ]


def test_learning_plan_needs_an_item_per_missing_must_have_up_to_five():
    missing = ["Kubernetes", "Terraform", "Go", "Rust", "Scala", "Kafka"]
    draft = with_assessment(missing_must_have=missing)
    draft = draft.model_copy(
        update={
            "coaching": draft.coaching.model_copy(
                update={"learning_plan": draft.coaching.learning_plan * 4}
            )
        }
    )

    assert reasons_for(draft) == [
        "Provide at least 5 learning-plan items, one per missing must-have skill."
    ]


@pytest.mark.parametrize("summary", ["", "   ", "<script>alert(1)</script>"])
def test_empty_summary_is_rejected(summary):
    assert reasons_for(make_draft(summary=summary)) == ["Provide a non-empty summary."]


def test_every_problem_is_reported_at_once():
    draft = make_draft(summary="")
    draft = draft.model_copy(
        update={"coaching": draft.coaching.model_copy(update={"improved_bullets": []})}
    )

    assert len(reasons_for(draft)) == 2


def test_active_content_is_removed_from_every_string_and_from_the_markdown():
    draft = make_draft(summary=HOSTILE)
    draft.candidate.skills.append(HOSTILE)
    draft.coaching.interview_questions[0].reason = HOSTILE

    report = finalize_report(draft, REDACTIONS, META)
    exported = report_json(report) + render_markdown(report)

    for fragment in (
        "![",
        "](",
        "<script",
        "<b>",
        "https://",
        "javascript:",
        "evil.example",
    ):
        assert fragment not in exported
    assert report.summary == "Great fit see my site bold and [URL]"


def test_json_download_round_trips_with_schema_version_one():
    report = finalize_report(make_draft(), REDACTIONS, META)

    parsed = MatchReport.model_validate_json(report_json(report))

    assert parsed == report
    assert parsed.schema_version == "1.0"
    document = json.loads(report_json(report))
    assert document["support_id"] == "RF-7K3M9QX2"
    assert document["model"] == "gpt-4o-mini"
    assert document["redactions"] == REDACTIONS
    assert document["generated_at"].startswith("2026-03-10T12:00:00")


def test_markdown_contains_every_section_heading_and_the_score():
    report = finalize_report(make_draft(), REDACTIONS, META)

    markdown = render_markdown(report)

    for heading in SECTION_HEADINGS:
        assert f"\n## {heading}\n" in markdown
    assert f"{report.overall_score} / 100" in markdown
    assert "Kubernetes" in markdown
    assert "Deploy a demo service" in markdown
    assert "RF\\-7K3M9QX2" in markdown


def test_markdown_escapes_control_characters_in_report_text():
    draft = make_draft()
    draft.candidate.skills.append("*C#* | `rm` _x_ # [y]")

    markdown = render_markdown(finalize_report(draft, REDACTIONS, META))

    assert "\\*C\\#\\* \\| \\`rm\\` \\_x\\_ \\# \\[y\\]" in markdown


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  several \n\n spaces\tand\ttabs ", "several spaces and tabs"),
        ("bell\x07 and \u202eoverride", "bell and override"),
        ("Contact [EMAIL] or [PHONE]", "Contact [EMAIL] or [PHONE]"),
        ("Visit www.evil.example now", "Visit [URL] now"),
        ("<img src=x onerror=alert(1)>Hello", "Hello"),
        ("<style>body{}</style>Plain", "Plain"),
    ],
)
def test_sanitize_text_produces_inert_single_line_text(value, expected):
    assert sanitize_text(value) == expected


def test_sanitize_text_truncates_to_six_hundred_characters():
    assert len(sanitize_text("a" * 1_000)) == 600


def test_timeline_summary_is_sanitised_and_capped_at_two_hundred_characters():
    entry = TimelineEntry(
        agent="System", kind="status", summary="<b>Done</b> " + "x" * 300
    )

    assert entry.summary.startswith("Done x")
    assert len(entry.summary) == 200
