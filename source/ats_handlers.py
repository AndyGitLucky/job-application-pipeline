"""
ats_handlers.py
===============
Dedizierte Handler für die gängigsten ATS-Systeme.

Unterstützt:
  - Personio   (häufigste Wahl bei Münchner Startups/KMU)
  - Greenhouse (Tech-Firmen, internationale Startups)
  - Lever      (Tech-Firmen)
  - Workable   (KMU, internationale)
  - Generic    (Fallback für unbekannte Systeme)

Einbindung in auto_apply.py:
  from ats_handlers import apply_with_ats
  ok = apply_with_ats(meta, anschreiben)

Abhängigkeiten:
  pip install selenium webdriver-manager
"""

import logging
import time
import os
import re
from pathlib import Path

from source.env_utils import load_dotenv, env_flag

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        ElementNotInteractableException,
        ElementClickInterceptedException,
        StaleElementReferenceException,
    )
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    # detect_ats() soll auch ohne Selenium funktionieren.
    SELENIUM_AVAILABLE = False
    webdriver = None
    By = WebDriverWait = Select = EC = Service = Keys = ActionChains = None
    TimeoutException = NoSuchElementException = ElementNotInteractableException = ElementClickInterceptedException = StaleElementReferenceException = Exception
    ChromeDriverManager = None

log = logging.getLogger(__name__)

load_dotenv(Path(__file__))

# ─── Konfiguration ─────────────────────────────────────────────────────────────
CONFIG = {
    "review_mode":    env_flag("AUTO_APPLY_REVIEW_MODE", True),   # True = ausfüllen aber NICHT abschicken
    "headless":       env_flag("SELENIUM_HEADLESS", False),       # False = Browser sichtbar (empfohlen)
    "wait_timeout":   int(os.getenv("SELENIUM_FIELD_WAIT", "10")),
    "slow_mode":      True,   # True = menschliche Tipp-Geschwindigkeit simulieren
    "slow_delay":     0.05,   # Sekunden zwischen Tastendrücken
    "cv_path":        os.getenv("ATS_CV_PATH", os.getenv("SENDER_CV_PATH", "..\\CVs\\Andreas_Eichmann_CV.pdf")),
}

CANDIDATE = {
    "first_name": os.getenv("ATS_FIRST_NAME", "Andreas"),
    "last_name":  os.getenv("ATS_LAST_NAME",  "Eichmann"),
    "email":      os.getenv("ATS_EMAIL",      "andreas.eichmann@hotmail.com"),
    "phone":      os.getenv("ATS_PHONE",      "0176 3866 3585"),
    "city":       os.getenv("ATS_CITY",       "München"),
    "country":    os.getenv("ATS_COUNTRY",    "Deutschland"),
    "linkedin":   os.getenv("ATS_LINKEDIN",   "https://linkedin.com/in/andreas-eichmann"),
    # In vielen ATS-Formularen gibt es nur ein "Website" Feld. Default: GitHub Profil.
    "portfolio":  os.getenv("ATS_PORTFOLIO",  "https://github.com/AndyGitLucky"),
    "github":     os.getenv("ATS_GITHUB",     "https://github.com/AndyGitLucky"),
}

# ─── ATS-Erkennung ─────────────────────────────────────────────────────────────

ATS_SIGNATURES = {
    "personio":    ["personio.de", "personio.com", "/recruiting/"],
    "greenhouse":  ["greenhouse.io", "boards.greenhouse.io"],
    "lever":       ["lever.co", "jobs.lever.co"],
    "workable":    ["workable.com", "apply.workable.com"],
    "successfactors": ["successfactors.com", "successfactors.eu"],
    "indeed":     ["indeed.", "/viewjob", "indeed.com/q-"],
}

def detect_ats(url: str) -> str:
    url_lower = url.lower()
    for ats, signatures in ATS_SIGNATURES.items():
        if any(sig in url_lower for sig in signatures):
            log.info(f"  ATS erkannt: {ats.upper()}")
            return ats
    log.info("  ATS: unbekannt → Generic-Handler")
    return "generic"


# ─── Browser-Factory ───────────────────────────────────────────────────────────

def get_driver():
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium nicht installiert. Installiere: pip install selenium webdriver-manager")
    options = webdriver.ChromeOptions()
    if CONFIG["headless"]:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Prefer a local chromedriver to avoid network downloads (webdriver_manager/Selenium Manager).
    chromedriver_path = (os.getenv("CHROMEDRIVER_PATH") or "").strip()
    if chromedriver_path and Path(chromedriver_path).exists():
        driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    # Try Selenium's built-in manager (may still download once, but often works out-of-the-box).
    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception:
        pass

    # Fallback: webdriver_manager (may require internet access).
    if ChromeDriverManager is None:
        raise RuntimeError("ChromeDriver nicht gefunden. Setze CHROMEDRIVER_PATH oder installiere webdriver-manager.")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def wait_for(driver, selector, by=None, timeout=None) -> object:
    if by is None:
        by = By.CSS_SELECTOR
    t = timeout or CONFIG["wait_timeout"]
    return WebDriverWait(driver, t).until(
        EC.presence_of_element_located((by, selector))
    )


def slow_type(element, text: str):
    """Tippt Text mit menschlicher Geschwindigkeit."""
    if CONFIG["slow_mode"]:
        for char in text:
            element.send_keys(char)
            time.sleep(CONFIG["slow_delay"])
    else:
        element.send_keys(text)


def safe_find(driver, selector: str, by=None):
    if by is None:
        by = By.CSS_SELECTOR
    try:
        return driver.find_element(by, selector)
    except NoSuchElementException:
        return None


