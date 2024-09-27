import pytest


@pytest.fixture(scope="module")
def libretexts_slug() -> str:
    return "geo"


@pytest.fixture(scope="module")
def libretexts_url(libretexts_slug: str) -> str:
    return f"https://{libretexts_slug}.libretexts.org"


@pytest.fixture(scope="module")
def home_png_size() -> int:
    return 13461


@pytest.fixture(scope="module")
def home_welcome_text_paragraphs() -> list[str]:
    return [
        "Welcome to the Geosciences Library. This Living Library is a principal hub of "
        "the LibreTexts project, which is a multi-institutional collaborative venture "
        "to develop the next generation of open-access texts to improve postsecondary "
        "education at all levels of higher learning. The LibreTexts approach is highly "
        "collaborative where an Open Access textbook environment is under constant "
        "revision by students, faculty, and outside experts to supplant conventional "
        "paper-based books."
    ]
