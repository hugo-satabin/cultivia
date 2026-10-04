"""Uploaders navigateur (Playwright) — publication par clics, rythme lent.

Pour toutes les plateformes sauf Telegram (qui reste en API bot), ce
module remplace les appels d'API par une automatisation du navigateur :
ouverture de la page d'upload, saisie du fichier via l'input natif,
remplissage des formulaires champ par champ, puis clic sur le bouton
de publication.

Tout est fait LENTEMENT et de facon "humaine" :
  - pauses aleatoires de plusieurs secondes entre chaque action,
  - frappe du clavier caractere par caractere avec des micro-pauses,
  - clics avec un petit decale aleatoire du curseur,
  - pauses longues entre deux plateformes.

Objectif : limiter les captchas et les blocages anti-bot.

Playwright (plus stable que Selenium : pas de chromedriver a tenir
a jour, retries natifs des locators, gestion des inputs caches) :
  - installation : `pip install playwright` puis
    `playwright install chromium`.
  - La premiere fois, lancer `python multi_platform_publisher.py
    --login youtube tiktok ...` : le navigateur s'ouvre, vous vous
    connectez manuellement a chaque plateforme, puis Entree dans le
    terminal. Les cookies sont gardes dans .browser_profiles/<plateforme>.
  - Les selecteurs des interfaces web changent souvent : chaque etape
    est loggee pour faciliter le debug, et chaque selection essaie une
    liste de selecteurs de secours.

Note legale : l'automatisation des interfaces web peut enfreindre les
CGU de certaines plateformes ; les API officielles (TikTok, YouTube,
Facebook...) restent disponibles en passant --api.
"""

from __future__ import annotations

import logging
import os
import random
import time

log = logging.getLogger("publisher.browser")

# Timeout par defaut des attentes explicites (secondes)
WAIT_TIMEOUT = 90
# Attente apres le clic sur "publier" avant de considerer l'envoi parti
PUBLISH_SETTLE = (10, 25)

BROWSER_PLATFORMS = ("tiktok", "youtube", "dailymotion", "facebook",
                     "instagram", "x", "pinterest", "snapchat")


# ---------------------------------------------------------------------------
# Rythme humain
# ---------------------------------------------------------------------------

class HumanPace:
    """Gere toutes les attentes 'humaines' (lentes) de la session.

    Toutes les durees sont en secondes et tirent aleatoirement entre
    min et max pour ne pas produire de motif detectable.
    """

    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.min_delay = float(cfg.get("min_delay", 3.0))
        self.max_delay = float(cfg.get("max_delay", 9.0))
        self.typing_min = float(cfg.get("typing_min", 0.08))
        self.typing_max = float(cfg.get("typing_max", 0.35))

    def pause(self, min_s=None, max_s=None):
        """Pause aleatoire, appelee entre chaque action du flow."""
        lo = self.min_delay if min_s is None else min_s
        hi = self.max_delay if max_s is None else max_s
        d = random.uniform(lo, hi)
        log.debug("pause %.1fs", d)
        time.sleep(d)

    def slow_type(self, page, locator, text, clear=False):
        """Saisit `text` caractere par caractere, avec des micro-pauses
        et parfois un petit 'temps de reflexion' au milieu."""
        log.debug("frappe de %d caracteres", len(text))
        locator.focus()
        if clear:
            try:
                locator.fill("")
            except Exception:
                # champs contenteditable : tout selectionner puis suppr.
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
        self.pause(0.5, 1.5)
        for i, ch in enumerate(text):
            page.keyboard.type(ch)
            time.sleep(random.uniform(self.typing_min, self.typing_max))
            # une fois toutes les ~30 lettres, pause plus longue
            if i and i % 30 == 0 and random.random() < 0.5:
                time.sleep(random.uniform(0.6, 1.8))

    def slow_click(self, page, locator):
        """Clique doucement : petit decale aleatoire dans l'element,
        appui maintenu un court instant, puis pause."""
        delay_ms = random.randint(60, 180)
        log.debug("clic (appui %dms)", delay_ms)
        try:
            box = locator.bounding_box()
            if box:
                locator.click(
                    position={
                        "x": box["width"] / 2 + random.uniform(
                            -box["width"] / 4, box["width"] / 4),
                        "y": box["height"] / 2 + random.uniform(
                            -box["height"] / 4, box["height"] / 4),
                    },
                    delay=delay_ms,
                )
            else:
                locator.click(delay=delay_ms)
        except Exception:
            locator.click()
        self.pause(1.0, 3.0)

    def gentle_scroll(self, page, dy=300):
        """Petit defilement vertical pour paraitre humain."""
        try:
            page.mouse.wheel(0, dy)
        except Exception:
            pass
        self.pause(1.0, 2.5)