def safe_fill(driver, selector: str, value: str, by=None) -> bool:
    el = safe_find(driver, selector, by)
    if el:
        el.clear()
        slow_type(el, value)
        return True
    return False


def safe_fill_by_label(driver, label_hint: str, value: str) -> bool:
    """
    Greenhouse/ATS haben oft Custom Questions, bei denen die Input-IDs dynamisch sind.
    Wir suchen daher das Feld ueber das zugehoerige Label (z.B. "LinkedIn Profile", "Website").
    """
    if not label_hint or not value:
        return False

    hint = label_hint.strip().lower()
    xpath = (
        "//label[contains(translate(normalize-space(.),"
        " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'),"
        f" '{hint}')]"
    )
    labels = driver.find_elements(By.XPATH, xpath)
    for lab in labels:
        try:
            target = None
            for_attr = (lab.get_attribute("for") or "").strip()
            if for_attr:
                target = safe_find(driver, f"//*[@id='{for_attr}']", by=By.XPATH)
            if not target:
                target = safe_find(driver, ".//following::input[1]", by=By.XPATH)
            if target and target.is_enabled():
                target.click()
                try:
                    target.clear()
                except Exception:
                    pass
                slow_type(target, value)
                return True
        except Exception:
            continue
    return False


def safe_upload(driver, selector: str, file_path: str) -> bool:
    el = safe_find(driver, selector)
    if el and Path(file_path).exists():
        try:
            # Some ATS hide the real file input; attempt to make it temporarily usable.
            driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                el,
            )
        except Exception:
            pass
        try:
            el.send_keys(str(Path(file_path).resolve()))
            time.sleep(1)
            return True
        except Exception:
            return False
    return False


# ─── Basis-Handler ─────────────────────────────────────────────────────────────

class BaseHandler:
    def __init__(self, driver, meta: dict | None = None):
        self.driver = driver
        self.wait   = WebDriverWait(driver, CONFIG["wait_timeout"])
        self.meta = meta or {}

    def _cover_letter_path(self) -> str:
        return (self.meta.get("cover_letter_path") or "").strip()

    def fill_cover_letter(self, text: str) -> bool:
        selectors = [
            "textarea[name*='cover']",
            "textarea[name*='anschreiben']",
            "textarea[name*='motivation']",
            "textarea[id*='cover']",
            "textarea[placeholder*='Cover']",
            "textarea[placeholder*='Anschreiben']",
            "div[contenteditable='true']",
        ]
        for sel in selectors:
            el = safe_find(self.driver, sel)
            if el:
                el.click()
                el.clear()
                slow_type(el, text)
                log.info("    ✓ Anschreiben eingetragen")
                return True
        return False

    def upload_cv(self) -> bool:
        selectors = [
            "input[type='file'][name*='cv']",
            "input[type='file'][name*='resume']",
            "input[type='file'][name*='lebenslauf']",
            "input[type='file'][accept*='.pdf']",
            "input[type='file'][accept*='.doc']",
            "input[type='file']",
        ]
        for sel in selectors:
            if safe_upload(self.driver, sel, CONFIG["cv_path"]):
                log.info("    ✓ CV hochgeladen")
                return True
        return False

    def upload_cover_letter(self) -> bool:
        path = self._cover_letter_path()
        if not path:
            return False

        selectors = [
            "input[id='cover_letter']",
            "input[name='job_application[cover_letter]']",
            "input[type='file'][name*='cover_letter']",
            "input[type='file'][name*='cover']",
            "input[type='file'][name*='anschreiben']",
            "input[type='file'][name*='motivation']",
            "input[type='file'][name*='application_documents'][name*='cover']",
            "input[type='file'][data-qa*='cover']",
            "input[type='file']",
        ]

        for sel in selectors:
            if safe_upload(self.driver, sel, path):
                log.info("    ✓ Cover Letter hochgeladen")
                return True
        return False

    def submit(self) -> bool:
        if CONFIG["review_mode"]:
            log.info("    [REVIEW] Submit NICHT geklickt (review_mode=True)")
            return True
        selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button[data-ui='submit']",
            "*[class*='submit']",
        ]
        for sel in selectors:
            el = safe_find(self.driver, sel)
            if el:
                el.click()
                log.info("    ✓ Formular abgeschickt")
                return True
        log.warning("    Submit-Button nicht gefunden")
        return False


# ─── Personio Handler ──────────────────────────────────────────────────────────

