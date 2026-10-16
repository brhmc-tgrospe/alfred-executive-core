"""A.L.F.R.E.D. Autonomous Browser DOM & Persistent Session Engine.

Provides persistent-session web automation using Playwright Chromium:
1. browser_navigate_and_parse_dom: Launches/reuses persistent browser (.alfred_browser_profile),
   navigates to URL, auto-scrolls for lazy-loaded DOM, and extracts interactive elements.
2. browser_interact_dom_element: Clicks, types, or hovers elements by selector or text.
3. browser_scroll_and_inspect: Scrolls active page and summarizes visible DOM content.

All tools implement strict primitive type hints (str, int, bool) and docstrings
for clean schema reflection with the Gemini Multimodal Live API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from playwright.async_api import async_playwright, Playwright, BrowserContext, Page
except ImportError:
    async_playwright = None
    Playwright = None
    BrowserContext = None
    Page = None

logger = logging.getLogger("AlfredBrowserAutomation")


class BrowserAutomationLogistics:
    """Persistent Chromium browser automation and DOM interaction engine."""

    def __init__(self, profile_dir: Optional[str] = None) -> None:
        if profile_dir is None:
            # Default to .alfred_browser_profile in the project root
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.profile_dir = base_dir / ".alfred_browser_profile"
        else:
            self.profile_dir = Path(profile_dir)

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright: Optional[Any] = None
        self._context: Optional[Any] = None
        self._page: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Any:
        """Ensures a persistent Chromium browser context and active page are running."""
        if async_playwright is None:
            raise RuntimeError("Playwright is not installed. Please install playwright.")

        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

            if self._context is None:
                logger.info("[Browser] Launching persistent Chromium context at %s...", self.profile_dir)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=False,
                    viewport={"width": 1280, "height": 800},
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                    ],
                )

            if self._page is None or self._page.is_closed():
                pages = self._context.pages
                self._page = pages[0] if pages else await self._context.new_page()

            return self._page

    async def browser_navigate_and_parse_dom(
        self,
        url: str,
        search_query: str = "",
        scroll_full_page: bool = True,
    ) -> str:
        """Navigates to a webpage in the persistent browser, scrolls for lazy content, and extracts DOM structure.

        Parameters:
            url: The destination URL (e.g. 'https://github.com', 'google.com').
            search_query: Optional keyword to filter extracted text and elements.
            scroll_full_page: If True, scrolls down the page to trigger lazy-loaded dynamic content.

        Returns:
            A structured summary of the page title, URL, form inputs, actionable buttons/links, and main text.
        """
        target_url = url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = f"https://{target_url}"

        try:
            page = await self._ensure_browser()
            logger.info("[Browser] Navigating to %s...", target_url)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(500)

            if scroll_full_page:
                # Incrementally scroll to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(200)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(200)

            title = await page.title()
            current_url = page.url
            html_content = await page.content()

            # Parse DOM with BeautifulSoup
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html_content, "html.parser")
                # Remove non-content elements
                for element in soup(["script", "style", "noscript", "svg", "head"]):
                    element.decompose()

                # Extract interactive inputs
                inputs_summary = []
                for inp in soup.find_all(["input", "textarea", "select"])[:15]:
                    tag = inp.name
                    itype = inp.get("type", "text")
                    iname = inp.get("name", "")
                    iid = inp.get("id", "")
                    iplaceholder = inp.get("placeholder", "")
                    desc = f"<{tag} type='{itype}'"
                    if iid:
                        desc += f" id='{iid}'"
                    if iname:
                        desc += f" name='{iname}'"
                    if iplaceholder:
                        desc += f" placeholder='{iplaceholder}'"
                    desc += ">"
                    inputs_summary.append(desc)

                # Extract interactive buttons and key links
                buttons_summary = []
                for btn in soup.find_all(["button", "a"])[:20]:
                    text = btn.get_text(strip=True)
                    if text and len(text) < 40:
                        href = btn.get("href", "")
                        if href and not href.startswith(("#", "javascript:")):
                            buttons_summary.append(f"[{text}]({href[:60]})")
                        else:
                            buttons_summary.append(f"<button: {text}>")

                # Extract cleaned body text
                body_text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            else:
                inputs_summary = []
                buttons_summary = []
                lines = [title]

            # Filter by search_query if provided
            if search_query.strip():
                query = search_query.strip().lower()
                lines = [line for line in lines if query in line.lower()]
                buttons_summary = [b for b in buttons_summary if query in b.lower()]
                inputs_summary = [i for i in inputs_summary if query in i.lower()]

            text_snippet = "\n".join(lines[:35])
            if len(text_snippet) > 2000:
                text_snippet = text_snippet[:2000] + "\n...[truncated]"

            result_lines = [
                f"Page Title: {title}",
                f"URL: {current_url}",
                "",
                "Interactive Form Inputs:",
                "\n".join(f"  - {inp}" for inp in inputs_summary[:8]) if inputs_summary else "  (none)",
                "",
                "Actionable Buttons & Links:",
                "  " + ", ".join(buttons_summary[:12]) if buttons_summary else "  (none)",
                "",
                "DOM Content Extract:",
                text_snippet if text_snippet else "  (No textual content matching query)",
            ]

            return "\n".join(result_lines)

        except Exception as e:
            logger.error("[Browser] Navigation or parsing error: %s", e)
            return f"Browser navigation error for '{target_url}': {e}"

    async def browser_interact_dom_element(
        self,
        target_selector_or_text: str = "",
        action: str = "click",
        input_text: str = "",
        submit_enter: bool = False,
    ) -> str:
        """Interacts with a web element (click, type, fill, hover) or scrolls the active page.

        Parameters:
            target_selector_or_text: CSS selector, visible element text, or empty when scrolling.
            action: Action to perform: 'click', 'type', 'fill', 'hover', 'scroll_down', 'scroll_up'.
            input_text: Text string to type into input fields if action is 'type' or 'fill'.
            submit_enter: If True, presses the Enter key immediately after the action.

        Returns:
            Status message describing the interaction outcome and current page state.
        """
        act = action.lower().strip()
        if "scroll" in act:
            direction = "up" if "up" in act else "down"
            return await self.browser_scroll_and_inspect(direction=direction)

        if not target_selector_or_text.strip():
            return "Error: target_selector_or_text parameter cannot be empty."

        target = target_selector_or_text.strip()

        try:
            page = await self._ensure_browser()

            # Identify locator
            locator = None
            if target.startswith(("#", ".", "[", "//", "xpath=")) or ">" in target:
                locator = page.locator(target)
            else:
                # Try visible text or role matches
                try:
                    role_btn = page.get_by_role("button", name=re.compile(re.escape(target), re.IGNORECASE))
                    if await role_btn.count() > 0:
                        locator = role_btn
                except Exception:
                    pass

                if locator is None:
                    try:
                        text_loc = page.get_by_text(re.compile(re.escape(target), re.IGNORECASE))
                        if await text_loc.count() > 0:
                            locator = text_loc
                    except Exception:
                        pass

                if locator is None:
                    try:
                        placeholder_loc = page.get_by_placeholder(re.compile(re.escape(target), re.IGNORECASE))
                        if await placeholder_loc.count() > 0:
                            locator = placeholder_loc
                    except Exception:
                        pass

                if locator is None:
                    locator = page.locator(f"text={target}")

            # Verify locator presence with 4s timeout
            count = await locator.count()
            if count == 0:
                return f"Error: No visible DOM element found matching '{target}' on {page.url}."

            element = locator.first

            if act == "click":
                await element.click(timeout=6000)
            elif act in ("type", "fill"):
                await element.fill(input_text, timeout=6000)
            elif act == "hover":
                await element.hover(timeout=6000)
            elif act == "clear":
                await element.fill("", timeout=6000)
            elif act == "press_enter":
                await element.press("Enter", timeout=6000)
            else:
                return f"Error: Unsupported action '{action}'. Use 'click', 'type', 'fill', 'hover', 'clear', or 'press_enter'."

            if submit_enter and act != "press_enter":
                await page.keyboard.press("Enter")

            await page.wait_for_timeout(500)
            new_title = await page.title()
            new_url = page.url

            return f"Successfully performed '{act}' on '{target}'. Page title: '{new_title}', URL: {new_url}."

        except Exception as e:
            logger.error("[Browser] Interaction error on '%s': %s", target, e)
            return f"Browser interaction error on '{target}': {e}"

    async def browser_scroll_and_inspect(
        self,
        direction: str = "down",
        pixels: int = 800,
    ) -> str:
        """Scrolls the active browser page and returns an inspection summary of newly visible DOM elements.

        Parameters:
            direction: Direction to scroll: 'down' or 'up'.
            pixels: Number of pixels to scroll (default: 800).

        Returns:
            Summary of current viewport scroll position and visible page content.
        """
        try:
            page = await self._ensure_browser()
            delta = abs(pixels) if direction.lower() == "down" else -abs(pixels)
            await page.evaluate(f"window.scrollBy(0, {delta})")
            await page.wait_for_timeout(400)

            scroll_y = await page.evaluate("window.scrollY")
            title = await page.title()
            url = page.url

            # Extract visible text snippet
            html = await page.content()
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html, "html.parser")
                for s in soup(["script", "style", "noscript", "svg"]):
                    s.decompose()
                lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
                snippet = "\n".join(lines[10:35])[:1500]
            else:
                snippet = "(Page content updated)"

            return (
                f"Scrolled {direction} by {abs(pixels)}px. Current scroll position: Y={scroll_y}.\n"
                f"Page Title: {title}\nURL: {url}\nVisible Content:\n{snippet}"
            )

        except Exception as e:
            logger.error("[Browser] Scroll error: %s", e)
            return f"Browser scroll error: {e}"

    async def close(self) -> None:
        """Gracefully closes the persistent browser context and Playwright process."""
        async with self._lock:
            try:
                if self._context is not None:
                    await self._context.close()
                    self._context = None
                if self._playwright is not None:
                    await self._playwright.stop()
                    self._playwright = None
                self._page = None
                logger.info("[Browser] Persistent browser closed.")
            except Exception as e:
                logger.warning("[Browser] Error closing browser: %s", e)
