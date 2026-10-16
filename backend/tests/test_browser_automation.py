"""Unit tests for A.L.F.R.E.D. Autonomous Browser DOM & Persistent Session Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.tools.browser_automation import BrowserAutomationLogistics


@pytest.fixture
def mock_browser_logistics(tmp_path):
    logistics = BrowserAutomationLogistics(profile_dir=str(tmp_path / "test_browser_profile"))
    return logistics


@pytest.mark.asyncio
async def test_browser_navigate_and_parse_dom(mock_browser_logistics):
    """Verifies page navigation, scrolling, and DOM extraction of buttons, forms, and content."""
    mock_page = AsyncMock()
    mock_page.title = AsyncMock(return_value="GitHub: Let's build from here")
    mock_page.url = "https://github.com"
    mock_page.content = AsyncMock(return_value="""
        <html>
            <head><title>GitHub</title></head>
            <body>
                <header>
                    <a href="/login">Sign In</a>
                    <button id="nav-toggle">Menu</button>
                </header>
                <main>
                    <form action="/search">
                        <input type="text" name="q" id="query-input" placeholder="Search GitHub" />
                        <button type="submit">Search</button>
                    </form>
                    <p>Where the world builds software. Millions of developers and companies build.</p>
                </main>
            </body>
        </html>
    """)

    with patch.object(mock_browser_logistics, "_ensure_browser", return_value=mock_page):
        # 1. Unfiltered navigation with auto-scroll
        res = await mock_browser_logistics.browser_navigate_and_parse_dom("github.com", scroll_full_page=True)
        assert "Page Title: GitHub: Let's build from here" in res
        assert "URL: https://github.com" in res
        assert "<input type='text' id='query-input' name='q' placeholder='Search GitHub'>" in res
        assert "Sign In" in res
        assert "Where the world builds software" in res

        # 2. Filtered navigation by search_query
        filtered_res = await mock_browser_logistics.browser_navigate_and_parse_dom(
            "https://github.com", search_query="Search", scroll_full_page=False
        )
        assert "Search GitHub" in filtered_res
        assert "Where the world builds" not in filtered_res


@pytest.mark.asyncio
async def test_browser_interact_dom_element_actions(mock_browser_logistics):
    """Verifies click, type/fill, hover, and Enter key submission on dynamic web elements."""
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_locator.click = AsyncMock()
    mock_locator.fill = AsyncMock()
    mock_locator.hover = AsyncMock()
    mock_locator.press = AsyncMock()
    mock_locator.first = mock_locator

    mock_keyboard = MagicMock()
    mock_keyboard.press = AsyncMock()

    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.title = AsyncMock(return_value="Search Results")
    mock_page.url = "https://github.com/search?q=alfred"
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_page.keyboard = mock_keyboard
    mock_page.wait_for_timeout = AsyncMock()

    with patch.object(mock_browser_logistics, "_ensure_browser", return_value=mock_page):
        # 1. Click interaction
        click_res = await mock_browser_logistics.browser_interact_dom_element("#submit-btn", action="click")
        assert "Successfully performed 'click' on '#submit-btn'" in click_res
        mock_locator.click.assert_called_once()

        # 2. Type/Fill interaction with submit_enter
        type_res = await mock_browser_logistics.browser_interact_dom_element(
            "input[name=q]", action="type", input_text="alfred executive core", submit_enter=True
        )
        assert "Successfully performed 'type' on 'input[name=q]'" in type_res
        mock_locator.fill.assert_called_with("alfred executive core", timeout=6000)
        mock_page.keyboard.press.assert_called_with("Enter")

        # 3. Empty target error
        empty_res = await mock_browser_logistics.browser_interact_dom_element("", action="click")
        assert "Error: target_selector_or_text parameter cannot be empty" in empty_res

        # 4. Unsupported action
        bad_action_res = await mock_browser_logistics.browser_interact_dom_element("#btn", action="teleport")
        assert "Error: Unsupported action 'teleport'" in bad_action_res


@pytest.mark.asyncio
async def test_browser_scroll_and_inspect(mock_browser_logistics):
    """Verifies scrolling down/up and viewport inspection."""
    mock_page = AsyncMock()
    mock_page.title = AsyncMock(return_value="Active Dashboard")
    mock_page.url = "https://example.com/dashboard"
    mock_page.evaluate = AsyncMock(side_effect=[None, 1600])
    mock_page.content = AsyncMock(return_value="<html><body><div>Section 1</div><div>Section 2</div></body></html>")

    with patch.object(mock_browser_logistics, "_ensure_browser", return_value=mock_page):
        res = await mock_browser_logistics.browser_scroll_and_inspect(direction="down", pixels=800)
        assert "Scrolled down by 800px" in res
        assert "Current scroll position: Y=1600" in res
        assert "Page Title: Active Dashboard" in res


@pytest.mark.asyncio
async def test_browser_close(mock_browser_logistics):
    """Verifies graceful context and playwright shutdown."""
    mock_context = AsyncMock()
    mock_playwright = AsyncMock()

    mock_browser_logistics._context = mock_context
    mock_browser_logistics._playwright = mock_playwright
    mock_browser_logistics._page = AsyncMock()

    await mock_browser_logistics.close()

    mock_context.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    assert mock_browser_logistics._context is None
    assert mock_browser_logistics._playwright is None
    assert mock_browser_logistics._page is None