class PersonioHandler(BaseHandler):
    """
    Personio ist das häufigste ATS bei Münchner Startups.
    URL-Muster: https://FIRMA.personio.de/job/XXXXX
    Formular-Struktur: einzelne Seite mit Standardfeldern + Datei-Upload
    """

    def _accept_cookies_best_effort(self) -> None:
        """Best-effort Cookie Banner Click (varies per site/language)."""
        try:
            # Common cookie buttons (German/English). We keep this intentionally broad.
            texts = [
                "alle akzeptieren",
                "akzeptieren",
                "accept all",
                "i agree",
                "agree",
            ]
            for t in texts:
                xpath = (
                    "//button[contains(translate(normalize-space(.),"
                    " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'),"
                    f" '{t}')]"
                )
                buttons = self.driver.find_elements(By.XPATH, xpath)
                for b in buttons[:2]:
                    try:
                        if b.is_displayed() and b.is_enabled():
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                            b.click()
                            time.sleep(1)
                            return
                    except Exception:
                        continue
        except Exception:
            pass

    def _is_on_form(self) -> bool:
        # Heuristic (strict-ish): only count as "form open" if we see typical application inputs.
        try:
            if self.driver.find_elements(By.CSS_SELECTOR, "input[data-qa^='input-']"):
                return True
        except Exception:
            pass

        markers = [
            "input[data-qa='input-first_name']",
            "input[name='first_name']",
            "#first_name",
            "input[data-qa='input-email']",
            "input[name='email']",
            "input[type='email']",
        ]
        for sel in markers:
            if safe_find(self.driver, sel):
                return True

        # Fallback: combination of email + file input is a strong signal.
        try:
            if self.driver.find_elements(By.CSS_SELECTOR, "input[type='email']") and self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                return True
        except Exception:
            pass

        return False

    def _find_apply_button(self):
        # Prefer specific selectors first.
        selectors = [
            "a[data-qa*='apply']",
            "button[data-qa*='apply']",
            "a[href*='#apply']",
        ]
        for sel in selectors:
            el = safe_find(self.driver, sel)
            if el and el.is_displayed() and el.is_enabled():
                return el

        # Fallback: click by visible text.
        texts = [
            "apply for this job",
            "apply now",
            "apply",
            "jetzt bewerben",
            "bewerben",
        ]
        for t in texts:
            xpath = (
                "(//a|//button)[contains(translate(normalize-space(.),"
                " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'),"
                f" '{t}')]"
            )
            for el in self.driver.find_elements(By.XPATH, xpath)[:3]:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        return None

    def _describe_el(self, el) -> str:
        try:
            tag = (el.tag_name or "").lower()
        except Exception:
            tag = "?"
        try:
            txt = (el.text or "").strip().replace("\n", " ")
        except Exception:
            txt = ""
        try:
            href = (el.get_attribute("href") or "").strip()
        except Exception:
            href = ""
        txt = (txt[:80] + "...") if len(txt) > 80 else txt
        href = (href[:120] + "...") if len(href) > 120 else href
        parts = [f"tag={tag}"]
        if txt:
            parts.append(f"text='{txt}'")
        if href:
            parts.append(f"href='{href}'")
        return " ".join(parts)

    def _human_click(self, el) -> bool:
        """Try a real user-like click before falling back to JS click."""
        try:
            self.driver.switch_to.default_content()
        except Exception:
            pass
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass

        # 1) Normal WebElement click (preferred)
        try:
            el.click()
            return True
        except Exception:
            pass

        # 2) ActionChains click (often triggers 'trusted' events better than JS click)
        try:
            ActionChains(self.driver).move_to_element(el).pause(0.2).click(el).perform()
            return True
        except Exception:
            pass

        # 3) Keyboard activate
        try:
            el.send_keys(Keys.ENTER)
            return True
        except Exception:
            pass

        # 4) JS click (last resort; may not trigger trusted handlers)
        try:
            self.driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False

    def _wait_for_form_after_click(self, timeout: int = 12) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(lambda d: self._is_on_form() or self._try_switch_to_form_iframe())
            return True
        except Exception:
            return False

    def _js_set_value(self, el, value: str) -> bool:
        try:
            self.driver.execute_script(
                """
                const el = arguments[0];
                const val = arguments[1];
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                """,
                el,
                value,
            )
            return True
        except Exception:
            return False

    def _dispatch_click_events(self, el) -> bool:
        """
        Dispatch a richer click event sequence. Some pages ignore a plain JS click.
        This still doesn't create "trusted" events, but improves compatibility.
        """
        try:
            self.driver.execute_script(
                """
                const el = arguments[0];
                const rect = el.getBoundingClientRect();
                const cx = rect.left + rect.width / 2;
                const cy = rect.top + rect.height / 2;
                const opts = {bubbles:true, cancelable:true, view:window, clientX:cx, clientY:cy};
                const types = ['pointerover','pointermove','pointerdown','mousedown','pointerup','mouseup','click'];
                for (const t of types) {
                  try { el.dispatchEvent(new MouseEvent(t, opts)); } catch (e) {}
                }
                """,
                el,
            )
            return True
        except Exception:
            return False

    def _personio_apply_url_variants(self, url: str) -> list[str]:
        base = (url or "").strip()
        if not base:
            return []
        out: list[str] = []
        # Order matters: "display=apply" worked for Agile Robots; try it first.
        candidates = ["apply", "application_form", "application"]
        if re.search(r"(^|[?&])display=", base, flags=re.IGNORECASE):
            for c in candidates:
                out.append(re.sub(r"(display=)[^&]+", rf"\1{c}", base, flags=re.IGNORECASE))
        else:
            sep = "&" if "?" in base else "?"
            for c in candidates:
                out.append(base + f"{sep}display={c}")

        # Hash-based apply (less reliable on some Personio pages)
        out.append(base.split("#")[0] + "#apply")

        seen: set[str] = set()
        uniq: list[str] = []
        for u in out:
            if u not in seen:
                uniq.append(u)
                seen.add(u)
        return uniq

    def _safe_fill_el(self, el, value: str) -> bool:
        if not value:
            return False
        try:
            if not el.is_displayed() or not el.is_enabled():
                return False
        except Exception:
            return False
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        try:
            ActionChains(self.driver).move_to_element(el).pause(0.15).click(el).perform()
        except Exception:
            try:
                el.click()
            except Exception:
                pass
        try:
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
        except Exception:
            try:
                el.clear()
            except Exception:
                pass
        try:
            slow_type(el, value)
            return True
        except ElementNotInteractableException:
            return self._js_set_value(el, value)

    def _fill_by_keywords(self, keywords: list[str], value: str) -> bool:
        """Find a visible enabled input by keyword match on name/id/placeholder/aria-label."""
        if not value:
            return False
        kws = [k.strip().lower() for k in keywords if k and k.strip()]
        if not kws:
            return False
        try:
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input, textarea")
        except Exception:
            inputs = []

        for el in inputs:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag = (el.tag_name or "").lower()
                typ = (el.get_attribute("type") or "").lower()
                if tag == "input" and typ in ("hidden", "submit", "button", "checkbox", "radio", "file"):
                    continue
                hay = " ".join(
                    [
                        (el.get_attribute("name") or ""),
                        (el.get_attribute("id") or ""),
                        (el.get_attribute("placeholder") or ""),
                        (el.get_attribute("aria-label") or ""),
                    ]
                ).lower()
                if not hay.strip():
                    continue
                if any(k in hay for k in kws):
                    if self._safe_fill_el(el, value):
                        return True
            except Exception:
                continue
        return False

    def _fill_url_fields_best_effort(self) -> int:
        """
        If Personio custom questions render URL fields without stable labels,
        fill first empty URL-like field with LinkedIn and second with GitHub/Portfolio.
        """
        filled = 0
        try:
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input, textarea")
        except Exception:
            inputs = []

        url_like = []
        for el in inputs:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag = (el.tag_name or "").lower()
                typ = (el.get_attribute("type") or "").lower()
                if tag == "input" and typ in ("hidden", "submit", "button", "checkbox", "radio", "file"):
                    continue
                hay = " ".join(
                    [
                        typ,
                        (el.get_attribute("name") or ""),
                        (el.get_attribute("id") or ""),
                        (el.get_attribute("placeholder") or ""),
                        (el.get_attribute("aria-label") or ""),
                    ]
                ).lower()
                if ("url" in hay) or ("http" in hay) or ("link" in hay) or typ == "url":
                    url_like.append(el)
            except Exception:
                continue

        # Only fill empty ones
        empties = []
        for el in url_like:
            try:
                cur = (el.get_attribute("value") or "").strip()
                if not cur:
                    empties.append(el)
            except Exception:
                continue

        if empties:
            if self._safe_fill_el(empties[0], CANDIDATE["linkedin"]):
                filled += 1
            if len(empties) > 1:
                if self._safe_fill_el(empties[1], CANDIDATE["github"] or CANDIDATE["portfolio"]):
                    filled += 1
        return filled

    def _debug_dump_visible_fields(self, limit: int = 80) -> None:
        if not env_flag("ATS_DEBUG_FIELDS", False):
            return
        try:
            els = self.driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        except Exception:
            return
        log.info("    [DEBUG] Sichtbare Felder (name/id/type/placeholder/aria):")
        n = 0
        for el in els:
            if n >= limit:
                break
            try:
                if not el.is_displayed():
                    continue
                tag = (el.tag_name or "").lower()
                typ = (el.get_attribute("type") or "").lower()
                name = (el.get_attribute("name") or "").strip()
                _id = (el.get_attribute("id") or "").strip()
                ph = (el.get_attribute("placeholder") or "").strip()
                aria = (el.get_attribute("aria-label") or "").strip()
                if tag == "input" and typ in ("hidden",):
                    continue
                log.info(f"    [DEBUG] {tag} type={typ} name='{name}' id='{_id}' placeholder='{ph}' aria='{aria}'")
                n += 1
            except Exception:
                continue

    def _safe_fill_field(self, field_name: str, selector: str, value: str) -> bool:
        if not value:
            return False
        # Try all candidate selectors; pick the first interactable element.
        for sel in [s.strip() for s in selector.split(",") if s.strip()]:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                els = []
            for el in els[:3]:
                try:
                    if not el.is_displayed() or not el.is_enabled():
                        continue
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    except Exception:
                        pass

                    # Click and focus
                    try:
                        ActionChains(self.driver).move_to_element(el).pause(0.15).click(el).perform()
                    except Exception:
                        try:
                            el.click()
                        except Exception:
                            pass

                    # Clear robustly
                    try:
                        el.send_keys(Keys.CONTROL, "a")
                        el.send_keys(Keys.BACKSPACE)
                    except Exception:
                        try:
                            el.clear()
                        except Exception:
                            pass

                    # Type
                    try:
                        slow_type(el, value)
                        return True
                    except ElementNotInteractableException:
                        # Last resort: set via JS + events
                        if self._js_set_value(el, value):
                            return True
                except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
                    continue
                except Exception:
                    continue
        return False

    def _try_switch_to_form_iframe(self) -> bool:
        """Some sites embed the application form in an iframe."""
        try:
            self.driver.switch_to.default_content()
            frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe")
            for idx, fr in enumerate(frames[:10]):
                try:
                    self.driver.switch_to.default_content()
                    self.driver.switch_to.frame(fr)
                    if self._is_on_form():
                        log.info(f"    [Personio] Formular in iframe gefunden (index={idx})")
                        return True
                except Exception:
                    continue
            self.driver.switch_to.default_content()
        except Exception:
            pass
        return False

    def _scroll_until_form(self, steps: int = 10) -> bool:
        """Trigger lazy-load by scrolling down after clicking Apply."""
        try:
            self.driver.switch_to.default_content()
            for i in range(max(1, steps)):
                if self._is_on_form():
                    return True
                if self._try_switch_to_form_iframe():
                    return True
                self.driver.execute_script("window.scrollBy(0, Math.max(600, window.innerHeight));")
                time.sleep(0.6)
            return self._is_on_form() or self._try_switch_to_form_iframe()
        except Exception:
            return False

    def _open_application_form(self) -> bool:
        """
        Personio job pages often show a job detail first. The actual application form is shown
        only after clicking "Apply for this job" / "Jetzt bewerben".
        """
        self._accept_cookies_best_effort()

        # If an apply button exists, click it even if the page contains other forms.
        apply_btn = self._find_apply_button()
        if apply_btn:
            log.info(f"    [Personio] Apply-Button gefunden: {self._describe_el(apply_btn)}")

            # Wait until it is actually clickable (not covered by overlays).
            try:
                WebDriverWait(self.driver, 8).until(lambda d: apply_btn.is_displayed() and apply_btn.is_enabled())
            except Exception:
                pass

            before_url = (self.driver.current_url or "")
            ok = self._human_click(apply_btn)
            log.info(f"    [Personio] Apply-Button geklickt ({'ok' if ok else 'failed'})")

            # Sometimes the first click only scrolls/focuses; try a second click quickly.
            time.sleep(0.8)
            if not (self._is_on_form() or self._try_switch_to_form_iframe()):
                try:
                    ok2 = self._human_click(apply_btn)
                    if ok2:
                        log.info("    [Personio] Apply-Button erneut geklickt (retry)")
                except Exception:
                    pass

            # Dispatch richer click events (helps on some sites)
            if not (self._is_on_form() or self._try_switch_to_form_iframe()):
                try:
                    if self._dispatch_click_events(apply_btn):
                        log.info("    [Personio] Apply-Events dispatch()")
                except Exception:
                    pass

            # Wait/probe for form appearance.
            if self._wait_for_form_after_click(timeout=10):
                return True

            # If URL hash navigation exists, try it.
            try:
                href = (apply_btn.get_attribute("href") or "").strip()
                if href.startswith("#"):
                    self.driver.get(before_url.split("#")[0] + href)
                elif "#apply" not in (before_url.lower()):
                    self.driver.get(before_url.split("#")[0] + "#apply")
                time.sleep(1.0)
            except Exception:
                pass

            if self._wait_for_form_after_click(timeout=6):
                return True
            if self._scroll_until_form():
                return True

            # Try direct URL variants to bypass click handlers entirely.
            for u in self._personio_apply_url_variants(before_url):
                try:
                    if (self.driver.current_url or "").strip() != u:
                        log.info(f"    [Personio] Try URL: {u}")
                        self.driver.get(u)
                        time.sleep(1.2)
                        if self._wait_for_form_after_click(timeout=6) or self._scroll_until_form(steps=12):
                            return True
                except Exception:
                    continue
        else:
            log.info("    [Personio] Kein Apply-Button gefunden (evtl. schon im Formular)")
            if self._is_on_form() or self._try_switch_to_form_iframe():
                return True

        # Last resort: wait a bit (some pages auto-scroll to form after hash changes).
        try:
            log.info("    [Personio] Warte auf Formularfelder ...")
            WebDriverWait(self.driver, 10).until(lambda d: self._is_on_form() or self._try_switch_to_form_iframe())
            return True
        except Exception:
            # Try hash-navigation + scroll as final attempt
            try:
                if "#apply" not in (self.driver.current_url or ""):
                    self.driver.get(self.driver.current_url.split("#")[0] + "#apply")
                    time.sleep(1.0)
                if self._scroll_until_form(steps=12):
                    return True
            except Exception:
                pass

            # Review-mode helper: if automation can't open the form reliably, let the user click once.
            if CONFIG["review_mode"]:
                log.warning("    [Personio] Bitte einmal MANUELL auf 'Apply for this job' klicken (Review-Assist).")
                try:
                    WebDriverWait(self.driver, 60).until(lambda d: self._is_on_form() or self._try_switch_to_form_iframe())
                    log.info("    [Personio] Formular erkannt (nach manuellem Klick)")
                    return True
                except Exception:
                    pass
            return False

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Personio] Öffne: {url}")
        self.driver.get(url)
        time.sleep(3)

        if not self._open_application_form():
            log.warning("    [Personio] Formular nicht gefunden (Apply-Button evtl. anders / Login nötig)")
            # In review mode we still return True-ish to avoid marking as hard error
            # if the page requires a manual step (captcha/login).
            return CONFIG["review_mode"]

        # Guard: ensure we are really on the application form before filling.
        if not (self._is_on_form() or self._try_switch_to_form_iframe()):
            log.warning("    [Personio] Formular scheint noch nicht sichtbar zu sein (Lazy-Load).")
            if not self._scroll_until_form(steps=14):
                return CONFIG["review_mode"]

        self._debug_dump_visible_fields()

        filled = 0

        # Personio-spezifische Selektoren
        fields = {
            "Vorname":    ("input[data-qa='input-first_name'], input[name='first_name'], #first_name", CANDIDATE["first_name"]),
            "Nachname":   ("input[data-qa='input-last_name'], input[name='last_name'], #last_name",   CANDIDATE["last_name"]),
            "Email":      ("input[data-qa='input-email'], input[name='email'], input[type='email']",   CANDIDATE["email"]),
            "Telefon":    ("input[data-qa='input-phone'], input[name='phone'], input[type='tel']",     CANDIDATE["phone"]),
            "Ort":        ("input[data-qa='input-location'], input[name='location']",                  CANDIDATE["city"]),
            "LinkedIn":   ("input[name='linkedin'], input[placeholder*='LinkedIn']",                   CANDIDATE["linkedin"]),
            "Website":    ("input[name='website'], input[name*='website'], input[placeholder*='Website'], input[placeholder*='GitHub']", CANDIDATE["portfolio"]),
        }

        for name, (selector, value) in fields.items():
            ok = self._safe_fill_field(name, selector, value)
            if ok:
                log.info(f"    ✓ {name}")
                filled += 1
            else:
                log.info(f"    · {name} (nicht gefüllt)")

        # Robust via Labels (Custom Questions)
        try:
            linkedin_hints = ["LinkedIn", "LinkedIn Profile", "LinkedIn URL", "linkedin.com", "LinkedIn-Profil"]
            website_hints = ["Website", "Homepage", "Portfolio", "GitHub", "URL", "Webseite"]

            if any(safe_fill_by_label(self.driver, h, CANDIDATE["linkedin"]) for h in linkedin_hints):
                log.info("    ✓ LinkedIn (Label)")
                filled += 1
            if (
                any(safe_fill_by_label(self.driver, h, CANDIDATE["portfolio"]) for h in website_hints)
                or any(safe_fill_by_label(self.driver, h, CANDIDATE["github"]) for h in website_hints)
            ):
                log.info("    ✓ Website/GitHub (Label)")
                filled += 1
        except Exception:
            pass

        # Fallback: keyword scan (Personio custom fields can be named unpredictably)
        if self._fill_by_keywords(["linkedin"], CANDIDATE["linkedin"]):
            log.info("    ✓ LinkedIn (keyword)")
            filled += 1
        if self._fill_by_keywords(["github", "portfolio", "website", "homepage", "webseite", "url"], CANDIDATE["portfolio"]):
            log.info("    ✓ Website/GitHub (keyword)")
            filled += 1

        url_filled = self._fill_url_fields_best_effort()
        if url_filled:
            log.info(f"    ✓ URL-Felder gefüllt (best-effort): {url_filled}")
            filled += url_filled

        # Anschreiben (Personio hat oft ein "Message" oder "Motivationsschreiben" Feld)
        if self.fill_cover_letter(anschreiben) or self.upload_cover_letter():
            filled += 1

        # CV hochladen
        if self.upload_cv():
            filled += 1

        # Datenschutz-Checkbox (Personio hat meist eine)
        privacy_selectors = [
            "input[type='checkbox'][name*='privacy']",
            "input[type='checkbox'][name*='datenschutz']",
            "input[type='checkbox'][id*='gdpr']",
            "input[type='checkbox'][id*='consent']",
        ]
        for sel in privacy_selectors:
            el = safe_find(self.driver, sel)
            if el and not el.is_selected():
                el.click()
                log.info("    ✓ Datenschutz-Checkbox")
                filled += 1
                break

        log.info(f"    → {filled} Felder ausgefüllt")
        time.sleep(2)
        return self.submit()


