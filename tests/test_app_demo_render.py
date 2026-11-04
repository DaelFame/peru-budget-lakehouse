"""The dashboard must boot against the committed demo layer in demo mode.

This is the only test that exercises app.py end to end: every query, every
component and the demo-mode branches. Without it, a broken render path is only
discovered by opening the browser.
"""

from streamlit.testing.v1 import AppTest

REQUIRED_KPI_LABELS = {
    "Total Planned Budget (PIM)",
    "Total Executed Budget",
    "PIM/devengado pair coverage",
}

DISABLED_KPI_LABELS = {"Budget Execution Rate", "Unexecuted Budget Gap"}


def run_app() -> AppTest:
    app = AppTest.from_file("app.py", default_timeout=120)
    app.run()
    return app


def test_dashboard_renders_without_exceptions():
    app = run_app()

    assert [str(exception.value) for exception in app.exception] == []


def test_demo_mode_reports_coverage_instead_of_rates():
    app = run_app()
    labels = {metric.label for metric in app.metric}

    assert REQUIRED_KPI_LABELS <= labels
    assert labels.isdisjoint(DISABLED_KPI_LABELS)


def test_demo_mode_states_the_sampling_caveat():
    app = run_app()
    texts = [info.value for info in app.info] + [caption.value for caption in app.caption]

    assert any("Built from a sample" in text for text in texts)