# ---------------------------------------------------------------------------
# Uploader navigateur de base
# ---------------------------------------------------------------------------

class BrowserUploaderBase:
    """Base commune des uploaders par clics (Playwright sync).

    Compatible avec l'interface attendue par Publisher : attribut
    `name` + methode `upload(video_path, title, description, tags)`.
    """

    name = "base"
    # URL d'accueil pour le mode --login (connexion manuelle)
    login_url = ""
    # Canal Playwright : "" (chromium bundle), "msedge" ou "chrome".
    # "msedge" lance l'Edge installe sur la machine.
    channel = ""
    # Si non vide : variable d'environnement pointant vers le
    # repertoire "User Data" d'un Edge existant (session perso/SSO).
    user_data_dir_env = ""

    def __init__(self, config):
        self.cfg = config
        self.browser_cfg = config.get("browser", {}) or {}
        self.pace = HumanPace(self.browser_cfg)
        self._pw = None
        self._context = None
        self._page = None

    # -- infrastructure ----------------------------------------------------

    def _start(self):
        """Demarre un Chromium avec profil persistant par plateforme
        (garde les cookies de connexion) et renvoie la page."""
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "playwright absent — pip install playwright puis "
                "playwright install chromium")
        profile = os.path.join(
            self.browser_cfg.get("profile_dir", ".browser_profiles"),
            self.name)
        os.makedirs(profile, exist_ok=True)
        # Session Edge perso (SSO) : reutiliser le vrai profil Edge
        # de l'utilisateur si l'environnement le demande.
        if self.user_data_dir_env and os.getenv(self.user_data_dir_env):
            profile = os.getenv(self.user_data_dir_env)
            log.warning(
                "%s: session Edge personnelle (%s) — ferme Edge "
                "avant le lancement, sinon le profil est verrouille "
                "et Playwright echouera.", self.name, profile)
        if self.browser_cfg.get("headless", False):
            log.warning("%s: mode headless actif — les captchas sont "
                        "plus frequents en headless.", self.name)
        self._pw = sync_playwright().start()
        launch_kwargs = {
            "user_data_dir": profile,
            "headless": bool(self.browser_cfg.get("headless", False)),
            "viewport": {"width": 1280, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            "ignore_default_args": ["--enable-automation"],
        }
        channel = self.channel or self.browser_cfg.get("channel") or ""
        if channel:
            launch_kwargs["channel"] = channel
        self._context = self._pw.chromium.launch_persistent_context(
            **launch_kwargs)
        self._context.set_default_timeout(WAIT_TIMEOUT * 1000)
        self._page = (self._context.pages[0]
                      if self._context.pages
                      else self._context.new_page())
        return self._page

    def _close(self):
        for closer in (self._context, self._pw):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        self._pw = None
        self._context = None
        self._page = None

    def _goto(self, page, url):
        log.info("%s: ouverture %s", self.name, url)
        page.goto(url, wait_until="domcontentloaded")
        self.pace.pause(4.0, 10.0)

    # -- helpers d'interface ------------------------------------------------

    def _find(self, page, selectors, timeout=WAIT_TIMEOUT):
        """Essaie chaque selecteur CSS dans l'ordre, renvoie le premier
        locator visible trouve."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for sel in selectors:
                loc = page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=2000)
                    log.debug("element trouve : %s", sel)
                    return loc
                except Exception:
                    continue
            time.sleep(1.0)
        raise LookupError("Aucun element pour %s (essais: %s)"
                          % (self.name, selectors))

    def _find_any_attached(self, page, selectors, timeout=WAIT_TIMEOUT):
        """Comme _find mais accepte un element attache meme cache
        (utile pour les inputs fichier)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for sel in selectors:
                loc = page.locator(sel).first
                try:
                    loc.wait_for(state="attached", timeout=2000)
                    return loc
                except Exception:
                    continue
            time.sleep(1.0)
        raise LookupError("Aucun element pour %s (essais: %s)"
                          % (self.name, selectors))

    def _click_button_with_text(self, page, texts,
                                timeout=WAIT_TIMEOUT):
        """Cherche un bouton dont le texte visible (ou l'aria-label)
        correspond a l'un des candidats (FR puis EN), et clique
        lentement."""
        wanted = [t.lower().strip() for t in texts]
        deadline = time.time() + timeout
        while time.time() < deadline:
            for loc in page.locator(
                    "button, div[role='button'], "
                    "span[role='button']").all():
                try:
                    if not loc.is_visible():
                        continue
                    label = " ".join(filter(None, (
                        loc.inner_text() or "",
                        loc.get_attribute("aria-label") or "",
                        loc.get_attribute("title") or "",
                    ))).lower().strip()
                    if not label:
                        continue
                    if any(w in label for w in wanted):
                        self.pace.slow_click(page, loc)
                        return loc
                except Exception:
                    continue
            time.sleep(1.5)
        raise LookupError("Bouton introuvable pour %s (textes: %s)"
                          % (self.name, texts))

    def _is_logged_out(self, page):
        """Detecte une redirection vers une page de connexion."""
        url = (page.url or "").lower()
        return any(m in url for m in (
            "login", "signin", "accounts.google.com", "session"))

    def _send_file(self, page, selectors, video_path):
        """Passe le fichier via l'input natif : Playwright gere les
        inputs caches directement, sans boite de dialogue OS."""
        loc = self._find_any_attached(page, selectors)
        loc.set_input_files(os.path.abspath(video_path))
        log.info("%s: fichier fourni (%s)", self.name,
                 os.path.basename(video_path))
        self.pace.pause(5.0, 12.0)

    # -- API commune ---------------------------------------------------------

    def upload(self, video_path, title, description, tags):
        log.info("%s : upload navigateur de %s", self.name,
                 os.path.basename(video_path))
        try:
            page = self._start()
        except ImportError as exc:
            log.error("%s: %s", self.name, exc)
            return ""
        except Exception as exc:
            log.error("%s: lancement du navigateur impossible : %s",
                      self.name, exc)
            return ""
        try:
            return self._do_upload(page, video_path, title,
                                   description, tags)
        except Exception as exc:
            log.error("%s: echec de l'upload navigateur : %s",
                      self.name, exc)
            return ""
        finally:
            self.pace.pause(2.0, 5.0)
            self._close()
            log.info("%s : navigateur ferme", self.name)

    def _do_upload(self, page, video_path, title, description, tags):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# TikTok — TikTok Studio (upload web)
# ---------------------------------------------------------------------------

class TikTokBrowserUploader(BrowserUploaderBase):
    name = "tiktok"
    login_url = "https://www.tiktok.com/login"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.tiktok.com/tiktokstudio/upload")
        if self._is_logged_out(page):
            log.error("TikTok: non connecte — lance "
                      "`--login tiktok` d'abord.")
            return ""
        self._send_file(page, ["input[type='file']"], video_path)

        # Legende : champ contenteditable (title + description + tags)
        caption = (title + "\n" + description)[:2150]
        if tags:
            caption += " " + " ".join("#" + t for t in tags[:8])
        field = self._find(page, ["div[contenteditable='true']",
                                  "[contenteditable='true']"])
        self.pace.slow_type(page, field, caption)
        self.pace.gentle_scroll(page, 250)

        # Attendre la fin du televersement : le bouton publish s'active
        log.info("TikTok: attente de la fin d'upload...")
        self.pace.pause(10.0, 20.0)
        deadline = time.time() + 600
        while time.time() < deadline:
            try:
                btn = self._find(page,
                                 ["button[data-e2e='post_video_button']",
                                  "button"], timeout=10)
                if btn.is_enabled():
                    break
            except Exception:
                pass
            time.sleep(5)
        else:
            raise LookupError("TikTok: upload toujours en cours apres "
                              "10 min.")
        self.pace.pause(3.0, 8.0)
        self.pace.slow_click(page, btn)

        # Confirmation
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("TikTok: demande de publication envoyee.")
        return "tiktok-web"


# ---------------------------------------------------------------------------
# YouTube — YouTube Studio (upload web)
# ---------------------------------------------------------------------------

class YouTubeBrowserUploader(BrowserUploaderBase):
    name = "youtube"
    login_url = "https://accounts.google.com"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.youtube.com/upload")
        if self._is_logged_out(page):
            log.error("YouTube: non connecte — lance "
                      "`--login youtube` d'abord.")
            return ""
        self._send_file(page, ["input[type='file']"], video_path)

        # Titre
        title_field = self._find(
            page,
            ["#name-text", "#name", "ytcp-textarea#name-text",
             "textarea[aria-label*='title']",
             "div[contenteditable='true'][aria-label*='title']"])
        self.pace.slow_type(page, title_field, title[:95], clear=True)
        self.pace.pause(2.0, 5.0)

        # Description
        desc_field = self._find(
            page,
            ["#description-text", "#description",
             "textarea[aria-label*='description']",
             "div[contenteditable='true'][aria-label*='escription']"])
        self.pace.slow_type(page, desc_field, description[:4900],
                            clear=True)
        self.pace.pause(2.0, 5.0)

        # Defiler jusqu'aux boutons (3 ecrans "Suivant" puis "Enregistrer")
        for _ in range(3):
            self.pace.gentle_scroll(page, 400)
            self._click_button_with_text(page, ["suivant", "next"])
            self.pace.pause(3.0, 7.0)
        self.pace.gentle_scroll(page, 300)
        self._click_button_with_text(page, ["enregistrer", "publier",
                                             "done", "save"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("YouTube: demande de publication envoyee.")
        return "youtube-web"


# ---------------------------------------------------------------------------
# Dailymotion — upload web
# ---------------------------------------------------------------------------

class DailymotionBrowserUploader(BrowserUploaderBase):
    name = "dailymotion"
    login_url = "https://www.dailymotion.com/login"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.dailymotion.com/upload")
        if self._is_logged_out(page):
            log.error("Dailymotion: non connecte — lance "
                      "`--login dailymotion` d'abord.")
            return ""
        self._send_file(page, ["input[type='file']"], video_path)

        title_field = self._find(
            page,
            ["input[name='title']", "input[placeholder*='titre']",
             "input[placeholder*='title']", "input[type='text']"])
        self.pace.slow_type(page, title_field, title[:140], clear=True)
        self.pace.pause(2.0, 5.0)

        desc_field = self._find(
            page,
            ["textarea[name='description']",
             "textarea[placeholder*='description']",
             "textarea"])
        self.pace.slow_type(page, desc_field, description[:2900],
                            clear=True)
        self.pace.pause(2.0, 5.0)

        self.pace.gentle_scroll(page, 350)
        self._click_button_with_text(page, ["publier", "publish"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("Dailymotion: demande de publication envoyee.")
        return "dailymotion-web"


# ---------------------------------------------------------------------------
# Facebook — composer une publication video (best effort)
# ---------------------------------------------------------------------------

class FacebookBrowserUploader(BrowserUploaderBase):
    name = "facebook"
    login_url = "https://www.facebook.com/login"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.facebook.com/")
        if self._is_logged_out(page):
            log.error("Facebook: non connecte — lance "
                      "`--login facebook` d'abord.")
            return ""

        # Ouvrir le composer
        trigger = self._find(
            page,
            ["div[aria-label*='Créer une publication']",
             "div[aria-label*='Create a post']",
             "div[role='button']:has-text('publication')"])
        self.pace.slow_click(page, trigger)
        self.pace.pause(3.0, 7.0)

        # Joindre le fichier dans la boite de dialogue ouverte
        self._send_file(page, ["input[type='file'][accept*='video']",
                               "input[type='file']"], video_path)

        # Zone de texte du composer
        field = self._find(
            page,
            ["div[role='textbox'][contenteditable='true']",
             "div[contenteditable='true']"])
        self.pace.slow_type(
            page, field, (title + "\n\n" + description)[:6000])
        self.pace.pause(3.0, 8.0)

        self._click_button_with_text(
            page, ["publier", "post", "publier maintenant"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("Facebook: demande de publication envoyee.")
        return "facebook-web"


# ---------------------------------------------------------------------------
# Instagram — publication web (best effort)
# ---------------------------------------------------------------------------

class InstagramBrowserUploader(BrowserUploaderBase):
    name = "instagram"
    login_url = "https://www.instagram.com/accounts/login/"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.instagram.com/")
        if self._is_logged_out(page):
            log.error("Instagram: non connecte — lance "
                      "`--login instagram` d'abord.")
            return ""

        # Bouton "Nouvelle publication" / "Create new post"
        trigger = self._find(
            page,
            ["svg[aria-label='Nouvelle publication']",
             "svg[aria-label='Create new post']",
             "div[aria-label='Nouvelle publication']",
             "div[aria-label='Create new post']"])
        self.pace.slow_click(page, trigger)
        self.pace.pause(3.0, 7.0)

        self._send_file(page, ["input[type='file']"], video_path)

        # Passer a l'ecran de details (bouton "Continuer"/"Next")
        self._click_button_with_text(page, ["continuer", "suivant",
                                            "next"])
        self.pace.pause(3.0, 7.0)

        # Legende
        field = self._find(
            page,
            ["div[role='textbox'][contenteditable='true']",
             "textarea[aria-label*='légende']",
             "textarea[aria-label*='caption']"])
        caption = (title + "\n\n" + description)[:2150]
        if tags:
            caption += " " + " ".join("#" + t for t in tags[:10])
        self.pace.slow_type(page, field, caption)
        self.pace.pause(3.0, 8.0)

        self._click_button_with_text(page, ["partager", "share"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("Instagram: demande de publication envoyee.")
        return "instagram-web"


# ---------------------------------------------------------------------------
# X (Twitter) — composer un post web
# ---------------------------------------------------------------------------

class XBrowserUploader(BrowserUploaderBase):
    name = "x"
    login_url = "https://x.com/login"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://x.com/compose/post")
        if self._is_logged_out(page):
            log.error("X: non connecte — lance `--login x` d'abord.")
            return ""

        self._send_file(page, ["input[data-testid='fileInput']",
                               "input[type='file']"], video_path)

        # Texte du post (limite X ~ 280 caract. — la description est
        # deja tronquee par DescriptionBuilder.for_x)
        field = self._find(
            page,
            ["div[data-testid='tweetTextarea_0']",
             "div[role='textbox'][contenteditable='true']"])
        text = (title + "\n" + description).strip()[:280]
        self.pace.slow_type(page, field, text)
        self.pace.pause(3.0, 8.0)

        self._click_button_with_text(page, ["publier", "poster",
                                            "post"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("X: demande de publication envoyee.")
        return "x-web"


# ---------------------------------------------------------------------------
# Pinterest — pin builder web
# ---------------------------------------------------------------------------

class PinterestBrowserUploader(BrowserUploaderBase):
    name = "pinterest"
    login_url = "https://www.pinterest.com/login/"

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://www.pinterest.com/pin-builder/")
        if self._is_logged_out(page):
            log.error("Pinterest: non connecte — lance "
                      "`--login pinterest` d'abord.")
            return ""
        self._send_file(page, ["input[type='file']"], video_path)

        title_field = self._find(
            page,
            ["textarea[placeholder*='titre']",
             "textarea[placeholder*='title']",
             "textarea[name='title']"])
        self.pace.slow_type(page, title_field, title[:95], clear=True)
        self.pace.pause(2.0, 5.0)

        desc_field = self._find(
            page,
            ["textarea[placeholder*='description']",
             "textarea[name='description']", "textarea"])
        self.pace.slow_type(page, desc_field, description[:480],
                            clear=True)
        self.pace.pause(2.0, 5.0)

        self._click_button_with_text(page, ["publier", "publish"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("Pinterest: demande de publication envoyee.")
        return "pinterest-web"


# ---------------------------------------------------------------------------
# Snapchat — web.snapchat.com (best effort, pas d'API publique)
# ---------------------------------------------------------------------------

class SnapchatBrowserUploader(BrowserUploaderBase):
    """Snapchat n'a pas d'API publique d'upload : on passe par le site
    web. Deux strategies de connexion, dans l'ordre :

      1. Session Edge personnelle : si EDGE_USER_DATA_DIR pointe vers
         le "User Data" de ton Edge, on le reutilise tel quel (SSO
         deja etabli). Edge doit etre completement ferme avant.
      2. Identifiants SNAPCHAT_EMAIL / SNAPCHAT_PASSWORD saisis
         lentement sur accounts.snapchat.com (peut declencher une
         verification 2FA/captcha : le code attend et loggue).

    Le flux d'upload (web.snapchat.com) est en best effort : bouton
    de creation, selection du fichier, legende, envoi vers la Story
    (Spotlight n'est pas toujours propose selon les comptes)."""
    name = "snapchat"
    login_url = "https://accounts.snapchat.com/accounts/login"
    channel = "msedge"
    user_data_dir_env = "EDGE_USER_DATA_DIR"

    def __init__(self, config):
        super().__init__(config)
        self.sc_cfg = config.get("snapchat", {}) or {}

    def _do_upload(self, page, video_path, title, description, tags):
        self._goto(page, "https://web.snapchat.com/")
        if self._is_logged_out(page):
            # Soit la session Edge perso n'est pas branchee/valide,
            # soit le profil dedie n'a jamais ete connecte.
            if not self._try_login(page):
                log.error("Snapchat: connexion impossible — lance "
                          "`--login snapchat` d'abord, ou renseigne "
                          "EDGE_USER_DATA_DIR / SNAPCHAT_EMAIL.")
                return ""
            self._goto(page, "https://web.snapchat.com/")

        # Bouton "Creer un Snap" / "+" de l'interface web
        trigger = self._find(
            page,
            ["button[aria-label*='Snap']", "div[aria-label*='Create']",
             "div[aria-label*='Créer']",
             "button:has-text('+')", "div[role='button']:has-text('+')"])
        self.pace.slow_click(page, trigger)
        self.pace.pause(3.0, 7.0)

        self._send_file(page, ["input[type='file']"], video_path)

        # Legende si un champ de texte est present
        caption = (title + "\n" + description)[:240]
        try:
            field = self._find(
                page,
                ["div[role='textbox'][contenteditable='true']",
                 "textarea"], timeout=15)
            self.pace.slow_type(page, field, caption)
        except LookupError:
            log.info("Snapchat: pas de champ legende visible, on "
                     "publie sans texte.")
            pass

        # Destination : la Story (Spotlight selon le compte)
        self._click_button_with_text(
            page, ["my story", "ma story", "story", "spotlight"])
        self.pace.pause(2.0, 6.0)
        self._click_button_with_text(
            page, ["envoyer", "publier", "send", "post"])
        self.pace.pause(*PUBLISH_SETTLE)
        log.info("Snapchat: demande de publication envoyee.")
        return "snapchat-web"

    def _try_login(self, page):
        """Remplit le formulaire de connexion Snapchat avec les
        identifiants configures, lentement. Renvoie True si on
        aboutit a une session valide (meme approximation)."""
        email = self.sc_cfg.get("email", "")
        password = self.sc_cfg.get("password", "")
        if not email or not password:
            return False
        log.info("Snapchat: connexion via identifiants...")
        self._goto(page, "https://accounts.snapchat.com/accounts/login")
        user_field = self._find(
            page,
            ["input[name='account']", "input[name='email']",
             "input[type='email']", "input[autocomplete='username']",
             "input[type='text']"])
        self.pace.slow_type(page, user_field, email, clear=True)
        self.pace.pause(1.5, 4.0)
        pw_field = self._find(
            page,
            ["input[type='password']", "input[name='password']"])
        self.pace.slow_type(page, pw_field, password, clear=True)
        self.pace.pause(1.5, 4.0)
        self._click_button_with_text(
            page, ["log in", "connexion", "se connecter", "next",
                    "suivant"])
        # 2FA / captcha possible : on laisse le temps a l'utilisateur
        # de le resoudre dans la fenetre ouverte si besoin.
        log.info("Snapchat: si un code 2FA ou un captcha apparait, "
                 "traite-le dans la fenetre (attente jusqu'a 2 min).")
        deadline = time.time() + 120
        while time.time() < deadline:
            self.pace.pause(5.0, 10.0)
            if not self._is_logged_out(page):
                return True
        return not self._is_logged_out(page)


# ---------------------------------------------------------------------------
# Integration avec Publisher
# ---------------------------------------------------------------------------

_UPLOADERS = {
    "tiktok": TikTokBrowserUploader,
    "youtube": YouTubeBrowserUploader,
    "dailymotion": DailymotionBrowserUploader,
    "facebook": FacebookBrowserUploader,
    "instagram": InstagramBrowserUploader,
    "x": XBrowserUploader,
    "pinterest": PinterestBrowserUploader,
    "snapchat": SnapchatBrowserUploader,
}


def apply(uploaders, config):
    """Remplace, dans la liste d'uploaders du Publisher, ceux dont la
    plateforme est configuree pour l'upload navigateur. Les autres
    (telegram, spotify, apple_podcasts) restent inchanges."""
    browser_cfg = config.get("browser", {}) or {}
    platforms = browser_cfg.get(
        "platforms", list(BROWSER_PLATFORMS))
    out = []
    for uploader in uploaders:
        if (browser_cfg.get("enabled", True)
                and uploader.name in platforms
                and uploader.name in _UPLOADERS):
            log.info("%s: publication via navigateur (mode clics lent).",
                     uploader.name)
            out.append(_UPLOADERS[uploader.name](config))
        else:
            out.append(uploader)
    return out


def open_login(config, platforms=None):
    """Ouvre un navigateur par plateforme pour une connexion manuelle
    (les cookies sont conserves dans le profil persistant)."""
    platforms = platforms or list(BROWSER_PLATFORMS)
    for name in platforms:
        if name not in _UPLOADERS:
            log.warning("Pas d'uploader navigateur pour '%s'.", name)
            continue
        uploader = _UPLOADERS[name](config)
        try:
            page = uploader._start()
            log.info("%s: connecte-toi dans la fenetre ouverte, puis "
                     "reviens ici.", name)
            page.goto(uploader.login_url
                      or "https://" + name + ".com")
            input("Appuie sur Entree quand la connexion %s est faite..."
                  % name)
        except ImportError as exc:
            log.error("%s: %s", name, exc)
            return
        finally:
            uploader.pace.pause(1.0, 2.0)
            uploader._close()