# ─── Greenhouse Handler ────────────────────────────────────────────────────────

class GreenhouseHandler(BaseHandler):
    """
    Greenhouse wird von vielen internationalen Tech-Firmen genutzt.
    URL-Muster: https://boards.greenhouse.io/FIRMA/jobs/XXXXX
    Besonderheit: mehrseitiges Formular, Custom Questions
    """

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Greenhouse] Öffne: {url}")
        self.driver.get(url)
        time.sleep(3)

        filled = 0

        # Greenhouse Standard-Felder
        fields = {
            "Vorname":  ("input#first_name, input[name='job_application[first_name]']", CANDIDATE["first_name"]),
            "Nachname": ("input#last_name, input[name='job_application[last_name]']",   CANDIDATE["last_name"]),
            "Email":    ("input#email, input[name='job_application[email]']",            CANDIDATE["email"]),
            "Telefon":  ("input#phone, input[name='job_application[phone]']",            CANDIDATE["phone"]),
            "LinkedIn": ("input[name='job_application[answers_attributes][0][text_value]'], "
                         "input[placeholder*='LinkedIn']",                               CANDIDATE["linkedin"]),
            "Website":  ("input[name*='website'], input[placeholder*='Website'], "
                         "input[placeholder*='Portfolio']",                              CANDIDATE["portfolio"]),
        }

        for name, (selector, value) in fields.items():
            for sel in selector.split(", "):
                if safe_fill(self.driver, sel.strip(), value):
                    log.info(f"    ✓ {name}")
                    filled += 1
                    break

        # Robust: ueber Label finden (Custom Questions koennen ihre Indizes aendern)
        if safe_fill_by_label(self.driver, "LinkedIn", CANDIDATE["linkedin"]):
            log.info("    ✓ LinkedIn (Label)")
            filled += 1
        if safe_fill_by_label(self.driver, "Website", CANDIDATE["portfolio"]):
            log.info("    ✓ Website (Label)")
            filled += 1

        # Anschreiben
        if self.fill_cover_letter(anschreiben) or self.upload_cover_letter():
            filled += 1

        # CV hochladen – Greenhouse hat spezifische Upload-Zone
        cv_selectors = [
            "input[id='resume']",
            "input[name='job_application[resume]']",
            "input[type='file'][name*='resume']",
            "input[type='file']",
        ]
        for sel in cv_selectors:
            if safe_upload(self.driver, sel, CONFIG["cv_path"]):
                log.info("    ✓ CV hochgeladen")
                filled += 1
                break

        # Greenhouse hat oft "Education" und "Employment" Sektionen
        # Minimalausfüllung:
        self._fill_education()
        self._fill_location()

        log.info(f"    → {filled} Felder ausgefüllt")
        time.sleep(2)
        return self.submit()

    def _fill_education(self):
        """Greenhouse Education-Sektion – Minimalausfüllung."""
        try:
            school = safe_find(self.driver, "input[id*='school'], input[name*='school']")
            if school:
                slow_type(school, "Technische Universität München")
                degree_sel = safe_find(self.driver, "select[id*='degree'], select[name*='degree']")
                if degree_sel:
                    Select(degree_sel).select_by_visible_text("Bachelor's Degree")
                log.info("    ✓ Education (minimal)")
        except Exception:
            pass

    def _fill_location(self):
        """Greenhouse Location-Feld."""
        try:
            loc = safe_find(self.driver, "input[id='job_application_location']")
            if loc:
                loc.clear()
                slow_type(loc, "München, Deutschland")
                time.sleep(1)
                # Autocomplete-Auswahl
                suggestion = safe_find(self.driver, ".pac-item, [class*='suggestion']")
                if suggestion:
                    suggestion.click()
                log.info("    ✓ Standort")
        except Exception:
            pass


# ─── Lever Handler ─────────────────────────────────────────────────────────────

class LeverHandler(BaseHandler):
    """
    Lever wird von vielen Tech-Startups genutzt.
    URL-Muster: https://jobs.lever.co/FIRMA/UUID
    Besonderheit: React-basiertes Formular, oft mit Custom Questions
    """

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Lever] Öffne: {url}")
        self.driver.get(url)
        time.sleep(3)

        # Lever hat einen "Apply" Button auf der Job-Seite
        apply_btn = safe_find(self.driver, "a[href*='/apply'], button[class*='apply'], .postings-btn")
        if apply_btn:
            apply_btn.click()
            time.sleep(2)
            log.info("    ✓ Apply-Button geklickt")

        filled = 0

        fields = {
            "Name":     ("input[name='name'], input[id='name']",
                         f"{CANDIDATE['first_name']} {CANDIDATE['last_name']}"),
            "Email":    ("input[name='email'], input[id='email']",             CANDIDATE["email"]),
            "Telefon":  ("input[name='phone'], input[id='phone']",             CANDIDATE["phone"]),
            "LinkedIn": ("input[name='urls[LinkedIn]'], input[placeholder*='LinkedIn']", CANDIDATE["linkedin"]),
            "GitHub":   ("input[name='urls[GitHub]'], input[placeholder*='GitHub']",     CANDIDATE["github"]),
            "Portfolio":("input[name='urls[Portfolio]'], input[placeholder*='Portfolio']", CANDIDATE["portfolio"]),
        }

        for name, (selector, value) in fields.items():
            for sel in selector.split(", "):
                if safe_fill(self.driver, sel.strip(), value):
                    log.info(f"    ✓ {name}")
                    filled += 1
                    break

        # Anschreiben / Additional Info
        if self.fill_cover_letter(anschreiben):
            filled += 1

        # CV Upload
        cv_selectors = [
            "input[type='file'][name='resume']",
            "input[type='file'][class*='resume']",
            "input[type='file']",
        ]
        for sel in cv_selectors:
            if safe_upload(self.driver, sel, CONFIG["cv_path"]):
                log.info("    ✓ CV hochgeladen")
                filled += 1
                break

        log.info(f"    → {filled} Felder ausgefüllt")
        time.sleep(2)
        return self.submit()


# ─── Workable Handler ──────────────────────────────────────────────────────────

class WorkableHandler(BaseHandler):
    """
    Workable ist verbreitet bei mittelgroßen Unternehmen.
    URL-Muster: https://apply.workable.com/FIRMA/j/UUID
    """

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Workable] Öffne: {url}")
        self.driver.get(url)
        time.sleep(3)

        # Workable: "Apply for this job" Button
        apply_btn = safe_find(self.driver, "button[data-ui='apply-button'], a[data-ui='apply-button']")
        if apply_btn:
            apply_btn.click()
            time.sleep(2)

        filled = 0

        fields = {
            "Vorname":  ("input[name='firstname'], input[id='firstname']",  CANDIDATE["first_name"]),
            "Nachname": ("input[name='lastname'], input[id='lastname']",    CANDIDATE["last_name"]),
            "Email":    ("input[name='email'], input[type='email']",        CANDIDATE["email"]),
            "Telefon":  ("input[name='phone'], input[type='tel']",          CANDIDATE["phone"]),
            "LinkedIn": ("input[name='linkedin_profile_url']",              CANDIDATE["linkedin"]),
            "Website":  ("input[name='website']",                           CANDIDATE["portfolio"]),
        }

        for name, (selector, value) in fields.items():
            for sel in selector.split(", "):
                if safe_fill(self.driver, sel.strip(), value):
                    log.info(f"    ✓ {name}")
                    filled += 1
                    break

        if self.fill_cover_letter(anschreiben):
            filled += 1

        if self.upload_cv():
            filled += 1

        log.info(f"    → {filled} Felder ausgefüllt")
        time.sleep(2)
        return self.submit()


# ─── Indeed (Job-Board) ─────────────────────────────────────────────────────────

class IndeedHandler(BaseHandler):
    """
    Indeed ist kein klassisches ATS, aber oft der Einstiegspunkt (Job-Board).
    Im Review-Modus klicken wir nur Cookies + "Schnellbewerbung" an und stoppen dann,
    damit du den Bewerbungsflow sehen und manuell weiterklicken kannst.
    """

    def _click_cookie_banner(self) -> None:
        for selector in [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ]:
            el = safe_find(self.driver, selector)
            if el:
                el.click()
                time.sleep(1)
                return

        for xpath in [
            "//button[contains(.,'Alle Cookies akzeptieren')]",
            "//button[contains(.,'Alle ablehnen')]",
            "//button[contains(.,'Accept all')]",
            "//button[contains(.,'Reject all')]",
        ]:
            el = safe_find(self.driver, xpath, by=By.XPATH)
            if el:
                el.click()
                time.sleep(1)
                return

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Indeed] Öffne: {url}")
        self.driver.get(url)
        time.sleep(2)

        try:
            self._click_cookie_banner()
        except Exception:
            pass

        apply_btn = None
        for xpath in [
            "//a[contains(.,'Schnellbewerbung')]",
            "//button[contains(.,'Schnellbewerbung')]",
            "//a[contains(.,'Apply now')]",
            "//button[contains(.,'Apply now')]",
            "//a[contains(.,'Apply')]",
            "//button[contains(.,'Apply')]",
        ]:
            apply_btn = safe_find(self.driver, xpath, by=By.XPATH)
            if apply_btn:
                break

        if not apply_btn:
            log.error("  Indeed: Apply-Button nicht gefunden (evtl. Login/Cookie-Banner/Captcha)")
            return False

        apply_btn.click()
        time.sleep(2)

        if CONFIG["review_mode"]:
            log.info("    [REVIEW] Indeed-Flow gestartet (Schnellbewerbung geklickt) – stoppe hier")
            return True

        log.error("  Indeed: Live-Automation nicht implementiert (nur Review-Start).")
        return False


# ─── Generic Handler ───────────────────────────────────────────────────────────

class GenericHandler(BaseHandler):
    """
    Fallback für unbekannte ATS / eigene Bewerbungsformulare.
    Versucht gängige HTML-Feldnamen und Placeholder.
    """

    FIELD_SELECTORS = {
        "first_name": [
            "input[name*='first'], input[id*='first'], input[name*='vorname']",
            "//input[@placeholder[contains(.,'Vorname') or contains(.,'First name')]]",
        ],
        "last_name": [
            "input[name*='last'], input[id*='last'], input[name*='nachname']",
            "//input[@placeholder[contains(.,'Nachname') or contains(.,'Last name')]]",
        ],
        "email": [
            "input[type='email'], input[name*='email'], input[id*='email']",
        ],
        "phone": [
            "input[type='tel'], input[name*='phone'], input[name*='telefon']",
        ],
        "location": [
            "input[name*='city'], input[name*='location'], input[name*='ort']",
        ],
        "linkedin": [
            "input[name*='linkedin'], input[placeholder*='LinkedIn']",
        ],
    }

    def apply(self, url: str, anschreiben: str) -> bool:
        log.info(f"  [Generic] Öffne: {url}")
        self.driver.get(url)
        time.sleep(3)

        filled = 0
        values = {
            "first_name": CANDIDATE["first_name"],
            "last_name":  CANDIDATE["last_name"],
            "email":      CANDIDATE["email"],
            "phone":      CANDIDATE["phone"],
            "location":   CANDIDATE["city"],
            "linkedin":   CANDIDATE["linkedin"],
        }

        for field, selectors in self.FIELD_SELECTORS.items():
            value = values[field]
            for sel in selectors:
                by = By.XPATH if sel.startswith("//") else By.CSS_SELECTOR
                el = safe_find(self.driver, sel, by)
                if el:
                    el.clear()
                    slow_type(el, value)
                    log.info(f"    ✓ {field}")
                    filled += 1
                    break

        if self.fill_cover_letter(anschreiben):
            filled += 1

        if self.upload_cv():
            filled += 1

        log.info(f"    → {filled} Felder ausgefüllt")
        time.sleep(2)
        return self.submit()


# ─── Registry ──────────────────────────────────────────────────────────────────

HANDLERS = {
    "personio":   PersonioHandler,
    "greenhouse": GreenhouseHandler,
    "lever":      LeverHandler,
    "workable":   WorkableHandler,
    "indeed":     IndeedHandler,
    "generic":    GenericHandler,
}


# ─── Hauptfunktion (wird von auto_apply.py aufgerufen) ─────────────────────────

def apply_with_ats(meta: dict, anschreiben: str) -> bool:
    """
    Erkennt das ATS anhand der Job-URL und ruft den passenden Handler auf.
    Wird direkt von auto_apply.py aufgerufen.

    Args:
        meta:        Job-Metadaten (id, title, company, url, score)
        anschreiben: Generierter Anschreiben-Text

    Returns:
        True wenn erfolgreich (oder review_mode), False bei Fehler
    """
    url     = meta.get("url", "")
    ats     = detect_ats(url)
    handler_class = HANDLERS.get(ats, GenericHandler)

    log.info(f"  Handler: {handler_class.__name__}")

    driver = None
    try:
        driver  = get_driver()
        handler = handler_class(driver, meta)
        ok      = handler.apply(url, anschreiben)
        time.sleep(2)
        return ok

    except TimeoutException:
        log.error(f"  Timeout – Seite zu langsam oder Selector nicht gefunden")
        return False
    except Exception as e:
        log.error(f"  ATS-Handler Fehler ({ats}): {e}")
        return False
    finally:
        if driver:
            if not CONFIG["review_mode"]:
                driver.quit()
            else:
                log.info("  [REVIEW] Browser bleibt offen zur Kontrolle – manuell schließen")
                time.sleep(int(os.getenv("ATS_REVIEW_PAUSE_SECS", "30")))
                driver.quit()
