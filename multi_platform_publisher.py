"""
multi_platform_publisher.py
===========================
Génère et publie des vidéos courtes (10 s) sur TikTok, YouTube,
Dailymotion, Facebook, Instagram, X, Snapchat, Pinterest, Telegram,
Spotify (podcast) et Apple Podcasts en ~20 langues
(FR, EN, ES, PT, DE, AR, EN-GB/AU/IN, ZH, JA, KO, HI, TH, VI, ID,
 RU, SW, AM, YO, ZU).

Thèmes : ambition, psychologie, développement personnel, philosophie,
culture, positivité, volonté, faits historiques, actualités.

Fonctionnalités :
  - 20 histoires vulgarisées (accessible à tous)
  - Sources auto : Wikipedia (toutes langues) + actualités (RSS)
  - Traduction automatique via deep-translator (Google Translate)
  - Voix off via gTTS (par langue)
  - Musique de fond (dossier music/)
  - Support RTL (arabe) avec arabic-reshaper + python-bidi
  - Notifications email après chaque publication
  - Planificateur quotidien (5 créneaux/jour)
  - Vérification éthique et conformité CGU avant publication
  - Vulgarisation intelligente via Google Gemini (ou dictionnaire fallback)
  - 11 plateformes : TikTok, YouTube, Dailymotion, Facebook, Instagram,
    X, Snapchat, Pinterest, Telegram, Spotify (podcast), Apple Podcasts

Dépendances :
    pip install moviepy pillow gTTS requests google-auth google-auth-oauthlib
                google-api-python-client deep-translator feedparser
                arabic-reshaper python-bidi requests-oauthlib playwright

Usage :
    python multi_platform_publisher.py             # tout générer + publier
    python multi_platform_publisher.py --dry-run    # générer seulement
    python multi_platform_publisher.py --auto      # sélection auto
    python multi_platform_publisher.py --news       # actualité du jour
    python multi_platform_publisher.py --schedule   # 5 publications/jour
    python multi_platform_publisher.py --languages fr en  # langues précises
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import browser_uploaders

# ---------------------------------------------------------------------------
# Langues
# ---------------------------------------------------------------------------

LANGUAGES = {
    "fr": {
        "name": "Francais",
        "tts_lang": "fr",
        "tts_tld": "fr",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 38,
        "wiki_domain": "fr.wikipedia.org",
    },
    "en": {
        "name": "English",
        "tts_lang": "en",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "en.wikipedia.org",
    },
    "es": {
        "name": "Espanol",
        "tts_lang": "es",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 40,
        "wiki_domain": "es.wikipedia.org",
    },
    "pt": {
        "name": "Portugues",
        "tts_lang": "pt",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 40,
        "wiki_domain": "pt.wikipedia.org",
    },
    "de": {
        "name": "Deutsch",
        "tts_lang": "de",
        "tts_tld": "de",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 56,
        "rtl": False,
        "text_width": 44,
        "wiki_domain": "de.wikipedia.org",
    },
    "ar": {
        "name": "العربية",
        "tts_lang": "ar",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "font_size": 56,
        "rtl": True,
        "text_width": 40,
        "wiki_domain": "ar.wikipedia.org",
    },
    # --- Anglais variantes ---
    "en-gb": {
        "name": "English (UK)",
        "tts_lang": "en",
        "tts_tld": "co.uk",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "en.wikipedia.org",
    },
    "en-au": {
        "name": "English (AU)",
        "tts_lang": "en",
        "tts_tld": "com.au",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "en.wikipedia.org",
    },
    "en-in": {
        "name": "English (India)",
        "tts_lang": "en",
        "tts_tld": "co.in",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "en.wikipedia.org",
    },
    # --- Langues asiatiques ---
    "zh": {
        "name": "中文",
        "tts_lang": "zh-CN",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "font_size": 52,
        "rtl": False,
        "text_width": 34,
        "wiki_domain": "zh.wikipedia.org",
    },
    "ja": {
        "name": "日本語",
        "tts_lang": "ja",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "font_size": 52,
        "rtl": False,
        "text_width": 36,
        "wiki_domain": "ja.wikipedia.org",
    },
    "ko": {
        "name": "한국어",
        "tts_lang": "ko",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "font_size": 52,
        "rtl": False,
        "text_width": 36,
        "wiki_domain": "ko.wikipedia.org",
    },
    "hi": {
        "name": "हिन्दी",
        "tts_lang": "hi",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "font_size": 52,
        "rtl": False,
        "text_width": 38,
        "wiki_domain": "hi.wikipedia.org",
    },
    "th": {
        "name": "ไทย",
        "tts_lang": "th",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "font_size": 48,
        "rtl": False,
        "text_width": 36,
        "wiki_domain": "th.wikipedia.org",
    },
    "vi": {
        "name": "Tiếng Việt",
        "tts_lang": "vi",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 56,
        "rtl": False,
        "text_width": 40,
        "wiki_domain": "vi.wikipedia.org",
    },
    "id": {
        "name": "Bahasa Indonesia",
        "tts_lang": "id",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "id.wikipedia.org",
    },
    # --- Russe ---
    "ru": {
        "name": "Русский",
        "tts_lang": "ru",
        "tts_tld": "ru",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 56,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "ru.wikipedia.org",
    },
    # --- Langues africaines ---
    "sw": {
        "name": "Kiswahili",
        "tts_lang": "sw",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "sw.wikipedia.org",
    },
    "am": {
        "name": "አማርኛ",
        "tts_lang": "am",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf",
        "font_size": 52,
        "rtl": False,
        "text_width": 38,
        "wiki_domain": "am.wikipedia.org",
    },
    "yo": {
        "name": "Yorùbá",
        "tts_lang": "yo",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "yo.wikipedia.org",
    },
    "zu": {
        "name": "isiZulu",
        "tts_lang": "zu",
        "tts_tld": "com",
        "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_size": 64,
        "rtl": False,
        "text_width": 42,
        "wiki_domain": "zu.wikipedia.org",
    },
}

DESCRIPTION_TEMPLATES = {
    "fr": {"part": "Partie", "episode": "Episode", "theme": "Theme",
           "sub_short": "Abonne-toi pour la suite",
           "sub_long": "On continue demain — abonne-toi pour ne rien rater !",
           "saga": "Saga", "of": "sur",
           "intro": ["Et si je te racontais...", "Tu sais ce qui est fascinant ?", "Laisse-moi te raconter une histoire.", "Accroche-toi, c'est fort.", "Figure-toi que..."],
           "outro": ["Qu'est-ce que tu en penses ?", "Dis-moi en commentaire.", "Et toi, tu aurais fait quoi ?", "Partage si ca t'a marque.", "On en parle en commentaire ?"],
           "transition": ["Voici l'idee cle :", "Alors, retiens ca :", "Le point fondamental :", "Ce qu'il faut comprendre :", "La chose essentielle :"],
           "punch": ["C'est puissant, non ?", "Ca fait reflechir.", "Vraiment, prends le temps d'y penser.", "Et ca change tout.", "Simple, mais profond."]},
    "en": {"part": "Part", "episode": "Episode", "theme": "Theme",
           "sub_short": "Subscribe for more",
           "sub_long": "See you tomorrow — subscribe so you don't miss what's next!",
           "saga": "Series", "of": "of",
           "intro": ["What if I told you...", "You know what's fascinating?", "Let me tell you a story.", "Hold on, this is powerful.", "Picture this..."],
           "outro": ["What do you think?", "Tell me in the comments.", "What would you have done?", "Share if this hit home.", "Let's talk in the comments."],
           "transition": ["Here's the key idea:", "So remember this:", "The fundamental point:", "What you need to understand:", "The essential thing:"],
           "punch": ["Powerful, right?", "Makes you think.", "Really, sit with that for a second.", "And it changes everything.", "Simple, but profound."]},
    "es": {"part": "Parte", "episode": "Episodio", "theme": "Tema",
           "sub_short": "Suscribete para mas",
           "sub_long": "Continuamos manana — suscribete para no perderte nada!",
           "saga": "Serie", "of": "de",
           "intro": ["Que tal si te cuento...", "Sabes lo fascinante que es?", "Dejame contarte una historia.", "Agarrate, esto es fuerte.", "Imaginate esto..."],
           "outro": ["Que piensas?", "Dimelo en los comentarios.", "Y tu, que harías?", "Comparte si te marco.", "Hablamos en los comentarios?"],
           "transition": ["Aqui esta la idea clave:", "Entonces, recuerda esto:", "El punto fundamental:", "Lo que hay que entender:", "Lo esencial:"],
           "punch": ["Es poderoso, no?", "Hace reflexionar.", "De verdad, piensalo un momento.", "Y lo cambia todo.", "Simple, pero profondo."]},
    "pt": {"part": "Parte", "episode": "Episodio", "theme": "Tema",
           "sub_short": "Inscreva-se para mais",
           "sub_long": "Continuamos amanha — inscreva-se para nao perder nada!",
           "saga": "Serie", "of": "de",
           "intro": ["Que tal se eu te contasse...", "Sabe o que e fascinante?", "Deixa eu te contar uma historia.", "Segura, isso e forte.", "Imagina isso..."],
           "outro": ["O que voce acha?", "Me conta nos comentarios.", "E voce, o que faria?", "Compartilha se te marcou.", "Bora conversar nos comentarios?"],
           "transition": ["Aqui esta a ideia chave:", "Entao, lembra disso:", "O ponto fundamental:", "O que voce precisa entender:", "O essencial:"],
           "punch": ["E poderoso, ne?", "Faz refletir.", "Serie, pensa um pouco nisso.", "E muda tudo.", "Simples, mas profundo."]},
    "de": {"part": "Teil", "episode": "Episode", "theme": "Thema",
           "sub_short": "Abonniere fur mehr",
           "sub_long": "Morgen geht es weiter — abonniere, um nichts zu verpassen!",
           "saga": "Serie", "of": "von",
           "intro": ["Was ware, wenn ich dir erzahle...", "Weisst du, was faszinierend ist?", "Lass mir dir eine Geschichte erzaehlen.", "Halte fest, das ist stark.", "Stell dir vor..."],
           "outro": ["Was denkst du?", "Sag mir in den Kommentaren.", "Was wuerdest du tun?", "Teile, wenn es dich beruehrt hat.", "Lass uns in den Kommentaren reden."],
           "transition": ["Hier ist die Kernidee:", "Also, merk dir das:", "Der wesentliche Punkt:", "Was du verstehen musst:", "Das Wesentliche:"],
           "punch": ["Stark, oder?", "Macht nachdenklich.", "Wirklich, nimm dir einen Moment.", "Und das aendert alles.", "Einfach, aber tief."]},
    "ar": {"part": "جزء", "episode": "حلقة", "theme": "موضوع",
           "sub_short": "اشترك للمزيد", "sub_long": "نكمل غداً — اشترك حتى لا تفوتك الأجزاء القادمة!",
           "saga": "سلسلة", "of": "من",
           "intro": ["ماذا لو أخبرتك...", "هل تعرف ما هو المدهش؟", "دعني أحكي لك قصة.", "تمسك جيداً، هذا قوي.", "تخيل هذا..."],
           "outro": ["ما رأيك؟", "أخبرني في التعليقات.", "وأنت، ماذا كنت ستفعل؟", "شارك إذا لمسك.", "لنتحدث في التعليقات."],
           "transition": ["إليك الفكرة الرئيسية:", "إذن، تذكر هذا:", "النقطة الأساسية:", "ما يجب أن تفهمه:", "الشيء المهم:"],
           "punch": ["إنه قوي، أليس كذلك؟", "يجعلك تفكر.", "حقاً، خذ وقتك للتفكير.", "وهذا يغير كل شيء.", "بسيط، لكن عميق."]},
    # --- Anglais variantes (meme templates, accents differents) ---
    "en-gb": {"part": "Part", "episode": "Episode", "theme": "Theme",
              "sub_short": "Subscribe for more",
              "sub_long": "See you tomorrow — subscribe so you don't miss what's next!",
              "saga": "Series", "of": "of",
              "intro": ["What if I told you...", "You know what's brilliant?", "Let me tell you a story.", "Mind you, this is powerful.", "Picture this..."],
              "outro": ["What do you reckon?", "Tell me in the comments.", "What would you have done?", "Share if this resonated.", "Let's chat in the comments."]},
    "en-au": {"part": "Part", "episode": "Episode", "theme": "Theme",
              "sub_short": "Subscribe for more",
              "sub_long": "Catch you tomorrow — subscribe so you don't miss what's next!",
              "saga": "Series", "of": "of",
              "intro": ["What if I told you...", "You know what's ripper?", "Let me tell you a yarn.", "Hold on, this is gold.", "Picture this..."],
              "outro": ["What do you reckon?", "Chuck us a comment.", "What would you have done?", "Share if this hit home.", "Let's yarn in the comments."]},
    "en-in": {"part": "Part", "episode": "Episode", "theme": "Theme",
              "sub_short": "Subscribe for more",
              "sub_long": "See you tomorrow — subscribe so you don't miss what's next!",
              "saga": "Series", "of": "of",
              "intro": ["What if I told you...", "You know what's fascinating?", "Let me tell you a story.", "Hold on, this is powerful.", "Picture this..."],
              "outro": ["What do you think?", "Tell me in the comments.", "What would you have done?", "Share if this hit home.", "Let's talk in the comments."]},
    # --- Chinois ---
    "zh": {"part": "部分", "episode": "集", "theme": "主题",
           "sub_short": "订阅看更多",
           "sub_long": "明天继续 — 订阅以免错过下一集！",
           "saga": "系列", "of": "共",
           "intro": ["如果我告诉你...", "你知道什么最令人惊叹吗？", "让我给你讲个故事。", "抓紧了，这很震撼。", "想象一下..."],
           "outro": ["你怎么看？", "在评论区告诉我。", "换作是你，会怎么做？", "如果触动你就分享吧。", "评论区聊聊？"]},
    # --- Japonais ---
    "ja": {"part": "パート", "episode": "エピソード", "theme": "テーマ",
           "sub_short": "もっと見るには登録",
           "sub_long": "また明日 — 登録して次を見逃さない！",
           "saga": "シリーズ", "of": "全",
           "intro": ["もし私が言ったら...", "何が驚きか知ってる？", "物語を聞かせてあげる。", "しっかり聞いて、これは強い。", "想像してみて..."],
           "outro": ["どう思う？", "コメントで教えて。", "あなたならどうする？", "心に響いたらシェアして。", "コメントで話そう。"]},
    # --- Coreen ---
    "ko": {"part": "부분", "episode": "에피소드", "theme": "주제",
           "sub_short": "더 보려면 구독",
           "sub_long": "내일 계속 — 구독하고 다음을 놓치지 마세요!",
           "saga": "시리즈", "of": "총",
           "intro": ["내가 말하면...", "뭐가 놀라운지 알아?", "이야기를 들려줄게.", "잡아, 이건 강력해.", "상상해봐..."],
           "outro": ["어떻게 생각해?", "댓글로 알려줘.", "너라면 어떻게 했어?", "마음에 닿으면 공유해.", "댓글에서 얘기하자."]},
    # --- Hindi ---
    "hi": {"part": "भाग", "episode": "एपिसोड", "theme": "विषय",
           "sub_short": "और देखने के लिए सब्सक्राइब करें",
           "sub_long": "कल मिलते हैं — सब्सक्राइब करें ताकि आगे कुछ भी न चूकें!",
           "saga": "श्रृंखला", "of": "में से",
           "intro": ["क्या हो अगर मैं बताऊं...", "पता है क्या दिलचस्प है?", "एक कहानी सुनाता हूं।", "ध्यान दो, यह ताक़तवर है।", "ज़रा सोचो..."],
           "outro": ["आपको क्या लगता है?", "कमेंट में बताइए।", "आप क्या करते?", "अगर छुआ तो शेयर करें।", "कमेंट में बात करते हैं?"]},
    # --- Thai ---
    "th": {"part": "ตอน", "episode": "เอพิโซด", "theme": "หัวข้อ",
           "sub_short": "กดติดตามดูต่อ",
           "sub_long": "พรุ่งนี้เจอกันใหม่ — กดติดตามเพื่อไม่พลาดตอนต่อไป!",
           "saga": "ซีรีส์", "of": "จาก",
           "intro": ["ถ้าฉันบอกว่า...", "รู้ไหมว่าอะไรน่าทึ่ง?", "มาเล่าเรื่องให้ฟังไหม?", "จับไว้ นี่มันทรงพลัง.", "ลองนึกดู..."],
           "outro": ["คุณคิดอย่างไร?", "บอกได้ในคอมเมนต์.", "แล้วคุณจะทำยังไง?", "แชร์ถ้ามันสะเทือนใจ.", "คุยกันในคอมเมนต์ไหม?"]},
    # --- Vietnamien ---
    "vi": {"part": "Phần", "episode": "Tập", "theme": "Chủ đề",
           "sub_short": "Đăng ký xem thêm",
           "sub_long": "Hẹn gặp ngày mai — đăng ký để không bỏ lỡ phần tiếp theo!",
           "saga": "Loạt", "of": "trên",
           "intro": ["Nếu tôi nói với bạn...", "Bạn biết điều gì thú vị không?", "Để tôi kể bạn nghe một câu chuyện.", "Giữ chặt, chuyện này mạnh mẽ.", "Hãy tưởng tượng..."],
           "outro": ["Bạn nghĩ sao?", "Cho tôi biết trong bình luận.", "Bạn sẽ làm gì?", "Chia sẻ nếu bạn thấy chạm đến lòng.", "Nói chuyện trong bình luận nhé?"]},
    # --- Indonésien ---
    "id": {"part": "Bagian", "episode": "Episode", "theme": "Tema",
           "sub_short": "Subscribe untuk lebih banyak",
           "sub_long": "Sampai jumpa besok — subscribe supaya tidak ketinggalan!",
           "saga": "Serial", "of": "dari",
           "intro": ["Bagaimana kalau aku cerita...", "Tahu apa yang menarik?", "Biar aku cerita sebuah kisah.", "Pegang ya, ini kuat.", "Bayangkan ini..."],
           "outro": ["Apa pendapatmu?", "Beritahu di komentar.", "Kalau kamu, kamu akan apa?", "Bagikan jika menyentuhmu.", "Ngobrol di komentar ya?"]},
    # --- Russe ---
    "ru": {"part": "Часть", "episode": "Эпизод", "theme": "Тема",
           "sub_short": "Подпишись, чтобы видеть больше",
           "sub_long": "Увидимся завтра — подпишись, чтобы не пропустить продолжение!",
           "saga": "Сериал", "of": "из",
           "intro": ["А если я скажу тебе...", "Знаешь, что удивительно?", "Расскажу тебе историю.", "Держись, это сильно.", "Представь себе..."],
           "outro": ["Что думаешь?", "Напиши в комментариях.", "А что бы сделал ты?", "Поделись, если тронуло.", "Обсудим в комментариях?"]},
    # --- Swahili ---
    "sw": {"part": "Sehemu", "episode": "Kipindi", "theme": "Mada",
           "sub_short": "Jisajili kwa zaidi",
           "sub_long": "Tutaonana kesho — jisajili usikose sehemu inayofuata!",
           "saga": "Msifu", "of": "ya",
           "intro": ["Hebu nikwambie...", "Unajua kitu cha kushangaza?", "Nikusimulie hadithi.", "Shikamana, hii ni nguvu.", "Fikiria hivi..."],
           "outro": ["Unafikiria nini?", "Niambie kwenye maoni.", "Wewe ungenyanya nini?", "Shiriki ikiwa imekugusa.", "Tuzungumze kwenye maoni?"],
           },
    # --- Amharique ---
    "am": {"part": "ክፍል", "episode": "ክፍል", "theme": "ርዕስ",
           "sub_short": "ተጨማሪ ለማግኘት ይመዝገቡ",
           "sub_long": "ደህና ይሁኑ ለነገ — ቀጣዩን ለመከታተል ይመዝገቡ!",
           "saga": "ተከታታይ", "of": "ከ",
           "intro": ["ብነግርህ።", "የሚያስደንቅ ነገር ታውቃለህ?", "ታሪክ ልንገርህ።", "በጥብቅ ያዝ፣ ይህ ጠንካራ ነው።", "አስብበት..."],
           "outro": ["ምን ያስባለህ?", "በአስተያየቶች ንገረኝ።", "አንተ ብትሆን ምን ታደርግ?", "ካነካካህ አጋራ።", "በአስተያየቶች እንወያይ?"]},
    # --- Yoruba ---
    "yo": {"part": "Eka", "episode": "Ere", "theme": "Koko",
           "sub_short": "Alabapin fun e sii",
           "sub_long": "A pade lola — alabapin ki o ma fi ohun ti n bo se!",
           "saga": "Series", "of": "ninu",
           "intro": ["Kilode ti mo ba so fun o...", "Se o mo ohun ti n dun?", "Jeki n so itan fun o.", "Mu drip, eleyi lagbara.", "Ronu nipa e..."],
           "outro": ["Kini o ro?", "So fun mi ninu comments.", "Iwo o se bee?", "Pin ti o ba yin inu.", "A ba soro ninu comments?"]},
    # --- Zulu ---
    "zu": {"part": "Ingcenye", "episode": "Isiqephu", "theme": "Isihloko",
           "sub_short": "Bhalisa ukuze ubone okuningi",
           "sub_long": "Siyozibonana kusasa — bhalisa ukuze ungashi okulandelayo!",
           "saga": "Uchungechunge", "of": "kwale",
           "intro": ["Ngingakutshela...", "Uyazi okumangalisayo?", "Ake ngikutshèle indaba.", "Bamba kabi, lokhu kunamandla.", "Cabanga ngakho..."],
           "outro": ["Ucabanga ukuthini?", "Ngitshele ezimeni zokuphawula.", "Wena ubezini?", "Yabelana uma ikuthinta.", "Sikhulume ezimeni zokuphawula?"]},
}

HASHTAGS_PER_LANG = {
    "fr": ["#ambition", "#psychologie", "#developpementpersonnel", "#philosophie",
           "#culture", "#positivite", "#volonte", "#histoire", "#motivation", "#shorts"],
    "en": ["#ambition", "#psychology", "#selfdevelopment", "#philosophy",
           "#culture", "#positivity", "#willpower", "#history", "#motivation", "#shorts"],
    "es": ["#ambicion", "#psicologia", "#desarrollopersonal", "#filosofia",
           "#cultura", "#positividad", "#voluntad", "#historia", "#motivacion", "#shorts"],
    "pt": ["#ambicao", "#psicologia", "#desenvolvimentopessoal", "#filosofia",
           "#cultura", "#positividade", "#vontade", "#historia", "#motivacao", "#shorts"],
    "de": ["#ambition", "#psychologie", "#persoenlichkeitsentwicklung", "#philosophie",
           "#kultur", "#positivitaet", "#willenskraft", "#geschichte", "#motivation", "#shorts"],
    "ar": ["#طموح", "#علم_النفس", "#تطوير_الذات", "#فلسفة",
           "#ثقافة", "#إيجابية", "#إرادة", "#تاريخ", "#تحفيز", "#شورتس"],
    "en-gb": ["#ambition", "#psychology", "#selfdevelopment", "#philosophy",
              "#culture", "#positivity", "#willpower", "#history", "#motivation", "#shorts"],
    "en-au": ["#ambition", "#psychology", "#selfdevelopment", "#philosophy",
              "#culture", "#positivity", "#willpower", "#history", "#motivation", "#shorts"],
    "en-in": ["#ambition", "#psychology", "#selfdevelopment", "#philosophy",
              "#culture", "#positivity", "#willpower", "#history", "#motivation", "#shorts"],
    "zh": ["#雄心", "#心理学", "#自我提升", "#哲学",
           "#文化", "#积极", "#意志", "#历史", "#激励", "#短视频"],
    "ja": ["#野心", "#心理学", "#自己啓発", "#哲学",
           "#文化", "#前向き", "#意志", "#歴史", "#モチベーション", "#ショート"],
    "ko": ["#야망", "#심리학", "#자기계발", "#철학",
           "#문화", "#긍정", "#의지", "#역사", "#동기부여", "#쇼츠"],
    "hi": ["#महत्वाकांक्षा", "#मनोविज्ञान", "#आत्मविकास", "#दर्शन",
           "#संस्कृति", "#सकारात्मकता", "#इच्छाशक्ति", "#इतिहास", "#प्रेरणा", "#शॉर्ट्स"],
    "th": ["#ความทะเยอทะยาน", "#จิตวิทยา", "#พัฒนาตนเอง", "#ปรัชญา",
           "#วัฒนธรรม", "#ความคิดบวก", "#ความตั้งใจ", "#ประวัติศาสตร์", "#แรงบันดาลใจ", "#ชอร์ตส์"],
    "vi": ["#thamvong", "#tamlyhoc", "#phattrienbanthan", "#trietly",
           "#vanhoa", "#tichtich", "#ychi", "#lichsu", "#dongluc", "#shorts"],
    "id": ["#ambisi", "#psikologi", "#pengembangandiri", "#filsafat",
           "#budaya", "#positivitas", "#kemauan", "#sejarah", "#motivasi", "#shorts"],
    "ru": ["#амбиции", "#психология", "#саморазвитие", "#философия",
           "#культура", "#позитивность", "#воля", "#история", "#мотивация", "#шортс"],
    "sw": ["#wia", "#saikolojia", "#maendeleobinafsi", "#falsafa",
           "#utamaduni", "#chanya", "#mapenzi", "#historia", "#motivasi", "#shorts"],
    "am": ["#ስልጣን", "#ሳይኮሎጂ", "#የራስ_ማሻሻያ", "#ፍልስፍኤ",
           "#ባህል", "#አዎንታዊነት", "#ፍቃደኝነት", "#ታሪክ", "#ማነቃቂያ", "#shorts"],
    "yo": ["#ifekufe", "#imookan", "#idagbasokearaeni", "#filosofi",
           "#asa", "#rere", "#ife", "#itan", "#igbega", "#shorts"],
    "zu": ["#inhloso", "#inzwangqondo", "#ukuzithuthukisa", "#filosofi",
           "#amasiko", "#okuhle", "#inhliziyo", "#umlando", "#ukukhuthaza", "#shorts"],
}

NEWS_FEEDS = {
    "fr": ["https://www.lemonde.fr/rss/une.xml",
           "https://www.francetvinfo.fr/titres.rss"],
    "en": ["https://feeds.bbci.co.uk/news/rss.xml",
           "https://rss.dw.com/rdf/rss-en-all"],
    "en-gb": ["https://feeds.bbci.co.uk/news/rss.xml",
              "https://rss.dw.com/rdf/rss-en-all"],
    "en-au": ["https://www.abc.net.au/news/feed/",
              "https://rss.dw.com/rdf/rss-en-all"],
    "en-in": ["https://www.thehindu.com/news/national/feeder/default.rss",
              "https://rss.dw.com/rdf/rss-en-all"],
    "es": ["https://rss.dw.com/rdf/rss-es-all"],
    "pt": ["https://rss.dw.com/rdf/rss-pt-br-all"],
    "de": ["https://rss.dw.com/rdf/rss-de-all",
           "https://www.spiegel.de/schlagzeilen/tops/index.rss"],
    "ar": ["https://rss.dw.com/rdf/rss-ar-all"],
    "ru": ["https://rss.dw.com/rdf/rss-ru-all",
           "https://meduza.io/rss/all"],
    "zh": ["https://rss.dw.com/rdf/rss-zh-all",
           "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"],
    "ja": ["https://rss.dw.com/rdf/rss-ja-all",
           "https://news.yahoo.co.jp/rss/categories/top.xml"],
    "ko": ["https://rss.dw.com/rdf/rss-ko-all"],
    "hi": ["https://rss.dw.com/rdf/rss-hi-all"],
    "th": ["https://rss.dw.com/rdf/rss-th-all"],
    "vi": ["https://rss.dw.com/rdf/rss-vi-all"],
    "id": ["https://rss.dw.com/rdf/rss-id-all"],
    "sw": ["https://rss.dw.com/rdf/rss-sw-all",
           "https://www.bbc.com/swahili/rss"],
    "am": ["https://rss.dw.com/rdf/rss-am-all"],
    "yo": ["https://www.bbc.com/yoruba/rss"],
    "zu": ["https://www.bbc.com/isizulu/rss"],
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG = {
    "width": 1080,
    "height": 1920,
    "fps": 24,
    "duration_seconds": 10,
    "work_dir": Path(tempfile.gettempdir()) / "multi_platform_publisher",
    "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "font_size": 64,
    # Langues cibles (toutes par defaut)
    "languages": ["fr", "en", "es", "pt", "de", "ar",
                  "en-gb", "en-au", "en-in",
                  "zh", "ja", "ko", "hi", "th", "vi", "id",
                  "ru", "sw", "am", "yo", "zu"],
    "source_language": "fr",
    # Nom du createur / de la chaine (toutes plateformes)
    "channel_name": os.getenv("CHANNEL_NAME", "Cultivia"),
    # TTS
    "tts": {"enabled": True, "lang": "fr", "slow": False, "tld": "fr"},
    # Musique
    "music": {"enabled": True, "dir": "music", "volume": 0.15,
              "fadein": 0.5, "fadeout": 0.5},
    # Traduction
    "translator": {"enabled": True},
    # Actualites
    "news": {"enabled": True, "max_episodes": 3},
    # Palettes
    "palettes": [
        ((20, 24, 38), (45, 55, 90)),
        ((30, 20, 40), (75, 40, 90)),
        ((10, 35, 30), (25, 80, 70)),
        ((40, 25, 20), (110, 60, 40)),
        ((15, 20, 35), (60, 90, 120)),
    ],
    # APIs
    "tiktok": {
        "client_key": os.getenv("TIKTOK_CLIENT_KEY", "awuejdlepfketjbr"),
        "client_secret": os.getenv("TIKTOK_CLIENT_SECRET", "UY2Cf2WjgKqEvMa2Vl5Q2BFZL8f8XXuL"),
        "access_token": os.getenv("TIKTOK_ACCESS_TOKEN", ""),
    },
    "youtube": {
        "client_secret_path": os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"),
        "credentials_path": os.getenv("YOUTUBE_TOKEN", "youtube_token.json"),
    },
    "dailymotion": {
        "api_key": os.getenv("DAILYMOTION_API_KEY", "b869eb5b9d5ca5a69d98"),
        "api_secret": os.getenv("DAILYMOTION_API_SECRET", "e68b3c0c45d7796cfc9ca19f4e77bb522b7e66a6"),
        "username": os.getenv("DAILYMOTION_USERNAME", "hugo.satabin.01@gmail.com"),
        "password": os.getenv("DAILYMOTION_PASSWORD", "Ingrandes86*"),
    },
    "facebook": {
        "page_id": os.getenv("FACEBOOK_PAGE_ID", ""),
        "access_token": os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
        "api_version": os.getenv("FACEBOOK_API_VERSION", "v19.0"),
    },
    "instagram": {
        # Instagram utilise la Graph API de Meta (compte professionnel)
        "account_id": os.getenv("INSTAGRAM_ACCOUNT_ID", ""),
        "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        "api_version": os.getenv("INSTAGRAM_API_VERSION", "v19.0"),
    },
    "x": {
        # X (Twitter) API v2 : l'upload media (INIT/APPEND/FINALIZE) et
        # la creation de tweet exigent un jeton utilisateur OAuth 2.0
        # (Authorization Code + PKCE, scopes "tweet.write media.write")
        # depuis la depreciation de l'ancien endpoint v1.1 en mai 2025.
        "user_access_token": os.getenv("X_USER_ACCESS_TOKEN", ""),
        "bearer_token": os.getenv("X_BEARER_TOKEN", ""),
    },
    "snapchat": {
        "client_id": os.getenv("SNAPCHAT_CLIENT_ID", ""),
        "client_secret": os.getenv("SNAPCHAT_CLIENT_SECRET", ""),
        "refresh_token": os.getenv("SNAPCHAT_REFRESH_TOKEN", ""),
        # Connexion navigateur (web.snapchat.com) :
        "email": os.getenv("SNAPCHAT_EMAIL", ""),
        "password": os.getenv("SNAPCHAT_PASSWORD", ""),

    },
    "pinterest": {
        "access_token": os.getenv("PINTEREST_ACCESS_TOKEN", ""),
        "board_id": os.getenv("PINTEREST_BOARD_ID", ""),
    },
    "telegram": {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "channels": {
            "fr": os.getenv("TELEGRAM_CHANNEL_FR", "t.me/+5ofC9VKcstBjMDc0"),
            "en": os.getenv("TELEGRAM_CHANNEL_EN", "https://t.me/CULTIVIA_CHANNEL_EN"),
            "es": os.getenv("TELEGRAM_CHANNEL_ES", "https://t.me/CULTIVIA_CHANNEL_ES"),
            "pt": os.getenv("TELEGRAM_CHANNEL_PT", "https://t.me/CULTIVIA_CHANNEL_PT"),
            "de": os.getenv("TELEGRAM_CHANNEL_DE", "https://t.me/CULTIVIA_CHANNEL_DE"),
            "ar": os.getenv("TELEGRAM_CHANNEL_AR", "t.me/+5ofC9VKcstBjMDc0"),
            "en-gb": os.getenv("TELEGRAM_CHANNEL_EN_GB", os.getenv("TELEGRAM_CHANNEL_EN", "https://t.me/CULTIVIA_CHANNEL_EN")),
            "en-au": os.getenv("TELEGRAM_CHANNEL_EN_AU", os.getenv("TELEGRAM_CHANNEL_EN", "https://t.me/CULTIVIA_CHANNEL_EN")),
            "en-in": os.getenv("TELEGRAM_CHANNEL_EN_IN", os.getenv("TELEGRAM_CHANNEL_EN", "https://t.me/CULTIVIA_CHANNEL_EN")),
            "zh": os.getenv("TELEGRAM_CHANNEL_ZH", "t.me/+5ofC9VKcstBjMDc0"),
            "ja": os.getenv("TELEGRAM_CHANNEL_JA", "t.me/+5ofC9VKcstBjMDc0"),
            "ko": os.getenv("TELEGRAM_CHANNEL_KO", "t.me/+5ofC9VKcstBjMDc0"),
            "hi": os.getenv("TELEGRAM_CHANNEL_HI", "t.me/+5ofC9VKcstBjMDc0"),
            "th": os.getenv("TELEGRAM_CHANNEL_TH", "t.me/+5ofC9VKcstBjMDc0"),
            "vi": os.getenv("TELEGRAM_CHANNEL_VI", "t.me/+5ofC9VKcstBjMDc0"),
            "id": os.getenv("TELEGRAM_CHANNEL_ID", "t.me/+5ofC9VKcstBjMDc0"),
            "ru": os.getenv("TELEGRAM_CHANNEL_RU", "t.me/+5ofC9VKcstBjMDc0"),
            "sw": os.getenv("TELEGRAM_CHANNEL_SW", "t.me/+5ofC9VKcstBjMDc0"),
            "am": os.getenv("TELEGRAM_CHANNEL_AM", "t.me/+5ofC9VKcstBjMDc0"),
            "yo": os.getenv("TELEGRAM_CHANNEL_YO", "t.me/+5ofC9VKcstBjMDc0"),
            "zu": os.getenv("TELEGRAM_CHANNEL_ZU", "t.me/+5ofC9VKcstBjMDc0"),
        },
    },
    "spotify": {
        "email": os.getenv("SPOTIFY_PODCAST_EMAIL", r"hugo.satabin@icloud.com"),
        "password": os.getenv("SPOTIFY_PODCAST_PASSWORD", r"Compteapple01"),
        "show_id": os.getenv("SPOTIFY_SHOW_ID", "e332ec80e9304868ad57121904b8c9c3"),
    },
    "apple_podcasts": {
        "host": os.getenv("APPLE_PODCAST_HOST", "buzzsprout"),
        "api_key": os.getenv("APPLE_PODCAST_API_KEY", ""),
        "show_id": os.getenv("APPLE_PODCAST_SHOW_ID", ""),
        "apple_id": os.getenv("APPLE_PODCAST_APPLE_ID", ""),
        "apple_password": os.getenv("APPLE_PODCAST_APPLE_PASSWORD", ""),
    },
    "gemini": {
        "api_key": os.getenv("GEMINI_API_KEY", "AIzaSyDn0AHc5mgUQn01MMxU5f-s5U3SUn-xfC0"),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "enabled": bool(os.getenv("GEMINI_API_KEY", "AIzaSyDn0AHc5mgUQn01MMxU5f-s5U3SUn-xfC0")),
    },
    # Ethique / conformite
    "ethics": {
        "enabled": True,
        # Mots interdits (insultes, haine, violence) — detection de base
        "banned_words": [
            "hate", "kill", "murder", "terror", "bomb", "weapon",
            "drug", "porn", "sex", "nude", "racist", "nazi",
        ],
        # Longueur max des descriptions par plateforme
        "max_desc_length": {
            "tiktok": 2200,
            "youtube": 5000,
            "dailymotion": 3000,
            "facebook": 63206,
            "instagram": 2200,
            "x": 280,
            "snapchat": 250,
            "pinterest": 500,
            "telegram": 1024,
            "spotify": 4000,
            "apple_podcasts": 4000,
        },
        # Disclaimer ajoute aux actualites
        "news_disclaimer": {
            "fr": "Information issue d'un flux RSS, non verifiee independamment.",
            "en": "Information from an RSS feed, not independently verified.",
            "en-gb": "Information from an RSS feed, not independently verified.",
            "en-au": "Information from an RSS feed, not independently verified.",
            "en-in": "Information from an RSS feed, not independently verified.",
            "es": "Informacion de un feed RSS, no verificada independientemente.",
            "pt": "Informacao de um feed RSS, nao verificada independentemente.",
            "de": "Information aus einem RSS-Feed, nicht unabhaengig geprueft.",
            "ar": "معلومات من مصدر RSS، لم يتم التحقق منها بشكل مستقل.",
            "zh": "来自RSS来源的信息，未经独立验证。",
            "ja": "RSSフィードからの情報。独立した確認は行われていません。",
            "ko": "RSS 피드의 정보이며 독립적으로 확인되지 않았습니다.",
            "hi": "आरएसएस फ़ीड से प्राप्त जानकारी, स्वतंत्र रूप से सत्यापित नहीं।",
            "th": "ข้อมูลจากฟีดRSS ไม่ได้รับการตรวจสอบอย่างอิสระ",
            "vi": "Thông tin từ nguồn RSS, chưa được xác minh độc lập.",
            "id": "Informasi dari feed RSS, belum diverifikasi secara independen.",
            "ru": "Информация из RSS-канала, независимо не проверена.",
            "sw": "Taarifa kutoka kwa RSS, haijachunguzwa kivyake.",
            "am": "ከRSS ምንጭ የመጣ መረጃ፣ በነፃነት አልተረጋገጠም።",
            "yo": "Alaye lati ọdọ RSS, a ko ṣẹ̀yìn àyẹ̀wò tọkànna.",
            "zu": "Ulwazi lusuka ku-RSS, aluhlolwanga ngokuzimele.",
        },
        # Attribution source obligeatoire
        "require_attribution": True,
    },
    # Email
    "email": {
        "enabled": True,
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER", "hugo.satabin.01@gmail.com"),
        "smtp_password": os.getenv("SMTP_PASSWORD", "Ingrandes86*"),
        "from_addr": os.getenv("SMTP_FROM", "hugo.satabin.01@gmail.com"),
        "to_addr": os.getenv("EMAIL_TO", "hugo.satabin.01@gmail.com"),
        "use_tls": True,
    },
    # Upload via navigateur (clics dans les interfaces web)
    # au lieu des API, avec un rythme lent "humain" pour
    # limiter les captchas. Telegram reste en API bot, les
    # podcasts passent par le flux RSS (aucun navigateur).
    "browser": {
        "enabled": bool(os.getenv("BROWSER_UPLOAD", "1")
                          not in ("0", "false", "no")),
        "headless": False,
        # Repertoire "User Data" d'un Edge existant pour
        # reutiliser sa session (SSO). Ferme Edge avant de
        # lancer, sinon le profil est verrouille. Vide =
        # profil dedie dans profile_dir.
        "edge_user_data_dir": os.getenv("EDGE_USER_DATA_DIR",
                                         ""),

        "profile_dir": os.getenv("BROWSER_PROFILE_DIR",
                                   ".browser_profiles"),
        "platforms": ["tiktok", "youtube", "dailymotion",
                      "facebook", "instagram", "x",
                      "pinterest", "snapchat"],
        # Pauses entre chaque action (secondes)
        "min_delay": 3.0,
        "max_delay": 9.0,
        # Vitesse de frappe par caractere (secondes)
        "typing_min": 0.08,
        "typing_max": 0.35,
        # Pause entre deux plateformes (secondes)
        "gap_min": 30.0,
        "gap_max": 90.0,
    },
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("publisher")

# ---------------------------------------------------------------------------
# Modeles de donnees
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    index: int
    text: str
    narration: str
    caption: str
    palette: tuple
    language: str = "fr"


@dataclass
class Story:
    id: str
    theme: str
    title: str
    episodes: list[Episode] = field(default_factory=list)
    language: str = "fr"
    source: str = "predefined"  # predefined, wikipedia, news

    @property
    def episode_count(self) -> int:
        return len(self.episodes)


def _ep(i, text, caption, palette_idx=0):
    return Episode(
        index=i,
        text=textwrap.fill(text, width=38),
        narration=text,
        caption=caption,
        palette=CONFIG["palettes"][palette_idx % len(CONFIG["palettes"])],
        language="fr",
    )

# ---------------------------------------------------------------------------
# Banque d'histoires vulgarisees (FR source)
# ---------------------------------------------------------------------------

def build_stories():
    """20 histoires en francais vulgarise, accessible a tous."""
    stories = []

    # 1. Stoicisme (philosophie) - 5 ep
    s = Story(id="stoicisme", theme="philosophie",
              title="Le Stoicisme en 5 actes")
    s.episodes = [
        _ep(1, "Il y a 2000 ans, un homme nait esclave. "
               "Son nom : Epictete. Il decouvre une chose enorme : "
               "on peut tout perdre, sauf une chose. Notre facon de reagir.",
            "La liberte interieure, meme en chaine.", 3),
        _ep(2, "Voici sa grande idee : ce n'est pas ce qui arrive "
               "qui nous fait souffrir. C'est ce qu'on en pense. "
               "Change tes pensees, tu changes ta vie.",
            "L'opinion crée la souffrance, pas l'evenement.", 3),
        _ep(3, "Marc Aurele, l'empereur le plus puissant du monde, "
               "ecrit chaque matin pour lui-meme. Son conseil : "
               "sois la meilleure version de toi.",
            "L'empereur qui se governait lui-meme.", 3),
        _ep(4, "Le stoicisme pose une question simple : est-ce que "
               "ca depend de toi ? Si oui, agis. Si non, lache prise. "
               "C'est tout simple.",
            "Le critere d'action : depend-il de toi ?", 3),
        _ep(5, "Etre stoicien, ce n'est pas subir en silence. "
               "C'est agir avec lucidite. Ta volonte, pas ta "
               "resignation. C'est ca, le vrai stoicisme.",
            "Agir, pas subir : la lecon finale.", 3),
    ]
    stories.append(s)

    # 2. Mindset (psychologie) - 3 ep
    s = Story(id="mindset", theme="psychologie",
              title="L'etat d'esprit qui change tout")
    s.episodes = [
        _ep(1, "Carol Dweck etudie des enfants pendant 30 ans. "
               "Certains fuient l'effort, d'autres le cherchent. "
               "Pourquoi ? La reponse va te surprendre.",
            "La decouverte qui change tout sur le cerveau.", 1),
        _ep(2, "L'esprit fixe croit que l'intelligence est figee "
               "a la naissance. L'esprit de croissance sait qu'elle "
               "se muscle, comme un sportif.",
            "Fixe ou croissance : deux mondes.", 1),
        _ep(3, "Ajoute \"pas encore\" a chaque echec. \"Je ne sais "
               "pas... encore.\" Tout a coup, la voie se rouvre. "
               "Essaie, ca change la vie.",
            "Le mot qui transforme l'echec.", 1),
    ]
    stories.append(s)

    # 3. Senèque (volonté) - 4 ep
    s = Story(id="seneque", theme="volonte",
              title="Seneque : le temps vole")
    s.episodes = [
        _ep(1, "\"Ce n'est pas que nous avons peu de temps, c'est "
               "que nous en perdons beaucoup.\" Seneque, il y a "
               "2000 ans. Encore vrai aujourd'hui, non ?",
            "Le temps perdu par negligence.", 0),
        _ep(2, "Les gens ont peur qu'on les derange pendant leur "
               "vie. Mais ils laissent les autres les deranger sans "
               "fin. Protege ton temps.",
            "Proteger son temps, c'est proteger sa vie.", 0),
        _ep(3, "Organise ta journee comme un projet. Une heure pour "
               "penser, une pour agir, une pour reposer l'esprit. "
               "Simple, non ? Mais puissant.",
            "L'agenda comme arme de volonte.", 0),
        _ep(4, "Celui qui possede son temps possede tout. La volonte "
               "commence par la garde du calendrier. A toi de jouer.",
            "Le temps maitrise, fondement de la volonte.", 0),
    ]
    stories.append(s)

    # 4. Hypatie (culture) - 4 ep
    s = Story(id="hypatie", theme="culture",
              title="Hypatie, la lumiere d'Alexandrie")
    s.episodes = [
        _ep(1, "Vers 370, a Alexandrie, une femme enseigne la "
               "geometrie et l'astronomie. Elle s'appelle Hypatie. "
               "A cette epoque, c'est rare.",
            "Une savante dans un monde d'hommes.", 4),
        _ep(2, "Elle ameliore l'astrolabe (un outil pour mesurer "
               "les etoiles). Elle ecrit des commentaires sur les "
               "maths. La connaissance n'a pas de genre.",
            "La science sans frontieres.", 4),
        _ep(3, "Dans une ville qui s'embrase, elle refuse de fuir. "
               "Elle dit : defendre la verite est mon devoir. "
               "Quel courage !",
            "Le courage de rester.", 4),
        _ep(4, "Sa mort en 415 ferme une ere. Mais ses ecrits "
               "voyagent pendant mille ans. Une lumiere que le "
               "temps n'eteint pas.",
            "Une lumiere que le temps n'eteint pas.", 4),
    ]
    stories.append(s)

    # 5. Thorndike (psychologie) - 2 ep
    s = Story(id="thorndike", theme="psychologie",
              title="Pourquoi les habitudes collent")
    s.episodes = [
        _ep(1, "Edward Thorndike met des chats dans des boites. "
               "Ils apprennent a sortir par essais et recompenses. "
               "Plus ca marche, plus ils repetent.",
            "La loi de l'effet : repeter ce qui marche.", 2),
        _ep(2, "Tout ce que tu repetes devient automatique. "
               "Mauvaises ou bonnes habitudes. Choisis tes "
               "repetitions, tu choisis ta vie.",
            "Construis ta mecanique du succes.", 2),
    ]
    stories.append(s)

    # 6. Mandela (ambition) - 5 ep
    s = Story(id="mandela", theme="ambition",
              title="Mandela : 27 ans pour une idee")
    s.episodes = [
        _ep(1, "1962 : Nelson Mandela est arrete. Il risque la mort. "
               "Au tribunal, il dit : je suis pret a mourir pour "
               "cette idee. Quel courage !",
            "Le discours de Rivonia, un tournant.", 2),
        _ep(2, "Sur l'ile de Robben, il casse des roches pendant "
               "13 ans. Chaque matin, il medite et lit. La prison "
               "n'a pas son esprit.",
            "Une prison pour le corps, libre pour l'esprit.", 2),
        _ep(3, "Il apprend la langue de ses gardiens pour les "
               "comprendre. Comprendre l'autre, c'est preparer la "
               "paix. Quelle lecon !",
            "La langue de l'ennemi comme outil de paix.", 2),
        _ep(4, "1990 : il sort, sourit, et demande la reconciliation. "
               "Pas la vengeance. Le monde retient son souffle. "
               "Incroyable, non ?",
            "La victoire sans vengeance.", 2),
        _ep(5, "Il devient president en 1994. Il dit : l'education "
               "est l'arme la plus puissante pour changer le monde. "
               "D'une cellule a la presidence.",
            "D'une cellule a la presidence.", 2),
    ]
    stories.append(s)

    # 7. Dunning-Kruger (culture) - 3 ep
    s = Story(id="dunning", theme="culture",
              title="Pourquoi les ignorants sont surs d'eux")
    s.episodes = [
        _ep(1, "Un homme vole une banque le visage decouvert. "
               "Citron presse sur les yeux. Il pensait effacer ses "
               "traces. Vrai ! L'ignorance qui s'ignore.",
            "L'ignorance qui s'ignore.", 1),
        _ep(2, "Dunning et Kruger le prouvent : moins on sait, "
               "plus on se sent competent. C'est paradoxal, non ? "
               "L'incompetence masque la competence.",
            "Une courbe vertigineuse de l'ego.", 1),
        _ep(3, "Le remede ? Le doute. Le doute actif. Questionner, "
               "tester, ecouter les autres. La modestie est une "
               "methode, pas une faiblesse.",
            "Douter pour grandir, pas pour cesser.", 1),
    ]
    stories.append(s)

    # 8. Viktor Frankl (developpement personnel) - 4 ep
    s = Story(id="frankl", theme="developpement personnel",
              title="Frankl : un sens dans l'enfer")
    s.episodes = [
        _ep(1, "Viktor Frankl, psychiatre, est deporte a Auschwitz. "
               "La-bas, il observe qui survit et qui s'effondre. "
               "Le laboratoire ultime.",
            "Le laboratoire ultime du sens.", 0),
        _ep(2, "Ceux qui survivent ont un \"pourquoi\". Une lettre "
               "a ecrire, un enfant a revoir, une oeuvre a finir. "
               "Toi, quel est ton pourquoi ?",
            "Celui qui a un pourquoi supporte tout.", 0),
        _ep(3, "On peut tout prendre a un homme, sauf une chose : "
               "choisir son attitude face aux events. Ta derniere "
               "liberte, c'est ta reaction.",
            "La derniere liberte humaine.", 0),
        _ep(4, "Il fonde la logotherapie : soigner par le sens, pas "
               "par le plaisir. Cherche ta tache, tu trouveras ta "
               "force. Belle lecon, non ?",
            "Le sens comme remede.", 0),
    ]
    stories.append(s)

    # 9. Marie Curie (ambition) - 4 ep
    s = Story(id="curie", theme="ambition",
              title="Marie Curie : deux prix, un combat")
    s.episodes = [
        _ep(1, "A Paris, une Polonaise exclue de l'universite "
               "etudie en cachette. Elle s'appelle Maria Sklodowska. "
               "Personne ne croit en elle. Elle, si.",
            "L'education volee, reconquise en secret.", 0),
        _ep(2, "Avec Pierre Curie, elle isole le radium a mains "
               "nues dans un hangar. Le poison rayonne. Elle ignore "
               "le danger. La science passe avant tout.",
            "Decouvrir la radioactivite, au peril de sa vie.", 0),
        _ep(3, "1903 : premier Nobel. On veut l'ignorer car elle "
               "est femme. Pierre exige qu'elle soit citee. Elle "
               "l'est. Quelle victoire !",
            "Le Nobel qu'on a voulu effacer.", 0),
        _ep(4, "1911 : second Nobel, seule. Elle meurt en 1934 d'un "
               "mal que ses carnets rayonnent encore aujourd'hui. "
               "Le sacrifice de la connaissance.",
            "Le sacrifice de la connaissance.", 0),
    ]
    stories.append(s)

    # 10. Le colibri (positivite) - 3 ep
    s = Story(id="colibri", theme="positivite",
              title="La parabole du colibri")
    s.episodes = [
        _ep(1, "Un incendie ravage la foret. Tous les animaux "
               "fuient, terrifies. Sauf un colibri qui vole vers "
               "la riviere. Etrange, non ?",
            "Quand le desespoir brule tout.", 2),
        _ep(2, "Le colibri prend une goutte d'eau dans son bec, la "
               "verse sur le feu, recommence. Encore. Encore. "
               "Ca parait fou, non ?",
            "Une goutte contre l'incendie.", 2),
        _ep(3, "Le tatou raille : c'est inutile ! Le colibri "
               "repond : je fais ma part. Fais ta part. C'est "
               "tout simple. Mais puissant.",
            "Fais ta part : la reponse du colibri.", 2),
    ]
    stories.append(s)

    # 11. Pygmalion (positivite) - 3 ep
    s = Story(id="pygmalion", theme="positivite",
              title="Pygmalion : croire transforme")
    s.episodes = [
        _ep(1, "Des chercheurs annoncent a des professeurs : ces "
               "eleves vont exploser. C'est faux. C'est au hasard. "
               "Mais ca va changer tout.",
            "Un mensonge pour une experience.", 1),
        _ep(2, "Huit mois plus tard, ces eleves ont vraiment "
               "progresse. Les attentes des adultes les ont "
               "transformes. Incroyable, non ?",
            "La prophetie qui se realise.", 1),
        _ep(3, "Croire en quelqu'un le fait grandir. Le decourager "
               "l'ecrase. Ton attente est une semence. Choisis-la "
               "bien.",
            "Ce que tu attends, tu le fais eclore.", 1),
    ]
    stories.append(s)

    # 12. Epicure (philosophie) - 3 ep
    s = Story(id="epicure", theme="philosophie",
              title="Epicure : le bonheur simple")
    s.episodes = [
        _ep(1, "Epicure vit dans un jardin, entoure d'amis. Il "
               "refuse le luxe et la gloire. Le bonheur, dit-il, "
               "est sobre. Simple.",
            "Le philosophe du jardin.", 2),
        _ep(2, "\"La mort n'est rien pour nous. Quand nous sommes, "
               "elle n'est pas. Quand elle est, nous ne sommes "
               "plus.\" Efficace, non ?",
            "L'angoisse de la mort desamorcee.", 2),
        _ep(3, "Trois besoins : un ami, la liberte, le loisir de "
               "penser. Le reste est bruit. Le reste est piege. "
               "A mediter.",
            "La recette du bonheur, il y a 2300 ans.", 2),
    ]
    stories.append(s)

    # 13. Harriet Tubman (volonte) - 4 ep
    s = Story(id="tubman", theme="volonte",
              title="Harriet Tubman : la conductrice")
    s.episodes = [
        _ep(1, "Nee esclave vers 1822, Harriet s'enfuit seule, de "
               "nuit, vers les Etats libres. Elle ne revient pas "
               "pour oublier. Au contraire.",
            "Une femme qui refuse d'etre une propriete.", 2),
        _ep(2, "Elle revient 13 fois. Elle guide 70 personnes vers "
               "le Nord par le chemin de fer clandestin. 13 retours "
               "en enfer. Pour les autres.",
            "13 retours en enfer pour liberer les autres.", 2),
        _ep(3, "Elle dit : je n'ai jamais perdu un passager. "
               "Le fusil sert a menacer, non l'esclave, mais sa "
               "peur. Quelle phrase !",
            "La route de la liberte, jalonnee de courage.", 2),
        _ep(4, "Pendant la guerre, elle espionne et mene un raid "
               "qui libere 700 esclaves en une nuit. De conductrice "
               "a commandante. Incroyable !",
            "De conductrice a commandante.", 2),
    ]
    stories.append(s)

    # 14. Conformite d'Asch (psychologie) - 3 ep
    s = Story(id="asch", theme="psychologie",
              title="Pourquoi on suit la foule")
    s.episodes = [
        _ep(1, "Une experience : des acteurs s'arretent dans la "
               "rue et regardent le ciel. Les passants imitent. "
               "Tous levent les yeux. Vrai !",
            "Quand le vide devient contagieux.", 1),
        _ep(2, "Solomon Asch le prouve : 75 % des gens nient "
               "l'evidence si la majority se trompe avant eux. "
               "La pression plie la vue. Effrayant, non ?",
            "L'evidence reniee par conformite.", 1),
        _ep(3, "L'antidote ? Savoir pourquoi tu crois ce que tu "
               "crois. La conviction se teste, ne se subit pas. "
               "Pense par toi-meme.",
            "Penser par soi-meme, un acte de courage.", 1),
    ]
    stories.append(s)

    # 15. L'ADN (biologie) - 4 ep
    s = Story(id="adn", theme="biologie",
              title="L'ADN : le code de la vie dechiffre")
    s.episodes = [
        _ep(1, "Dans les annees 1950, personne ne sait comment la "
               "vie se transmet de generation en generation. "
               "La reponse est cachee dans une molecule : l'ADN. "
               "Mais comment fonctionne-t-elle ?",
            "Le plus grand mystere de la biologie.", 0),
        _ep(2, "Rosalind Franklin prend une photo de l'ADN. "
               "Elle y voit une croix : deux brins enroules en "
               "helice. Cette image change tout. Mais elle ne le "
               "sait pas encore.",
            "La photo qui devait tout changer.", 0),
        _ep(3, "Watson et Crick utilisent cette photo. Ils "
               "proposent un modele : une double helice. Les deux "
               "brins se separent et se copient. C'est simple, "
               "c'est beau, c'est la vie.",
            "La double helice : la vie se copie.", 0),
        _ep(4, "L'ADN code des instructions en 4 lettres : A, T, "
               "G, C. Tes yeux, tes cheveux, ton metabolisme. "
               "Tout est ecrit dans ce livre miniature. Dans "
               "chacune de tes cellules.",
            "Quatre lettres pour ecrire toute la vie.", 0),
    ]
    stories.append(s)

    # 16. Mendeleev (chimie) - 4 ep
    s = Story(id="mendeleev", theme="chimie",
              title="Mendeleev : le tableau qui predit l'avenir")
    s.episodes = [
        _ep(1, "En 1869, on connait 63 elements. Mais personne "
               "ne voit l'ordre cache. Un chimiste russe, Dmitri "
               "Mendeleev, joue aux cartes avec les elements. "
               "Etrange methode, non ?",
            "Un chimiste qui joue aux cartes.", 3),
        _ep(2, "Il les classe par masse. Puis il remarque une "
               "repetition : toutes les 7 cases, les proprietes "
               "reviennent. Comme une chanson avec un refrain. "
               "La nature a un rythme !",
            "Le refrain cache des elements.", 3),
        _ep(3, "Son coup de genie : il laisse des cases vides. "
               "Il predit des elements qu'on n'a jamais vus. Il "
               "decrit leurs proprietes avant qu'elles existent. "
               "La science predit l'inconnu.",
            "Predire ce qui n'existe pas encore.", 3),
        _ep(4, "15 ans plus tard, le gallium est decouvert. Il "
               "rentre exactement dans la case vide. Puis le "
               "germanium. Le tableau avait raison. La chimie a "
               "une carte, comme un explorateur.",
            "Le tableau avait raison. Toujours.", 3),
    ]
    stories.append(s)

    # 17. Euler (mathematiques) - 4 ep
    s = Story(id="euler", theme="mathematiques",
              title="Euler : le genie qui voyait des ponts partout")
    s.episodes = [
        _ep(1, "En 1736, la ville de Konigsberg a 7 ponts. Les "
               "habitants se demandent : peut-on tous les traverser "
               "sans repasser deux fois sur le meme ? Personne ne "
               "trouve. Euler, lui, regarde autrement.",
            "7 ponts, 1 question, 1 genie.", 4),
        _ep(2, "Euler simplifie le probleme : il remplace les "
               "iles par des points, les ponts par des lignes. "
               "La carte devient un dessin simple. Cette idee "
               "fonde une nouvelle branche des maths : les "
               "graphes.",
            "Remplacer le reel par des points et des lignes.", 4),
        _ep(3, "Sa reponse : non, c'est impossible. Le raisonnement "
               "est elegant. Si un point a un nombre impair de "
               "ponts, on doit y commencer ou finir. Or il y en a "
               "trop. Donc impossible. Simple et puissant.",
            "La demonstration la plus elegante du siecle.", 4),
        _ep(4, "Euler, mal voyant puis aveugle, continue de "
               "calculer de tete. Il publie plus de 800 travaux. "
               "Le nombre e, le nombre i, les formules qui relient "
               "tout. Un esprit qui ne s'eteint pas.",
            "L'aveugle qui voyait plus loin que tous.", 4),
    ]
    stories.append(s)

    # 18. Les 4 vertus stoiciennes (stoicisme) - 4 ep
    s = Story(id="vertus_stoiciennes", theme="stoicisme",
              title="Les 4 piliers du stoicisme")
    s.episodes = [
        _ep(1, "Les stoiciens disent : pour vivre bien, tu n'as "
               "pas besoin de tout. Tu as besoin de 4 vertus. "
               "Pas 10, pas 100. Quatre. Simple, non ? Voici la "
               "premiere : la sagesse.",
            "4 vertus pour vivre bien. La premiere.", 3),
        _ep(2, "La sagesse, c'est savoir distinguer le bien du "
               "mal, l'utile du superflu. Epictete resume : ne "
               "desire que ce qui depend de toi. Le reste est "
               "bruit. C'est la clarte qui guide.",
            "La sagesse : voir clair dans le bruit.", 3),
        _ep(3, "Le courage : agir avec droiture, meme quand on "
               "a peur. Marc Aurele, empereur, affronte la guerre, "
               "la peste, la trahison. Il ecrit : le courage n'est "
               "pas l'absence de peur, mais l'action juste.",
            "Le courage : agir juste, meme effraye.", 3),
        _ep(4, "La temperance et la justice. La temperance : ni "
               "trop ni trop peu, le juste milieu. La justice : "
               "traiter chacun avec dignite. Ces 4 piliers "
               "tiennent la maison. La tienne. A batir.",
            "Les 4 piliers tiennent la maison. La tienne.", 3),
    ]
    stories.append(s)

    # 19. La guerre froide (geopolitique) - 5 ep
    s = Story(id="guerre_froide", theme="geopolitique",
              title="La guerre froide : 45 ans de peur")
    s.episodes = [
        _ep(1, "1947 : deux superpuissances se font face. USA et "
               "URSS. Pas de guerre directe, mais une peur "
               "permanente. Chacun veut convaincre le monde que "
               "son modele est le bon. Ca dure 45 ans.",
            "Deux geants, un monde coupe en deux.", 0),
        _ep(2, "Le mur de Berlin, 1961. Une ville coupee en "
               "deux par du beton. Les familles separentes. "
               "C'est le symbole d'un monde divise. Est contre "
               "Ouest. liberte contre controle.",
            "Le mur qui a coupe une ville et un monde.", 0),
        _ep(3, "1962 : Cuba. Des missiles sovietiques pointes "
               "vers les USA. 13 jours ou le monde frôle la "
               "guerre nucleaire. Kennedy et Khrouchtchev "
               "reculent de justesse. Ouf !",
            "13 jours ou le monde a tremble.", 0),
        _ep(4, "La guerre froide ne fait pas que des morts "
               "directes. Elle arme des camps, divise des pays, "
               "attise des conflits locaux. Du Vietnam a "
               "l'Afghanistan, les deux camps se battent par "
               "pays interposes.",
            "La guerre par d'autres mains.", 0),
        _ep(5, "1989 : le mur tombe. L'URSS s'effondre en 1991. "
               "Un monde bipolaire devient multipolaire. Mais "
               "les traces restent : frontieres, mefiances, "
               "armes nucleaires. La geopolitique ne s'arrete "
               "jamais vraiment.",
            "Le mur tombe, les traces restent.", 0),
    ]
    stories.append(s)

    # 20. Le controle des detroits (geopolitique) - 4 ep
    s = Story(id="detroits", theme="geopolitique",
              title="Les detroits : portes du monde")
    s.episodes = [
        _ep(1, "Un detroit, c'est un passage entre deux mers. "
               "Qui controle le passage controle le commerce. "
               "Simple. Puissant. Dangereux. Les empires l'ont "
               "toujours su.",
            "Qui controle la porte, controle tout.", 1),
        _ep(2, "Le detroit d'Ormuz : 20% du petrole mondial "
               "passe par la. Un seul pays, l'Iran, peut le "
               "fermer. Imagine : un point sur la carte qui "
               "fait trembler l'economie mondiale.",
            "Le point qui fait trembler le monde.", 1),
        _ep(3, "Bosphore, Malacca, Hormuz, Gibraltar : quatre "
               "portes, quatre bouchons. Si l'un se ferme, le "
               "commerce mondial s'etrangle. La geopolitique "
               "se joue sur quelques kilometres d'eau.",
            "Quatre portes pour toute la planete.", 1),
        _ep(4, "Aujourd'hui, la Chine construit des routes et "
               "des ports pour contourner ces detroits. Le "
               "nouveau Silk Road. La geopolitique change de "
               "terrain mais pas de regle : qui controle les "
               "routes, controle le futur.",
            "Les routes changent, la regle reste.", 1),
    ]
    stories.append(s)

    return stories

# ---------------------------------------------------------------------------
# Traducteur (deep-translator)
# ---------------------------------------------------------------------------

class Translator:
    """Traduit textes et histoires via Google Translate."""

    def __init__(self, config):
        self.enabled = config["translator"]["enabled"]
        self._gt = None
        if self.enabled:
            try:
                from deep_translator import GoogleTranslator
                self._gt = GoogleTranslator
            except ImportError:
                log.warning("deep-translator non installe. "
                            "Seul le francais sera disponible.")
                self.enabled = False

    def translate(self, text, source="fr", target="en"):
        if not self.enabled or source == target or not text:
            return text
        try:
            tr = self._gt(source=source, target=target)  # type: ignore
            return tr.translate(text)
        except Exception as exc:
            log.warning("Traduction %s->%s echouee : %s",
                        source, target, exc)
            return text

    def translate_story(self, story, target_lang):
        """Traduit une Story entiere vers target_lang."""
        if target_lang == story.language:
            return story

        tr_episodes = []
        for ep in story.episodes:
            raw = self.translate(ep.narration, "fr", target_lang)
            width = LANGUAGES[target_lang]["text_width"]
            tr_episodes.append(Episode(
                index=ep.index,
                text=textwrap.fill(raw, width=width),
                narration=raw,
                caption=self.translate(ep.caption, "fr", target_lang),
                palette=ep.palette,
                language=target_lang,
            ))

        slug = story.id.replace("_", "-")[:30]
        return Story(
            id=slug + "_" + target_lang,
            theme=story.theme,
            title=self.translate(story.title, "fr", target_lang),
            episodes=tr_episodes,
            language=target_lang,
            source=story.source,
        )

# ---------------------------------------------------------------------------
# Vulgarisateur
# ---------------------------------------------------------------------------

class Vulgarizer:
    """Simplifie un texte pour le rendre accessible a tous."""

    SIMPLIFICATIONS = {
        "neanmoins": "mais",
        "toutefois": "cependant",
        "subsequemment": "ensuite",
        "paradigme": "modele",
        "empirique": "pratique",
        "epistemologique": "sur la connaissance",
        "metaphysique": "au-dela du visible",
        "ontologique": "sur l'etre",
        "teleologique": "avec un but",
        "hermeneutique": "interpretation",
        "pragmatique": "pratique",
        "heuristique": "qui aide a decouvrir",
        "aporie": "impasse",
        "sophisme": "faux raisonnement",
        "doxographique": "compilation d'opinions",
        "consubstantiel": "de meme nature",
        "hermeneutique": "interpretation",
        "axiologique": "sur les valeurs",
        "hegemonique": "dominant",
        "synchronique": "a un instant donne",
        "diachronique": "dans le temps",
        # Biologie
        "mitochondrie": "usine d'energie de la cellule",
        "photosynthese": "facon dont les plantes fabriquent leur nourriture",
        "replication": "copie",
        "transcription": "lecture du code",
        "traduction": "fabrication de la proteine",
        "genotype": "code genetique",
        "phenotype": "aspect visible",
        "eucaryote": "cellule avec noyau",
        "procaryote": "cellule sans noyau",
        "haploide": "une seule copie des genes",
        "diploide": "deux copies des genes",
        # Chimie
        "stoichiometrie": "proportions des ingredients",
        "electronegativite": "force d'attraction des electrons",
        "isomere": "meme formule, forme differente",
        "enthalpie": "chaleur degagee",
        "entropy": "desordre",
        "endothermique": "absorbe la chaleur",
        "exothermique": "degage de la chaleur",
        "covalent": "liaison par partage",
        "ionique": "liaison par attraction",
        # Mathematiques
        "topologie": "etude des formes deformables",
        "differenciation": "calcul du taux de variation",
        "integration": "calcul de l'aire sous la courbe",
        "asymptote": "ligne qu'on frôle sans toucher",
        "determinant": "nombre qui resume une matrice",
        "eigenvalue": "valeur propre",
        "eigenvector": "vecteur propre",
        "conjecture": "hypothese non prouvee",
        "axiome": "verite de depart non demontree",
        "lemme": "petit theoreme preparatoire",
        "corollaire": "consequence directe",
    }

    def __init__(self, config=None):
        self.cfg = config or CONFIG
        self.gemini_enabled = self.cfg.get("gemini",
                                            {}).get("enabled", False)
        self.gemini_model = self.cfg.get("gemini",
                                          {}).get("model",
                                                  "gemini-2.0-flash")
        self.gemini_key = self.cfg.get("gemini", {}).get("api_key", "")

    def _vulgarize_gemini(self, text):
        """Utilise Gemini pour vulgariser intelligemment un texte."""
        if not self.gemini_enabled or not self.gemini_key:
            return text
        try:
            import requests
            url = ("https://generativelanguage.googleapis.com/v1beta/"
                    "models/" + self.gemini_model +
                    ":generateContent?key=" + self.gemini_key)
            prompt = (
                "Tu es un conteur passionne. Raconte ce texte comme si tu "
                "parlais a un ami autour d'un cafe. Utilise un langage "
                "simple, des phrases courtes et vivantes. Mets-y de "
                "l'emotion et du suspens. Ne mets pas de titres, de listes "
                "ou de mise en forme. Reponds uniquement avec le texte "
                "raconte, sans introduction ni conclusion. Texte:\n\n"
                + text
            )
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                },
            }
            resp = requests.post(url, json=body, timeout=30)
            if resp.ok:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content",
                                              {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", text).strip()
            log.warning("Gemini vulgarisation echouee: %s",
                         resp.status_code)
        except Exception as exc:
            log.warning("Gemini indisponible: %s", exc)
        return text

    def vulgarize(self, text):
        """Vulgarise un texte : Gemini si disponible, sinon dictionnaire."""
        if self.gemini_enabled:
            return self._vulgarize_gemini(text)
        # Fallback : remplacement par dictionnaire
        for complex_word, simple_word in self.SIMPLIFICATIONS.items():
            text = text.replace(complex_word, simple_word)
            text = text.replace(complex_word.capitalize(),
                                simple_word.capitalize())
        return text

# ---------------------------------------------------------------------------
# Wikipedia (multi-langue)
# ---------------------------------------------------------------------------

class WikipediaFetcher:
    """Recupere un article Wikipedia au hasard, dans la langue cible."""

    THEMES = {
        "ambition": ["ambition", "reussite", "entrepreneur", "pionnier"],
        "psychologie": ["psychologie", "cognition", "comportement",
                        "perception", "emotion"],
        "philosophie": ["philosophie", "philosophe", "ethique",
                        "metaphysique", "sagesse"],
        "culture": ["art", "litterature", "musique", "civilisation",
                    "peinture"],
        "histoire": ["histoire", "bataille", "empire", "revolution",
                     "decouverte"],
        "developpement personnel": ["motivation", "habitude",
                                    "resilience", "sagesse"],
        "volonte": ["volonte", "discipline", "perseverance",
                    "courage", "determination"],
        "positivite": ["optimisme", "bonheur", "gratitude",
                       "espoir", "bienveillance"],
    }

    def __init__(self, config):
        self.cfg = config
        import requests
        self.requests = requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MultiPlatformPublisher/1.0 (educational)"
        })

    def _random_titles(self, lang, count=5):
        domain = LANGUAGES[lang]["wiki_domain"]
        params = {"action": "query", "format": "json", "list": "random",
                  "rnnamespace": 0, "rnlimit": count * 2}
        resp = self.session.get("https://" + domain + "/w/api.php",
                                params=params, timeout=15)
        resp.raise_for_status()
        titles = [item["title"] for item in
                  resp.json().get("query", {}).get("random", [])]
        return titles[:count]

    def _summary(self, title, lang):
        import urllib.parse
        domain = LANGUAGES[lang]["wiki_domain"]
        encoded = urllib.parse.quote(title)
        url = "https://" + domain + "/api/rest_v1/page/summary/" + encoded
        resp = self.session.get(url, timeout=15)
        if not resp.ok:
            return None
        return resp.json()

    def _split_episodes(self, text, max_ep=5):
        text = re.sub(r"\[[\d,\s]+\]", "", text)
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        episodes = []
        current = []
        words = 0
        target = 28
        for sent in sentences:
            sw = len(sent.split())
            if words + sw > target and current:
                episodes.append(" ".join(current).strip())
                current = [sent]
                words = sw
                if len(episodes) >= max_ep:
                    break
            else:
                current.append(sent)
                words += sw
        if current and len(episodes) < max_ep:
            episodes.append(" ".join(current).strip())
        return episodes[:max_ep] if episodes else [text[:300]]

    def _guess_theme(self, title, extract):
        combined = (title + " " + extract).lower()
        best, score = "culture", 0
        for theme, keywords in self.THEMES.items():
            s = sum(1 for kw in keywords if kw in combined)
            if s > score:
                score, best = s, theme
        return best

    def fetch(self, lang="fr", max_episodes=5):
        for _ in range(5):
            try:
                titles = self._random_titles(lang, 5)
            except Exception as exc:
                log.warning("Wikipedia: echec titres (%s) : %s",
                            lang, exc)
                time.sleep(2)
                continue
            for title in titles:
                summary = self._summary(title, lang)
                if not summary:
                    continue
                extract = summary.get("extract", "")
                if len(extract) < 150:
                    continue
                theme = self._guess_theme(title, extract)
                eps = self._split_episodes(extract, max_episodes)
                palette_idx = random.randint(
                    0, len(self.cfg["palettes"]) - 1)
                episodes = []
                for i, txt in enumerate(eps, 1):
                    cap = txt[:80].rsplit(" ", 1)[0] + "..."
                    episodes.append(Episode(
                        index=i,
                        text=textwrap.fill(
                            txt, width=LANGUAGES[lang]["text_width"]),
                        narration=txt,
                        caption=cap,
                        palette=self.cfg["palettes"][palette_idx],
                        language=lang,
                    ))
                slug = title.lower().replace(" ", "_")[:30]
                story = Story(
                    id="wiki_" + slug + "_" + lang,
                    theme=theme,
                    title=title,
                    episodes=episodes,
                    language=lang,
                    source="wikipedia",
                )
                log.info("Wikipedia [%s] : '%s' (%s, %d ep.)",
                          lang, title, theme, len(episodes))
                return story
        log.warning("Wikipedia [%s] : aucun article pertinent.", lang)
        return None

# ---------------------------------------------------------------------------
# Actualites (RSS)
# ---------------------------------------------------------------------------

class NewsFetcher:
    """Recupere une actualite au hasard via RSS et la vulgarise."""

    def __init__(self, config):
        self.cfg = config
        self.vulg = Vulgarizer(config)
        import requests
        self.requests = requests

    def _parse_feed(self, url):
        try:
            import feedparser
        except ImportError:
            log.warning("feedparser non installe. Actualites "
                        "desactivees.")
            return []
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))
            if title and len(summary) > 50:
                entries.append((title, summary))
        return entries

    def fetch(self, lang="fr"):
        feeds = NEWS_FEEDS.get(lang, NEWS_FEEDS.get("fr", []))
        if not feeds:
            log.warning("Actualites [%s] : aucun flux RSS.", lang)
            return None
        all_entries = []
        for url in feeds:
            try:
                all_entries.extend(self._parse_feed(url))
            except Exception as exc:
                log.warning("RSS [%s] echec %s : %s", lang, url, exc)
        if not all_entries:
            log.warning("Actualites [%s] : aucun article.", lang)
            return None
        title, summary = random.choice(all_entries)
        summary = self.vulg.vulgarize(summary)
        max_ep = self.cfg["news"]["max_episodes"]
        # Decoupage en episodes courts
        sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
        episodes = []
        current = []
        words = 0
        for sent in sentences:
            sw = len(sent.split())
            if words + sw > 28 and current:
                episodes.append(" ".join(current).strip())
                current = [sent]
                words = sw
                if len(episodes) >= max_ep:
                    break
            else:
                current.append(sent)
                words += sw
        if current and len(episodes) < max_ep:
            episodes.append(" ".join(current).strip())
        if not episodes:
            episodes = [summary[:300]]
        palette_idx = random.randint(0, len(self.cfg["palettes"]) - 1)
        ep_list = []
        for i, txt in enumerate(episodes, 1):
            cap = txt[:80].rsplit(" ", 1)[0] + "..."
            ep_list.append(Episode(
                index=i,
                text=textwrap.fill(
                    txt, width=LANGUAGES[lang]["text_width"]),
                narration=txt,
                caption=cap,
                palette=self.cfg["palettes"][palette_idx],
                language=lang,
            ))
        slug = re.sub(r"[^a-z0-9]", "_", title.lower())[:30]
        story = Story(
            id="news_" + slug + "_" + lang,
            theme="actualite",
            title=title[:100],
            episodes=ep_list,
            language=lang,
            source="news",
        )
        log.info("Actualites [%s] : '%s' (%d ep.)",
                  lang, title[:60], len(ep_list))
        return story

# ---------------------------------------------------------------------------
# Selecteur automatique
# ---------------------------------------------------------------------------

class StorySelector:
    """Cyclise les histoires predefinies puis puise dans Wikipedia."""

    JOURNAL = Path("published_stories.json")

    def __init__(self, config):
        self.cfg = config
        self.predefined = build_stories()
        self.wiki = WikipediaFetcher(config)
        self.published = self._load()

    def _load(self):
        if self.JOURNAL.exists():
            try:
                data = json.loads(self.JOURNAL.read_text())
                return set(data.get("published_ids", []))
            except Exception:
                pass
        return set()

    def _save(self):
        self.JOURNAL.write_text(json.dumps(
            {"published_ids": sorted(self.published)},
            ensure_ascii=False, indent=2))

    def mark(self, story_id):
        self.published.add(story_id)
        self._save()

    def next_story(self, use_wiki=True):
        for story in self.predefined:
            if story.id not in self.published:
                return story
        if use_wiki:
            story = self.wiki.fetch(lang=self.cfg["source_language"])
            if story and story.id not in self.published:
                return story
        if self.predefined:
            self.published.clear()
            self._save()
            return self.predefined[0]
        return None

# ---------------------------------------------------------------------------
# Planificateur quotidien
# ---------------------------------------------------------------------------

class DailyScheduler:
    """Publie une histoire a des heures fixes, 5 fois par jour."""

    def __init__(self, publisher, times=None):
        self.publisher = publisher
        self.times = times or ["08:00", "11:00", "14:00", "17:00", "20:00"]

    def _next_run(self, now):
        from datetime import datetime, timedelta, time as dtime
        slots = []
        for t in self.times:
            h, m = t.split(":")
            cand = datetime.combine(now.date(), dtime(int(h), int(m)))
            if cand > now:
                slots.append(cand)
        if slots:
            return min(slots)
        h, m = self.times[0].split(":")
        return datetime.combine(
            now.date() + timedelta(days=1), dtime(int(h), int(m)))

    def run_forever(self, use_wiki=True, use_news=True):
        from datetime import datetime
        log.info("Planificateur demarre - creneaux : %s",
                  ", ".join(self.times))
        while True:
            now = datetime.now()
            target = self._next_run(now)
            wait = (target - now).total_seconds()
            log.info("Prochaine publication a %s (dans %.0f s)",
                      target.strftime("%Y-%m-%d %H:%M"), wait)
            time.sleep(max(wait, 0))
            try:
                self._publish_one(use_wiki, use_news)
            except Exception as exc:
                log.error("Publication planifiee echouee : %s — "
                           "planificateur continue.", exc)

    def _publish_one(self, use_wiki, use_news):
        from datetime import datetime
        selector = StorySelector(self.publisher.cfg)
        hour = datetime.now().hour
        # Le dernier creneau du jour -> actualite
        last_slot = self.times[-1].split(":")[0]
        story = None
        if use_news and str(hour) == last_slot:
            nf = NewsFetcher(self.publisher.cfg)
            story = nf.fetch(lang=self.publisher.cfg["source_language"])
        if not story:
            story = selector.next_story(use_wiki=use_wiki)
        if not story:
            log.warning("Aucune histoire a publier.")
            return
        log.info("=== Publication : %s (%s) - %d ep ===",
                  story.title, story.theme, story.episode_count)
        self.publisher.run([story])
        selector.mark(story.id)

# ---------------------------------------------------------------------------
# Generateur video (multilingue + RTL)
# ---------------------------------------------------------------------------

class VideoGenerator:
    """Genere une video verticale 10 s par episode, dans la langue cible."""

    def __init__(self, config):
        self.cfg = config
        self.work_dir = Path(config["work_dir"])
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _gradient(self, c_top, c_bottom, size):
        from PIL import Image, ImageDraw
        w, h = size
        img = Image.new("RGB", (w, h), c_top)
        draw = ImageDraw.Draw(img)
        for y in range(h):
            ratio = y / max(h - 1, 1)
            r = int(c_top[0] + (c_bottom[0] - c_top[0]) * ratio)
            g = int(c_top[1] + (c_bottom[1] - c_top[1]) * ratio)
            b = int(c_top[2] + (c_bottom[2] - c_top[2]) * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        path = self.work_dir / ("bg_%d_%d_%d_%dx%d.png" % (r, g, b, w, h))
        img.save(path, "PNG")
        return str(path)

    def _tts(self, ep, lang_code):
        cfg = self.cfg["tts"]
        if not cfg["enabled"]:
            return None
        try:
            from gtts import gTTS
        except ImportError:
            log.warning("gTTS non installe, voix off desactivee.")
            return None
        lang_cfg = LANGUAGES[lang_code]
        out_dir = self.work_dir / "tts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("%s_%s.mp3" % (lang_code, id(ep)))
        try:
            tts = gTTS(text=ep.narration, lang=lang_cfg["tts_lang"],
                       slow=cfg["slow"], tld=lang_cfg["tts_tld"])
            tts.save(str(out_path))
            return out_path
        except Exception as exc:
            log.warning("gTTS echoue : %s", exc)
            return None

    def _music(self):
        mc = self.cfg["music"]
        if not mc["enabled"]:
            return None
        d = Path(mc["dir"])
        if not d.is_dir():
            return None
        tracks = sorted(d.glob("*.mp3"))
        if not tracks:
            return None
        return random.choice(tracks)

    def _audio(self, ep, lang_code, dur):
        from moviepy import (AudioFileClip, CompositeAudioClip,
                                     concatenate_audioclips)
        tracks = []
        tts_path = self._tts(ep, lang_code)
        if tts_path and tts_path.exists():
            voice = AudioFileClip(str(tts_path))
            if voice.duration > dur:
                voice = voice.subclipped(0, dur)
            tracks.append(voice)
        music_path = self._music()
        if music_path:
            mc = self.cfg["music"]
            music = AudioFileClip(str(music_path)).with_volume_scaled(mc["volume"])
            if music.duration < dur:
                loops = int(dur / music.duration) + 1
                music = concatenate_audioclips(
                    [music] * loops).subclipped(0, dur)
            else:
                music = music.subclipped(0, dur)
            from moviepy import afx
            music = music.with_effects([
                afx.AudioFadeIn(mc["fadein"]),
                afx.AudioFadeOut(mc["fadeout"])])
            tracks.append(music)
        if not tracks:
            return None
        return CompositeAudioClip(tracks).with_duration(dur)

    def _text_clip_ltr(self, text, color_top, color_bottom, lang_cfg):
        from moviepy import (ImageClip, TextClip,
                                     CompositeVideoClip)
        dur = self.cfg["duration_seconds"]
        bg = ImageClip(self._gradient(
            color_top, color_bottom,
            (self.cfg["width"], self.cfg["height"]))).with_duration(dur)
        font = lang_cfg["font_path"]
        fs = lang_cfg["font_size"]
        w = int(self.cfg["width"] * 0.85)
        try:
            txt = TextClip(text=text, font_size=fs, font=font,
                           color="white",
                           stroke_color="black", stroke_width=3,
                           method="caption", size=(w, None),
                           text_align="center")
        except Exception:
            txt = TextClip(text=text, font_size=fs, font=font,
                           color="white",
                           stroke_color="black", stroke_width=3,
                           method="caption", size=(w, None),
                           text_align="center")
        from moviepy import vfx
        txt = (txt.with_duration(dur)
               .with_effects([vfx.CrossFadeIn(0.6)])
               .with_position("center"))
        return CompositeVideoClip([bg, txt],
            size=(self.cfg["width"], self.cfg["height"])).with_duration(dur)

    def _text_clip_rtl(self, text, color_top, color_bottom, lang_cfg):
        """Rendu RTL via PIL (arabe) + ImageClip."""
        from PIL import Image, ImageDraw, ImageFont
        from moviepy import ImageClip, TextClip, CompositeVideoClip
        dur = self.cfg["duration_seconds"]
        bg_path = self._gradient(color_top, color_bottom,
            (self.cfg["width"], self.cfg["height"]))
        bg = ImageClip(bg_path).with_duration(dur)
        # Reshape arabe
        display_text = text
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            display_text = get_display(arabic_reshaper.reshape(text))
        except ImportError:
            log.warning("arabic-reshaper/python-bidi non installe. "
                        "Le texte arabe peut etre mal rendu.")
        display_text = str(display_text)
        # Cree image de texte via PIL
        w = int(self.cfg["width"] * 0.85)
        h = int(self.cfg["height"] * 0.6)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(lang_cfg["font_path"],
                                       lang_cfg["font_size"])
        except Exception:
            font = ImageFont.load_default()
        # Centrage multi-ligne
        lines = display_text.split("\n")  # type: ignore
        line_h = lang_cfg["font_size"] + 10
        total_h = line_h * len(lines)
        y = (h - total_h) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)  # type: ignore
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            # Contour noir
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    draw.text((x + ox, y + oy), line, font=font,
                              fill=(0, 0, 0, 255))  # type: ignore
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))  # type: ignore
            y += line_h
        txt_path = self.work_dir / ("txt_%s.png" % id(text))
        img.save(str(txt_path), "PNG")
        from moviepy import vfx
        txt_clip = ImageClip(str(txt_path)).with_duration(dur)
        txt_clip = txt_clip.with_effects([vfx.CrossFadeIn(0.6)])
        txt_clip = txt_clip.with_position("center")
        return CompositeVideoClip([bg, txt_clip],
            size=(self.cfg["width"], self.cfg["height"])).with_duration(dur)

    def render_episode(self, story, ep, lang_code):
        lang_cfg = LANGUAGES[lang_code]
        if lang_cfg["rtl"]:
            clip = self._text_clip_rtl(ep.text, *ep.palette, lang_cfg)  # type: ignore
        else:
            clip = self._text_clip_ltr(ep.text, *ep.palette, lang_cfg)  # type: ignore
        dur = self.cfg["duration_seconds"]
        audio = self._audio(ep, lang_code, dur)
        has_audio = audio is not None
        if has_audio:
            clip = clip.with_audio(audio)
        out_dir = self.work_dir / story.id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("ep%02d_%s.mp4" % (ep.index, lang_code))
        clip.write_videofile(
            str(out_path),
            fps=self.cfg["fps"],
            codec="libx264",
            audio_codec="aac",
            audio=has_audio,
            preset="medium",
            threads=4,
            logger=None,
        )
        log.info("Video generee [%s] : %s", lang_code, out_path)
        return out_path

    def render_podcast(self, story, ep, lang_code):
        """Genere un fichier audio MP3 (podcast) au lieu d'une video.
        Combine voix off + musique de fond, sans limite de duree."""
        from moviepy import (AudioFileClip, CompositeAudioClip,
                                     concatenate_audioclips)
        out_dir = self.work_dir / (story.id + "_podcast")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("ep%02d_%s.mp3" % (ep.index, lang_code))
        tracks = []
        # Voix off (duree naturelle, non tronquee)
        tts_path = self._tts(ep, lang_code)
        if tts_path and tts_path.exists():
            voice = AudioFileClip(str(tts_path))
            tracks.append(voice)
            dur = voice.duration
        else:
            # Si pas de TTS, on ne peut pas faire de podcast
            log.warning("Podcast: pas de voix off pour %s ep%d [%s],"
                        " skip.", story.id, ep.index, lang_code)
            return None
        # Musique de fond
        music_path = self._music()
        if music_path:
            mc = self.cfg["music"]
            music = AudioFileClip(str(music_path)).with_volume_scaled(mc["volume"])
            if music.duration < dur:
                loops = int(dur / music.duration) + 1
                music = concatenate_audioclips(
                    [music] * loops).subclipped(0, dur)
            else:
                music = music.subclipped(0, dur)
            from moviepy import afx
            music = music.with_effects([
                afx.AudioFadeIn(mc["fadein"]),
                afx.AudioFadeOut(mc["fadeout"])])
            tracks.append(music)
        audio = CompositeAudioClip(tracks).with_duration(dur)
        audio.write_audiofile(str(out_path), logger=None)
        log.info("Podcast genere [%s] : %s (%.1fs)",
                  lang_code, out_path, dur)
        return out_path

# ---------------------------------------------------------------------------
# Descriptions (multilingues)
# ---------------------------------------------------------------------------

class DescriptionBuilder:

    def __init__(self, config):
        self.cfg = config

    def _hashtags(self, lang_code):
        return " ".join(HASHTAGS_PER_LANG.get(lang_code,
                        HASHTAGS_PER_LANG["fr"]))

    def _intro(self, lang_code, ep_index, platform=None):
        """Hook naturel, varie selon l'episode ET la plateforme."""
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intros = t.get("intro", [""])
        # Decale l'index selon la plateforme pour que le meme episode
        # ait un intro different selon ou il est publie.
        offset = {"tiktok": 0, "youtube": 1, "dailymotion": 2,
                  "facebook": 3, "instagram": 4, "x": 1,
                  "snapchat": 2, "pinterest": 3, "telegram": 0,
                  "spotify": 1, "apple_podcasts": 2}
        shift = offset.get(platform, 0) if platform else 0
        return intros[(ep_index - 1 + shift) % len(intros)]

    def _outro(self, lang_code, ep_index, platform=None):
        """Closing naturel, varie selon l'episode ET la plateforme."""
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        outros = t.get("outro", [""])
        offset = {"tiktok": 0, "youtube": 2, "dailymotion": 1,
                  "facebook": 4, "instagram": 3, "x": 0,
                  "snapchat": 1, "pinterest": 2, "telegram": 3,
                  "spotify": 4, "apple_podcasts": 0}
        shift = offset.get(platform, 0) if platform else 0
        return outros[(ep_index - 1 + shift) % len(outros)]

    def _transition(self, lang_code, ep_index, platform=None):
        """Phrase de transition naturelle entre le hook et le contenu."""
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        transitions = t.get("transition", [""])
        if not transitions:
            return ""
        offset = {"tiktok": 1, "youtube": 0, "dailymotion": 3,
                  "facebook": 2, "instagram": 4, "x": 0,
                  "snapchat": 1, "pinterest": 2, "telegram": 3,
                  "spotify": 0, "apple_podcasts": 1}
        shift = offset.get(platform, 0) if platform else 0
        return transitions[(ep_index - 1 + shift) % len(transitions)]

    def _punch(self, lang_code, ep_index, platform=None):
        """Phrase d'impact apres le contenu, avant le CTA."""
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        punches = t.get("punch", [""])
        if not punches:
            return ""
        offset = {"tiktok": 2, "youtube": 3, "dailymotion": 0,
                  "facebook": 1, "instagram": 4, "x": 0,
                  "snapchat": 2, "pinterest": 3, "telegram": 1,
                  "spotify": 0, "apple_podcasts": 4}
        shift = offset.get(platform, 0) if platform else 0
        return punches[(ep_index - 1 + shift) % len(punches)]

    def _ep_label(self, lang_code, ep, story):
        """Label d'episode naturel, pas robotique."""
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        return (str(ep.index) + "/" + str(story.episode_count))

    def for_tiktok(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "tiktok")
        outro = self._outro(lang_code, ep.index, "tiktok")
        punch = self._punch(lang_code, ep.index, "tiktok")
        tags = self._hashtags(lang_code)
        # TikTok : hook + caption + punch + CTA + hashtags, conversationnel
        desc = (intro + " " + ep.caption + "\n\n" +
                punch + "\n" +
                t["sub_short"] + " " + outro + "\n\n" + tags)
        return desc

    def for_youtube(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "youtube")
        outro = self._outro(lang_code, ep.index, "youtube")
        transition = self._transition(lang_code, ep.index, "youtube")
        punch = self._punch(lang_code, ep.index, "youtube")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        tags_str = "\n".join(HASHTAGS_PER_LANG.get(lang_code,
                                    HASHTAGS_PER_LANG["fr"]))
        desc = (intro + "\n\n" + transition + " " + ep.caption + "\n\n" +
                punch + "\n\n" +
                t["sub_long"] + " " + outro + "\n\n" +
                "---\n" + story.title + " — " + t["episode"] + " " +
                self._ep_label(lang_code, ep, story) + "\n" +
                t["theme"] + ": " + story.theme + "\n\n" + tags_str)
        tags = [h.strip("#") for h in
                HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])]
        tags += [story.theme, story.source]
        return title, desc, tags

    def for_dailymotion(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "dailymotion")
        outro = self._outro(lang_code, ep.index, "dailymotion")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        tags_str = self._hashtags(lang_code)
        desc = (intro + " " + ep.caption + "\n\n" +
                t["sub_short"] + " " + outro + "\n\n" +
                tags_str)
        tags = [h.strip("#") for h in
                HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])]
        return title, desc, tags

    def for_facebook(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "facebook")
        outro = self._outro(lang_code, ep.index, "facebook")
        transition = self._transition(lang_code, ep.index, "facebook")
        punch = self._punch(lang_code, ep.index, "facebook")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        tags_str = self._hashtags(lang_code)
        desc = (intro + "\n\n" + transition + " " + ep.caption + "\n\n" +
                punch + "\n\n" +
                t["sub_long"] + " " + outro + "\n\n" + tags_str)
        tags = [h.strip("#") for h in
                HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])]
        return title, desc, tags

    def for_instagram(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "instagram")
        outro = self._outro(lang_code, ep.index, "instagram")
        punch = self._punch(lang_code, ep.index, "instagram")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        tags_str = self._hashtags(lang_code)
        desc = (intro + " " + ep.caption + "\n\n" +
                punch + "\n" +
                t["sub_short"] + " " + outro + "\n\n" + tags_str)
        tags = [h.strip("#") for h in
                HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])][:30]
        return title, desc, tags

    def for_x(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "x")
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        # X : 280 caracteres, hook + caption + 3 hashtags
        desc = (intro + " " + ep.caption + " " +
                " ".join(all_tags[:3]))[:280]
        tags = [h.strip("#") for h in all_tags]
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        return title, desc, tags

    def for_snapchat(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "snapchat")
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        desc = (intro + " " + ep.caption + " " +
                " ".join(all_tags[:5]))[:250]
        tags = [h.strip("#") for h in all_tags]
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        return title, desc, tags

    def for_pinterest(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "pinterest")
        outro = self._outro(lang_code, ep.index, "pinterest")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        desc = (intro + " " + ep.caption + "\n\n" +
                t["sub_long"] + " " + outro + "\n\n" +
                " ".join(all_tags))[:500]
        tags = [h.strip("#") for h in all_tags][:20]
        return title, desc, tags

    def for_telegram(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "telegram")
        outro = self._outro(lang_code, ep.index, "telegram")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        desc = (intro + "\n\n" + ep.caption + "\n\n" +
                t["sub_short"] + " " + outro + "\n\n" +
                " ".join(all_tags[:5]))[:1024]
        tags = [h.strip("#") for h in all_tags]
        return title, desc, tags

    def for_spotify(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "spotify")
        outro = self._outro(lang_code, ep.index, "spotify")
        transition = self._transition(lang_code, ep.index, "spotify")
        punch = self._punch(lang_code, ep.index, "spotify")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        desc = (intro + "\n\n" + transition + " " + ep.caption + "\n\n" +
                punch + "\n\n" +
                t["sub_long"] + " " + outro + "\n\n" +
                story.title + " — " + t["episode"] + " " +
                self._ep_label(lang_code, ep, story) + "\n" +
                t["theme"] + ": " + story.theme + "\n\n" +
                " ".join(all_tags[:5]))[:4000]
        tags = [h.strip("#") for h in all_tags]
        return title, desc, tags

    def for_apple_podcasts(self, story, ep, lang_code):
        t = DESCRIPTION_TEMPLATES.get(lang_code,
                                       DESCRIPTION_TEMPLATES["fr"])
        intro = self._intro(lang_code, ep.index, "apple_podcasts")
        outro = self._outro(lang_code, ep.index, "apple_podcasts")
        transition = self._transition(lang_code, ep.index, "apple_podcasts")
        punch = self._punch(lang_code, ep.index, "apple_podcasts")
        title = story.title + " — " + self._ep_label(lang_code, ep, story)
        all_tags = HASHTAGS_PER_LANG.get(lang_code, HASHTAGS_PER_LANG["fr"])
        desc = (intro + "\n\n" + transition + " " + ep.caption + "\n\n" +
                punch + "\n\n" +
                t["sub_long"] + " " + outro + "\n\n" +
                story.title + " — " + t["episode"] + " " +
                self._ep_label(lang_code, ep, story) + "\n" +
                t["theme"] + ": " + story.theme + "\n\n" +
                " ".join(all_tags[:5]))[:4000]
        tags = [h.strip("#") for h in all_tags]
        return title, desc, tags

# ---------------------------------------------------------------------------
# Uploaders
# ---------------------------------------------------------------------------

class BaseUploader:
    """Interface commune. `upload()` doit renvoyer l'identifiant du post
    cree, ou "" en cas d'echec / configuration manquante."""
    name = "base"

    def upload(self, video_path, title, description, tags):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# TikTok — Content Posting API v2 (Direct Post)
# https://developers.tiktok.com/doc/content-posting-api-get-started
# ---------------------------------------------------------------------------

class TikTokUploader(BaseUploader):
    """Publie via /v2/post/publish/video/init/ en FILE_UPLOAD.

    Tant que l'app n'a pas ete auditee par TikTok, tout contenu publie
    est force en visibilite privee (SELF_ONLY) quelle que soit la valeur
    demandee dans post_info.privacy_level. Voir le formulaire "App review"
    du Developer Portal.
    """
    name = "tiktok"
    INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

    def __init__(self, cfg):
        self.cfg = cfg["tiktok"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        if not self.cfg["access_token"]:
            log.warning("TikTok: token manquant, ignore.")
            return ""

        headers = {
            "Authorization": "Bearer " + self.cfg["access_token"],
            "Content-Type": "application/json; charset=UTF-8",
        }
        video_size = os.path.getsize(video_path)
        body = {
            "post_info": {
                "title": title[:2200],
                "privacy_level": self.cfg.get("privacy_level", "SELF_ONLY"),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        }

        log.info("TikTok: init upload...")
        resp = self.requests.post(self.INIT_URL, headers=headers,
                                   json=body, timeout=30)
        if not resp.ok:
            log.error("TikTok init: %s %s", resp.status_code, resp.text)
            return ""
        data = resp.json().get("data", {})
        publish_id = data.get("publish_id", "")
        upload_url = data.get("upload_url", "")
        if not publish_id or not upload_url:
            log.error("TikTok: reponse init incomplete: %s", resp.text)
            return ""

        with open(video_path, "rb") as fh:
            video_bytes = fh.read()
        put_headers = {
            "Content-Type": "video/mp4",
            "Content-Range": "bytes 0-%d/%d" % (video_size - 1, video_size),
        }
        put_resp = self.requests.put(upload_url, headers=put_headers,
                                      data=video_bytes, timeout=300)
        if not put_resp.ok:
            log.error("TikTok upload PUT: %s %s",
                       put_resp.status_code, put_resp.text)
            return ""

        return self._wait_status(headers, publish_id)

    def _wait_status(self, headers, publish_id, attempts=10, delay=3):
        for _ in range(attempts):
            time.sleep(delay)
            resp = self.requests.post(self.STATUS_URL, headers=headers,
                                       json={"publish_id": publish_id},
                                       timeout=30)
            if not resp.ok:
                log.warning("TikTok status: %s %s",
                            resp.status_code, resp.text)
                continue
            status = resp.json().get("data", {}).get("status", "")
            log.info("TikTok: statut = %s", status)
            if status == "PUBLISH_COMPLETE":
                log.info("TikTok: publie (id=%s)", publish_id)
                return publish_id
            if status == "FAILED":
                log.error("TikTok: echec de publication (id=%s): %s",
                           publish_id, resp.text)
                return ""
        log.warning("TikTok: statut non confirme apres attente (id=%s)",
                    publish_id)
        return publish_id


# ---------------------------------------------------------------------------
# YouTube — YouTube Data API v3
# ---------------------------------------------------------------------------

class YouTubeUploader(BaseUploader):
    name = "youtube"

    def __init__(self, cfg):
        self.cfg = cfg["youtube"]

    def _auth(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        import googleapiclient.discovery
        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        tp = Path(self.cfg["credentials_path"])
        creds = None
        if tp.exists():
            creds = Credentials.from_authorized_user_file(str(tp), scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.cfg["client_secret_path"], scopes)
                creds = flow.run_local_server(port=0)
            tp.write_text(creds.to_json())
        return googleapiclient.discovery.build(
            "youtube", "v3", credentials=creds)

    def upload(self, video_path, title, description, tags):
        if not Path(self.cfg["client_secret_path"]).exists():
            log.warning("YouTube: client_secret manquant, ignore.")
            return ""
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        yt = self._auth()
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags,
                "categoryId": "27",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(str(video_path), resumable=True,
                                 chunksize=-1, mimetype="video/*")
        req = yt.videos().insert(part="snippet,status", body=body,
                                  media_body=media)
        resp = None
        try:
            while resp is None:
                status, resp = req.next_chunk()
                if status:
                    log.info("YouTube: upload %d%%",
                             int(status.progress() * 100))
        except HttpError as exc:
            log.error("YouTube: %s", exc)
            return ""
        vid = resp.get("id", "")
        log.info("YouTube: publie (id=%s)", vid)
        return vid


# ---------------------------------------------------------------------------
# Dailymotion — Graph API + endpoint d'upload dedie
# ---------------------------------------------------------------------------

class DailymotionUploader(BaseUploader):
    """NB: le flux OAuth 'password' (username/password) est deprecie cote
    Dailymotion pour les comptes recents ; prefere un refresh_token obtenu
    une fois via le flux 'authorization_code' si le grant 'password' est
    refuse par ton application partenaire."""
    name = "dailymotion"

    def __init__(self, cfg):
        self.cfg = cfg["dailymotion"]
        import requests
        self.requests = requests

    def _token(self):
        url = "https://api.dailymotion.com/oauth/token"
        data = {
            "grant_type": "password",
            "username": self.cfg["username"],
            "password": self.cfg["password"],
            "client_id": self.cfg["api_key"],
            "client_secret": self.cfg["api_secret"],
        }
        resp = self.requests.post(url, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]

    def upload(self, video_path, title, description, tags):
        if not self.cfg["api_key"]:
            log.warning("Dailymotion: cle API manquante, ignore.")
            return ""
        try:
            token = self._token()
        except Exception as exc:
            log.error("Dailymotion auth: %s", exc)
            return ""

        headers = {"Authorization": "Bearer " + token}
        # Etape 1 : recuperer une URL d'upload dediee (obligatoire, ne pas
        # poster directement sur upload.dailymotion.com/v2/file sans elle).
        get_url_resp = self.requests.get(
            "https://api.dailymotion.com/file/upload",
            headers=headers, timeout=30)
        if not get_url_resp.ok:
            log.error("Dailymotion get upload url: %s %s",
                       get_url_resp.status_code, get_url_resp.text)
            return ""
        upload_url = get_url_resp.json().get("upload_url", "")
        if not upload_url:
            log.error("Dailymotion: pas d'upload_url.")
            return ""

        with open(video_path, "rb") as fh:
            up_resp = self.requests.post(upload_url,
                                          files={"file1": fh}, timeout=300)
        if not up_resp.ok:
            log.error("Dailymotion upload: %s %s",
                       up_resp.status_code, up_resp.text)
            return ""
        vid_url = up_resp.json().get("url", "")
        if not vid_url:
            log.error("Dailymotion: pas d'URL de fichier renvoyee.")
            return ""

        create_resp = self.requests.post(
            "https://api.dailymotion.com/me/videos",
            headers=headers,
            data={
                "url": vid_url,
                "title": title[:140],
                "description": description[:3000],
                "tags": ",".join(tags),
                "channel": "lifestyle",
                "published": "true",
                "private": "false",
            }, timeout=30)
        if not create_resp.ok:
            log.error("Dailymotion create: %s %s",
                       create_resp.status_code, create_resp.text)
            return ""
        vid = create_resp.json().get("id", "")
        log.info("Dailymotion: publie (id=%s)", vid)
        return vid


# ---------------------------------------------------------------------------
# Facebook — Graph API (video Page)
# ---------------------------------------------------------------------------

class FacebookUploader(BaseUploader):
    """Upload simple (POST multipart) : suffisant pour de courtes videos
    (~10 s). Pour des fichiers > ~100 Mo, utilise plutot l'upload
    resumable (start/transfer/finish) de la Graph API."""
    name = "facebook"

    def __init__(self, cfg):
        self.cfg = cfg["facebook"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        if not self.cfg["access_token"] or not self.cfg["page_id"]:
            log.warning("Facebook: token ou page_id manquant, ignore.")
            return ""
        api_ver = self.cfg["api_version"]
        url = "https://graph.facebook.com/%s/%s/videos" % (
            api_ver, self.cfg["page_id"])
        with open(video_path, "rb") as fh:
            data = {
                "title": title[:80],
                "description": description,
                "access_token": self.cfg["access_token"],
            }
            resp = self.requests.post(url, data=data,
                                       files={"source": fh}, timeout=300)
        if resp.ok:
            vid = resp.json().get("id", "")
            log.info("Facebook: publie (id=%s)", vid)
            return vid
        log.error("Facebook: %s %s", resp.status_code, resp.text)
        return ""


# ---------------------------------------------------------------------------
# Instagram — Instagram Graph API, protocole d'upload "resumable"
# https://developers.facebook.com/docs/instagram-platform/content-publishing/
# ---------------------------------------------------------------------------

class InstagramUploader(BaseUploader):
    """Compte professionnel Instagram lie a une Page Facebook.

    Le conteneur est cree sur graph.facebook.com, mais l'envoi des octets
    de la video se fait sur un host different : rupload.facebook.com,
    avec l'entete 'Authorization: OAuth <token>' (et non 'Bearer').
    """
    name = "instagram"

    def __init__(self, cfg):
        self.cfg = cfg["instagram"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        if not self.cfg["access_token"] or not self.cfg["account_id"]:
            log.warning("Instagram: token ou account_id manquant, ignore.")
            return ""
        api_ver = self.cfg["api_version"]
        graph_base = "https://graph.facebook.com/%s" % api_ver
        file_size = os.path.getsize(video_path)

        # Etape 1 : creer un conteneur d'upload resumable
        init_resp = self.requests.post(
            "%s/%s/media" % (graph_base, self.cfg["account_id"]),
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": description[:2200],
                "access_token": self.cfg["access_token"],
            }, timeout=30)
        if not init_resp.ok:
            log.error("Instagram init: %s %s",
                       init_resp.status_code, init_resp.text)
            return ""
        container_id = init_resp.json().get("id", "")
        if not container_id:
            log.error("Instagram: pas de container id.")
            return ""

        # Etape 2 : envoyer les octets sur rupload.facebook.com
        rupload_url = "https://rupload.facebook.com/ig-api-upload/%s/%s" % (
            api_ver, container_id)
        rupload_headers = {
            "Authorization": "OAuth " + self.cfg["access_token"],
            "offset": "0",
            "file_size": str(file_size),
        }
        with open(video_path, "rb") as fh:
            video_bytes = fh.read()
        up_resp = self.requests.post(rupload_url, headers=rupload_headers,
                                      data=video_bytes, timeout=300)
        if not up_resp.ok:
            log.error("Instagram rupload: %s %s",
                       up_resp.status_code, up_resp.text)
            return ""

        # Etape 3 : attendre que le conteneur soit pret (FINISHED)
        status_url = "%s/%s" % (graph_base, container_id)
        for _ in range(15):
            time.sleep(3)
            st_resp = self.requests.get(status_url, params={
                "fields": "status_code",
                "access_token": self.cfg["access_token"],
            }, timeout=30)
            status_code = st_resp.json().get("status_code", "")
            log.info("Instagram: statut conteneur = %s", status_code)
            if status_code == "FINISHED":
                break
            if status_code == "ERROR":
                log.error("Instagram: conteneur en erreur: %s", st_resp.text)
                return ""
        else:
            log.warning("Instagram: statut non confirme, tentative de "
                        "publication quand meme.")

        # Etape 4 : publier
        pub_resp = self.requests.post(
            "%s/%s/media_publish" % (graph_base, self.cfg["account_id"]),
            data={
                "creation_id": container_id,
                "access_token": self.cfg["access_token"],
            }, timeout=30)
        if pub_resp.ok:
            vid = pub_resp.json().get("id", "")
            log.info("Instagram: publie (id=%s)", vid)
            return vid
        log.error("Instagram publish: %s %s",
                   pub_resp.status_code, pub_resp.text)
        return ""


# ---------------------------------------------------------------------------
# X (Twitter) — API v2, upload chunke INIT/APPEND/FINALIZE
# https://docs.x.com/x-api/media/quickstart/media-upload-chunked
# ---------------------------------------------------------------------------

class XUploader(BaseUploader):
    """Depuis mai 2025, l'ancien endpoint monolithique v1.1
    upload.twitter.com/1.1/media/upload.json (OAuth1) est deprecie.
    L'API v2 exige desormais un jeton utilisateur OAuth2 (Bearer) et un
    flux en 3 etapes (INIT -> APPEND -> FINALIZE), y compris pour de
    petites videos."""
    name = "x"
    CHUNK_SIZE = 4 * 1024 * 1024  # 4 Mo

    def __init__(self, cfg):
        self.cfg = cfg["x"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        # cfg["x"]["user_access_token"] doit etre un jeton OAuth2 obtenu
        # via le flux Authorization Code + PKCE avec le scope
        # 'media.write' (le bearer_token "app-only" ne suffit pas ici).
        token = self.cfg.get("user_access_token") or self.cfg.get(
            "bearer_token")
        if not token:
            log.warning("X: jeton OAuth2 utilisateur manquant, ignore.")
            return ""
        headers = {"Authorization": "Bearer " + token}
        base = "https://api.x.com/2/media/upload"

        total_bytes = os.path.getsize(video_path)
        init_resp = self.requests.post(base, headers=headers, data={
            "command": "INIT",
            "media_type": "video/mp4",
            "total_bytes": total_bytes,
            "media_category": "tweet_video",
        }, timeout=30)
        if not init_resp.ok:
            log.error("X media init: %s %s",
                       init_resp.status_code, init_resp.text)
            return ""
        media_id = init_resp.json().get("data", {}).get("id", "")
        if not media_id:
            log.error("X: pas de media id (init).")
            return ""

        with open(video_path, "rb") as fh:
            segment_index = 0
            while True:
                chunk = fh.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                append_resp = self.requests.post(
                    base + "/%s/append" % media_id,
                    headers=headers,
                    data={"segment_index": segment_index},
                    files={"media": chunk}, timeout=120)
                if not append_resp.ok:
                    log.error("X media append: %s %s",
                               append_resp.status_code, append_resp.text)
                    return ""
                segment_index += 1

        fin_resp = self.requests.post(
            base + "/%s/finalize" % media_id,
            headers=headers, timeout=60)
        if not fin_resp.ok:
            log.error("X media finalize: %s %s",
                       fin_resp.status_code, fin_resp.text)
            return ""

        state = fin_resp.json().get("data", {}).get(
            "processing_info", {}).get("state", "succeeded")
        while state == "pending" or state == "in_progress":
            time.sleep(3)
            st_resp = self.requests.get(base, headers=headers,
                                         params={"media_id": media_id,
                                                 "command": "STATUS"},
                                         timeout=30)
            state = st_resp.json().get("data", {}).get(
                "processing_info", {}).get("state", "succeeded")
        if state == "failed":
            log.error("X: traitement du media echoue (id=%s)", media_id)
            return ""

        text = title[:220]
        tag_str = " ".join(tags[:3]) if tags else ""
        if tag_str and len(text) + 1 + len(tag_str) <= 280:
            text = text + " " + tag_str
        tweet_resp = self.requests.post(
            "https://api.x.com/2/tweets",
            headers={**headers, "Content-Type": "application/json"},
            json={"text": text[:280], "media": {"media_ids": [media_id]}},
            timeout=30)
        if tweet_resp.ok:
            tid = tweet_resp.json().get("data", {}).get("id", "")
            log.info("X: publie (id=%s)", tid)
            return tid
        log.error("X tweet: %s %s", tweet_resp.status_code, tweet_resp.text)
        return ""


# ---------------------------------------------------------------------------
# Snapchat Spotlight
# ---------------------------------------------------------------------------

class SnapchatUploader(BaseUploader):
    """IMPORTANT : contrairement aux autres plateformes, Snapchat n'expose
    pas d'API publique en libre-service pour poster automatiquement sur
    Spotlight. La publication programmatique de contenu passe par les
    outils partenaires (Snapchat Marketing/Business API, ou un
    partenariat Content Publisher accorde au cas par cas par Snap Inc.),
    et non par un endpoint REST documente equivalent a
    'api.snapchat.com/v2/spotlight'. Les URLs ci-dessous n'existent pas
    officiellement : ne pas s'y fier tel quel.

    Options realistes :
      1. Demander l'acces au programme Snap Content Publisher API
         (validation manuelle par Snap) puis suivre leur doc specifique.
      2. Publier manuellement via l'app Snapchat.
      3. Retirer Snapchat de la liste des plateformes automatisees.
    """
    name = "snapchat"

    def __init__(self, cfg):
        self.cfg = cfg["snapchat"]

    def upload(self, video_path, title, description, tags):
        log.warning(
            "Snapchat: pas d'API publique de publication automatique "
            "disponible pour ce type de compte. Publication ignoree — "
            "voir la docstring de SnapchatUploader pour les alternatives.")
        return ""


# ---------------------------------------------------------------------------
# Pinterest — API v5 (video Pin en 3 etapes)
# https://developers.pinterest.com/docs/api/v5/media-create/
# ---------------------------------------------------------------------------

class PinterestUploader(BaseUploader):
    name = "pinterest"

    def __init__(self, cfg):
        self.cfg = cfg["pinterest"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        if not self.cfg["access_token"] or not self.cfg["board_id"]:
            log.warning("Pinterest: token ou board_id manquant, ignore.")
            return ""
        headers = {"Authorization": "Bearer " + self.cfg["access_token"]}

        # Etape 1 : enregistrer l'intention d'upload (retourne une
        # upload_url S3 + des upload_parameters a renvoyer tels quels)
        reg_resp = self.requests.post(
            "https://api.pinterest.com/v5/media",
            headers={**headers, "Content-Type": "application/json"},
            json={"media_type": "video"}, timeout=30)
        if not reg_resp.ok:
            log.error("Pinterest register: %s %s",
                       reg_resp.status_code, reg_resp.text)
            return ""
        reg = reg_resp.json()
        media_id = reg.get("media_id", "")
        upload_url = reg.get("upload_url", "")
        upload_params = reg.get("upload_parameters", {})
        if not media_id or not upload_url:
            log.error("Pinterest: reponse d'enregistrement incomplete.")
            return ""

        # Etape 2 : uploader le fichier vers l'upload_url fournie
        with open(video_path, "rb") as fh:
            up_resp = self.requests.post(
                upload_url, data=upload_params,
                files={"file": fh}, timeout=300)
        if not up_resp.ok:
            log.error("Pinterest upload: %s %s",
                       up_resp.status_code, up_resp.text)
            return ""

        # Etape 3 : attendre que le traitement soit termine
        status_url = "https://api.pinterest.com/v5/media/%s" % media_id
        for _ in range(15):
            time.sleep(3)
            st_resp = self.requests.get(status_url, headers=headers,
                                         timeout=30)
            status = st_resp.json().get("status", "")
            log.info("Pinterest: statut media = %s", status)
            if status == "succeeded":
                break
            if status == "failed":
                log.error("Pinterest: traitement echoue: %s", st_resp.text)
                return ""

        # Etape 4 : creer le Pin video
        pin_resp = self.requests.post(
            "https://api.pinterest.com/v5/pins",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "board_id": self.cfg["board_id"],
                "title": title[:100],
                "description": description[:500],
                "media_source": {
                    "source_type": "video_id",
                    "media_id": media_id,
                    "cover_image_url": self.cfg.get("cover_image_url", ""),
                },
            }, timeout=30)
        if pin_resp.ok:
            pid = pin_resp.json().get("id", "")
            log.info("Pinterest: publie (id=%s)", pid)
            return pid
        log.error("Pinterest pin: %s %s",
                   pin_resp.status_code, pin_resp.text)
        return ""


# ---------------------------------------------------------------------------
# Telegram — Bot API (sendVideo)
# ---------------------------------------------------------------------------

class TelegramUploader(BaseUploader):
    """Cette plateforme necessite un canal par langue : utiliser send()
    (le Publisher appelle cette methode directement), pas upload()."""
    name = "telegram"

    def __init__(self, cfg):
        self.cfg = cfg["telegram"]
        import requests
        self.requests = requests

    def upload(self, video_path, title, description, tags):
        log.warning("Telegram: utiliser send(video_path, caption, "
                    "lang_code) — upload() n'est pas utilise pour "
                    "cette plateforme.")
        return ""

    def send(self, video_path, caption, lang_code):
        bot_token = self.cfg["bot_token"]
        if not bot_token:
            log.warning("Telegram: bot_token manquant, ignore.")
            return ""
        channel = self.cfg.get("channels", {}).get(lang_code, "")
        if not channel:
            log.warning("Telegram: aucun canal pour la langue '%s', "
                        "ignore.", lang_code)
            return ""
        # Une URL "https://t.me/xxx" n'est pas un chat_id
        # valide pour l'API bot : convertir en "@xxx".
        # (Les liens prives "t.me/+hash" ne sont de toute
        # facon utilisables que pour rejoindre un canal,
        # pas comme destination d'un bot.)
        m = re.match(r"(?:https?://)?t\.me/([^/\s]+)",
                    channel)
        if m and not m.group(1).startswith("+"):
            channel = "@" + m.group(1)
        url = "https://api.telegram.org/bot%s/sendVideo" % bot_token
        with open(video_path, "rb") as fh:
            resp = self.requests.post(url, data={
                "chat_id": channel,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            }, files={"video": fh}, timeout=300)
        if resp.ok:
            mid = resp.json().get("result", {}).get("message_id", "")
            log.info("Telegram [%s]: publie (msg=%s)", lang_code, mid)
            return str(mid)
        log.error("Telegram: %s %s", resp.status_code, resp.text)
        return ""


# ---------------------------------------------------------------------------
# Spotify (podcast)
# ---------------------------------------------------------------------------

class SpotifyUploader(BaseUploader):
    """IMPORTANT : Spotify for Podcasters (ex-Anchor) n'a pas d'API
    publique documentee. Le endpoint 'podcasters.spotify.com/api/v1'
    utilise dans la version precedente de ce script est un endpoint
    prive de l'application web (non contractuel, peut changer ou etre
    bloque sans preavis, et son usage automatise viole tres probablement
    les CGU de Spotify).

    Alternative fiable : heberger le flux RSS du podcast via un
    hebergeur avec une vraie API publique (Buzzsprout, Transistor,
    Podbean — voir ApplePodcastsUploader ci-dessous) et soumettre ce
    flux RSS une seule fois sur https://podcasters.spotify.com/ ;
    Spotify indexera alors automatiquement chaque nouvel episode du
    flux, sans upload direct necessaire cote script.
    """
    name = "spotify"

    def __init__(self, cfg):
        self.cfg = cfg["spotify"]

    def upload(self, audio_path, title, description, tags):
        log.warning(
            "Spotify: pas d'API publique stable pour publier "
            "directement. Publiez l'episode via un hebergeur RSS "
            "(voir ApplePodcastsUploader) : Spotify l'indexera "
            "automatiquement depuis le flux. Publication ignoree.")
        return ""


# ---------------------------------------------------------------------------
# Apple Podcasts (via hebergeur RSS)
# ---------------------------------------------------------------------------

class ApplePodcastsUploader(BaseUploader):
    """Apple Podcasts n'a pas d'API d'upload direct : la distribution se
    fait via un flux RSS indexe par Apple. Cette classe pousse l'episode
    vers un hebergeur tiers (Buzzsprout ou Transistor) qui met a jour ce
    flux RSS ; le meme flux, une fois soumis a Apple Podcasts Connect et
    a Spotify for Podcasters, suffit a diffuser sur les deux plateformes."""
    name = "apple_podcasts"
    HOST_URLS = {
        "buzzsprout": "https://www.buzzsprout.com/api",
        "transistor": "https://api.transistor.fm/v1",
    }

    def __init__(self, cfg):
        self.cfg = cfg["apple_podcasts"]
        import requests
        self.requests = requests

    def _upload_buzzsprout(self, audio_path, title, description, tags):
        api_key = self.cfg["api_key"]
        show_id = self.cfg["show_id"]
        url = "%s/%s/episodes.json" % (self.HOST_URLS["buzzsprout"], show_id)
        headers = {"Authorization": "Token token=" + api_key}
        with open(audio_path, "rb") as fh:
            resp = self.requests.post(url, headers=headers, data={
                "episode[title]": title[:200],
                "episode[description]": description[:4000],
                "episode[tags]": ",".join(tags[:10]),
            }, files={"episode[audio_file]": fh}, timeout=300)
        if resp.ok:
            eid = resp.json().get("id", "")
            log.info("Apple Podcasts (Buzzsprout): publie (id=%s)", eid)
            return str(eid)
        log.error("Buzzsprout: %s %s", resp.status_code, resp.text)
        return ""

    def _upload_transistor(self, audio_path, title, description, tags):
        api_key = self.cfg["api_key"]
        url = self.HOST_URLS["transistor"] + "/episodes"
        headers = {"x-api-key": api_key}
        with open(audio_path, "rb") as fh:
            resp = self.requests.post(url, headers=headers, data={
                "episode[title]": title[:200],
                "episode[summary]": description[:4000],
                "episode[status]": "published",
            }, files={"episode[audio_file]": fh}, timeout=300)
        if resp.ok:
            eid = resp.json().get("data", {}).get("id", "")
            log.info("Apple Podcasts (Transistor): publie (id=%s)", eid)
            return str(eid)
        log.error("Transistor: %s %s", resp.status_code, resp.text)
        return ""

    def upload(self, audio_path, title, description, tags):
        if not self.cfg["api_key"]:
            log.warning("Apple Podcasts: API key manquante, ignore.")
            return ""
        host = self.cfg.get("host", "buzzsprout")
        if host == "buzzsprout":
            return self._upload_buzzsprout(audio_path, title, description,
                                            tags)
        if host == "transistor":
            return self._upload_transistor(audio_path, title, description,
                                            tags)
        log.warning("Apple Podcasts: hebergeur '%s' non supporte.", host)
        return ""

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class EmailNotifier:

    def __init__(self, config):
        self.cfg = config["email"]

    def _configured(self):
        return all([self.cfg["smtp_host"], self.cfg["smtp_user"],
                     self.cfg["smtp_password"],
                     self.cfg.get("from_addr") or self.cfg["smtp_user"],
                     self.cfg["to_addr"]])

    def send(self, subject, body):
        if not self.cfg["enabled"]:
            return
        if not self._configured():
            log.warning("Email: config incomplete (SMTP_HOST, "
                        "SMTP_USER, SMTP_PASSWORD, EMAIL_TO).")
            return
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from_addr = self.cfg.get("from_addr") or self.cfg["smtp_user"]
        to_addr = self.cfg["to_addr"]
        msg = MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        try:
            if self.cfg["use_tls"]:
                server = smtplib.SMTP(self.cfg["smtp_host"],
                                      self.cfg["smtp_port"], timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(self.cfg["smtp_host"],
                                      self.cfg["smtp_port"], timeout=30)
            server.login(self.cfg["smtp_user"], self.cfg["smtp_password"])
            server.sendmail(from_addr, [to_addr], msg.as_string())
            server.quit()
            log.info("Email envoye a %s", to_addr)
        except Exception as exc:
            log.error("Email: echec : %s", exc)

    def notify(self, story, ep, results, lang_code):
        lang_name = LANGUAGES.get(lang_code, {}).get("name", lang_code)
        subject = ("Video publiee [" + lang_name + "] " +
                   story.title + " - Ep. " + str(ep.index) + "/" +
                   str(story.episode_count))
        lines = [
            "Langue : " + lang_name,
            "Source : " + story.source,
            "Histoire : " + story.title,
            "Theme : " + story.theme,
            "Episode : " + str(ep.index) + " / " + str(story.episode_count),
            "Resume : " + ep.caption,
            "",
            "Plateformes :",
        ]
        for platform, pid in results.items():
            status = "publie" if pid else "echec / ignore"
            extra = " (id=" + pid + ")" if pid else ""
            lines.append("  - " + platform + ": " + status + extra)
        lines += ["", "Texte : " + ep.text, "",
                  "--- Multi-Platform Publisher"]
        self.send(subject, "\n".join(lines))

# ---------------------------------------------------------------------------
# Verificateur ethique / conformite CGU
# ---------------------------------------------------------------------------

class EthicsChecker:
    """Verifie que le contenu respecte un code ethique et les CGU
    des plateformes avant publication.

    Controles effectues :
      1. Mots interdits (haine, violence, contenu explicite)
      2. Attribution de la source (Wikipedia, RSS, predefinie)
      3. Disclaimer pour les actualites (information non verifiee)
      4. Longueur de description dans les limites de chaque plateforme
      5. Pas de medical/misleading claims (sante, finance)
      6. Respect des droits : rappel musique/voix sous licence
    """

    # Categories de mots sensibles supplementaires
    MEDICAL_CLAIMS = [
        "cure", "traitement", "remede", "guerison", "vaccine cures",
        "cancer cure", "diet miracle",
    ]
    FINANCIAL_CLAIMS = [
        "get rich", "guaranteed profit", "double your money",
        "devenez riche", "profit garanti",
    ]

    def __init__(self, config):
        self.cfg = config["ethics"]
        self.max_lengths = self.cfg.get("max_desc_length", {})

    def check_text(self, text, lang_code="fr"):
        """Retourne (ok: bool, issues: list[str])."""
        issues = []
        if not self.cfg.get("enabled", True):
            return True, []
        text_lower = text.lower()
        # 1. Mots interdits
        for word in self.cfg.get("banned_words", []):
            if word in text_lower:
                issues.append(
                    "Mot interdit detecte: '" + word + "'")
        # 2. Claims medicaux
        for claim in self.MEDICAL_CLAIMS:
            if claim in text_lower:
                issues.append(
                    "Affirmation medicale sensible: '" + claim + "'")
        # 3. Claims financiers
        for claim in self.FINANCIAL_CLAIMS:
            if claim in text_lower:
                issues.append(
                    "Promesse financiere suspecte: '" + claim + "'")
        ok = len(issues) == 0
        return ok, issues

    def check_story(self, story, lang_code):
        """Verifie tous les episodes d'une story.
        Retourne (ok, issues_par_episode)."""
        all_ok = True
        per_ep = {}
        for ep in story.episodes:
            ok, issues = self.check_text(ep.text, lang_code)
            ok2, issues2 = self.check_text(ep.narration, lang_code)
            ok3, issues3 = self.check_text(ep.caption, lang_code)
            combined = issues + issues2 + issues3
            per_ep[ep.index] = combined
            if combined:
                all_ok = False
        return all_ok, per_ep

    def add_disclaimer(self, description, story, lang_code):
        """Ajoute un disclaimer pour les sources RSS/news."""
        if story.source == "news":
            disclaimers = self.cfg.get("news_disclaimer", {})
            disclaimer = disclaimers.get(lang_code,
                                          disclaimers.get("fr", ""))
            if disclaimer:
                description = description + "\n\n[" + disclaimer + "]"
        return description

    def add_attribution(self, description, story, lang_code):
        """Ajoute l'attribution de la source si requise."""
        if not self.cfg.get("require_attribution", True):
            return description
        if story.source == "wikipedia":
            domain = LANGUAGES.get(lang_code, {}).get("wiki_domain",
                            "fr.wikipedia.org")
            attrib = "Source: https://" + domain
            description = description + "\n\n" + attrib
        elif story.source == "news":
            attrib = "Source: RSS feed"
            description = description + "\n\n" + attrib
        return description

    def check_description_length(self, description, platform):
        """Verifie que la description respecte la limite de la plateforme."""
        max_len = self.max_lengths.get(platform, 5000)
        if len(description) > max_len:
            return False, ("Description trop longue pour " + platform +
                           " (" + str(len(description)) + "/" +
                           str(max_len) + ")")
        return True, ""

    def truncate_for_platform(self, description, platform):
        """Tronque la description a la limite de la plateforme."""
        max_len = self.max_lengths.get(platform, 5000)
        if len(description) > max_len:
            return description[:max_len - 3] + "..."
        return description

    def full_check(self, story, ep, lang_code, platform, description):
        """Verifie episode + description pour une plateforme donnee.
        Retourne (ok, issues, cleaned_description)."""
        issues = []
        # 1. Verifier le texte de l'episode
        ok, text_issues = self.check_text(ep.text, lang_code)
        issues += text_issues
        ok_n, narr_issues = self.check_text(ep.narration, lang_code)
        issues += narr_issues
        # 2. Verifier la description
        ok_d, desc_issues = self.check_text(description, lang_code)
        issues += desc_issues
        # 3. Ajouter disclaimer + attribution
        description = self.add_disclaimer(description, story, lang_code)
        description = self.add_attribution(description, story, lang_code)
        # 4. Verifier la longueur
        ok_len, len_issue = self.check_description_length(
            description, platform)
        if not ok_len:
            issues.append(len_issue)
            description = self.truncate_for_platform(description, platform)
        ok = len(issues) == 0
        return ok, issues, description

# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

class Publisher:

    def __init__(self, config=CONFIG):
        self.cfg = config
        self.generator = VideoGenerator(config)
        self.builder = DescriptionBuilder(config)
        self.notifier = EmailNotifier(config)
        self.translator = Translator(config)
        self.ethics = EthicsChecker(config)
        self.uploaders = [
            TikTokUploader(config),
            YouTubeUploader(config),
            DailymotionUploader(config),
            FacebookUploader(config),
            InstagramUploader(config),
            XUploader(config),
            SnapchatUploader(config),
            PinterestUploader(config),
            TelegramUploader(config),
            SpotifyUploader(config),
            ApplePodcastsUploader(config),
        ]
        # Sauf Telegram (API bot), remplacer les uploaders API par des
        # des uploaders navigateur pour les plateformes configurees :
        # uploaders navigateur : upload du fichier + remplissage
        # des formulaires par clics, a rythme lent (anti-captcha).
        if self.cfg.get("browser", {}).get("enabled", True):
            self.uploaders = browser_uploaders.apply(
                self.uploaders, config)

    def run(self, stories, dry_run=False, platforms=None,
            languages=None):
        chosen = self.uploaders
        if platforms:
            chosen = [u for u in self.uploaders if u.name in platforms]
        langs = languages or self.cfg["languages"]

        for story in stories:
            for lang_code in langs:
                # Traduire si necessaire
                if lang_code == story.language:
                    lang_story = story
                elif self.translator.enabled:
                    log.info("Traduction vers %s...", lang_code)
                    try:
                        lang_story = self.translator.translate_story(
                            story, lang_code)
                    except Exception as exc:
                        log.error("Traduction %s [%s] echouee, "
                                   "skip langue : %s", story.id,
                                   lang_code, exc)
                        continue
                else:
                    log.warning("Traducteur desactive, skip %s",
                                lang_code)
                    continue

                log.info("=== %s [%s] (%s) - %d ep ===",
                          lang_story.title, lang_code,
                          lang_story.theme, lang_story.episode_count)
                # Verifications ethiques pre-publication
                try:
                    ok, per_ep = self.ethics.check_story(
                        lang_story, lang_code)
                except Exception as exc:
                    log.error("Verif ethique %s [%s] echouee, "
                               "skip langue : %s", story.id,
                               lang_code, exc)
                    continue
                if not ok:
                    for ep_idx, issues in per_ep.items():
                        for iss in issues:
                            log.warning("ETHIQUE [%s ep%d]: %s",
                                         lang_code, ep_idx, iss)
                    if self.cfg.get("ethics",
                                     {}).get("enabled", True):
                        log.error("Story %s [%s] rejetee pour motifs "
                                   "ethiques, skip.",
                                   lang_story.id, lang_code)
                        continue
                for ep in lang_story.episodes:
                    try:
                        video_path = self.generator.render_episode(
                            lang_story, ep, lang_code)
                    except Exception as exc:
                        log.error("Generation echouee %s ep%d [%s] : %s",
                                   story.id, ep.index, lang_code, exc)
                        continue
                    # Generer le podcast audio si Spotify est dans
                    # les plateformes choisies
                    podcast_path = None
                    needs_podcast = any(
                        u.name in ("spotify", "apple_podcasts")
                        for u in chosen)
                    if needs_podcast and not dry_run:
                        try:
                            podcast_path = self.generator.render_podcast(
                                lang_story, ep, lang_code)
                        except Exception as exc:
                            log.warning("Podcast echouee %s ep%d [%s] : %s",
                                         story.id, ep.index, lang_code, exc)
                    if dry_run:
                        log.info("[DRY-RUN] %s [%s] : %s",
                                  story.id, lang_code, video_path)
                        continue
                    # Chaque plateforme est deja isolee dans
                    # _publish_all ; ces garde-fous empechent un
                    # probleme global (reseau, SMTP...) d arreter
                    # les episodes et plateformes suivants.
                    try:
                        results = self._publish_all(
                            chosen, lang_story, ep, video_path,
                            lang_code, podcast_path)
                    except Exception as exc:
                        log.error("Publication %s ep%d [%s] "
                                   "interrompue, on continue : %s",
                                   story.id, ep.index, lang_code, exc)
                        results = {}
                    try:
                        self.notifier.notify(
                            lang_story, ep, results, lang_code)
                    except Exception as exc:
                        log.warning("Notification %s ep%d [%s] "
                                     "echouee : %s", story.id,
                                    ep.index, lang_code, exc)
                    time.sleep(5)

    def _publish_all(self, uploaders, story, ep, video_path, lang_code,
                      podcast_path=None):
        results = {}
        for uploader in uploaders:
            try:
                # Construire la description selon la plateforme
                if uploader.name == "tiktok":
                    desc = self.builder.for_tiktok(story, ep, lang_code)
                    title = story.title + " " + str(ep.index)
                    tags = []
                elif uploader.name == "youtube":
                    title, desc, tags = self.builder.for_youtube(
                        story, ep, lang_code)
                elif uploader.name == "dailymotion":
                    title, desc, tags = self.builder.for_dailymotion(
                        story, ep, lang_code)
                elif uploader.name == "facebook":
                    title, desc, tags = self.builder.for_facebook(
                        story, ep, lang_code)
                elif uploader.name == "instagram":
                    title, desc, tags = self.builder.for_instagram(
                        story, ep, lang_code)
                elif uploader.name == "x":
                    title, desc, tags = self.builder.for_x(
                        story, ep, lang_code)
                elif uploader.name == "snapchat":
                    title, desc, tags = self.builder.for_snapchat(
                        story, ep, lang_code)
                elif uploader.name == "pinterest":
                    title, desc, tags = self.builder.for_pinterest(
                        story, ep, lang_code)
                elif uploader.name == "telegram":
                    title, desc, tags = self.builder.for_telegram(
                        story, ep, lang_code)
                else:
                    continue
                # Verifications ethiques avant upload
                ok, issues, desc = self.ethics.full_check(
                    story, ep, lang_code, uploader.name, desc)
                if not ok:
                    for iss in issues:
                        log.warning("ETHIQUE [%s/%s]: %s",
                                     uploader.name, lang_code, iss)
                    if self.cfg.get("ethics",
                                     {}).get("enabled", True):
                        log.error("Skip %s : contenu non conforme.",
                                   uploader.name)
                        results[uploader.name] = ""
                        continue
                if uploader.name == "telegram":
                    pid = uploader.send(video_path, desc, lang_code)
                elif uploader.name == "spotify":
                    if podcast_path:
                        pid = uploader.upload(
                            podcast_path, title, desc, tags)
                    else:
                        log.warning("Spotify: pas de fichier podcast,"
                                    " skip.")
                        pid = ""
                elif uploader.name == "apple_podcasts":
                    if podcast_path:
                        pid = uploader.upload(
                            podcast_path, title, desc, tags)
                    else:
                        log.warning("Apple Podcasts: pas de fichier"
                                    " podcast, skip.")
                        pid = ""
                else:
                    pid = uploader.upload(video_path, title, desc, tags)
                results[uploader.name] = pid
                # En mode navigateur, marquer une pause lente
                # aleatoire avant la plateforme suivante :
                # les enchainements d'actions trop rapides
                # declenchent les captchas.
                if getattr(uploader, "name", "") in (
                        self.cfg.get("browser", {}).get(
                            "platforms", [])):
                    bc = self.cfg.get("browser", {})
                    gap = random.uniform(
                        bc.get("gap_min", 30.0),
                        bc.get("gap_max", 90.0))
                    log.info("Pause anti-captcha: %.0fs avant"
                              " la plateforme suivante.", gap)
                    time.sleep(gap)
            except Exception as exc:
                log.error("Echec %s pour %s ep%d [%s] : %s",
                           uploader.name, story.id, ep.index,
                           lang_code, exc)
                results[uploader.name] = ""
        return results

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Genere et publie des videos courtes multi-plateforme "
                    "multilingues.")
    p.add_argument("--dry-run", action="store_true",
                   help="Genere sans publier.")
    p.add_argument("--story", type=str, default=None,
                   help="ID d'une histoire precise.")
    p.add_argument("--auto", action="store_true",
                   help="Selection auto (predefinie + Wikipedia).")
    p.add_argument("--wikipedia", action="store_true",
                   help="Un article Wikipedia au hasard.")
    p.add_argument("--news", action="store_true",
                   help="Actualite du jour (RSS).")
    p.add_argument("--schedule", action="store_true",
                   help="Planificateur quotidien (5 publications/jour).")
    p.add_argument("--times", nargs="*", default=None,
                   help="Horaires (ex: 08:00 12:00 18:00).")
    p.add_argument("--languages", nargs="*",
                   choices=list(LANGUAGES.keys()),
                   help="Langues de publication.")
    p.add_argument("--platforms", nargs="*",
                   choices=["tiktok", "youtube", "dailymotion",
                            "facebook", "instagram", "x",
                            "snapchat", "pinterest", "telegram",
                            "spotify", "apple_podcasts"],
                   help="Restreindre les plateformes.")
    p.add_argument("--login", nargs="*", default=None,
                   choices=list(browser_uploaders.BROWSER_PLATFORMS),
                   help="Ouvrir les navigateurs pour une connexion"
                        " manuelle (premiere utilisation), puis quitter.")
    p.add_argument("--api", action="store_true",
                   help="Utiliser les API officielles au lieu du"
                        " navigateur (mode clics lents).")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.login is not None:
        browser_uploaders.open_login(CONFIG, args.login)
        return
    if args.api:
        CONFIG.setdefault("browser", {})["enabled"] = False
    publisher = Publisher(CONFIG)

    if args.schedule:
        scheduler = DailyScheduler(publisher, times=args.times)
        scheduler.run_forever(use_wiki=True, use_news=True)
        return

    if args.auto:
        selector = StorySelector(CONFIG)
        story = selector.next_story(use_wiki=True)
        if not story:
            log.error("Aucune histoire a publier.")
            sys.exit(1)
        publisher.run([story], dry_run=args.dry_run,
                      platforms=args.platforms,
                      languages=args.languages)
        if not args.dry_run:
            selector.mark(story.id)
        log.info("Termine.")
        return

    if args.wikipedia:
        fetcher = WikipediaFetcher(CONFIG)
        story = fetcher.fetch(lang=CONFIG["source_language"])
        if not story:
            log.error("Wikipedia: aucun article.")
            sys.exit(1)
        publisher.run([story], dry_run=args.dry_run,
                      platforms=args.platforms,
                      languages=args.languages)
        log.info("Termine.")
        return

    if args.news:
        fetcher = NewsFetcher(CONFIG)
        story = fetcher.fetch(lang=CONFIG["source_language"])
        if not story:
            log.error("Actualites: aucun article.")
            sys.exit(1)
        publisher.run([story], dry_run=args.dry_run,
                      platforms=args.platforms,
                      languages=args.languages)
        log.info("Termine.")
        return

    stories = build_stories()
    if args.story:
        stories = [s for s in stories if s.id == args.story]
        if not stories:
            log.error("Aucune histoire avec l'id '%s'", args.story)
            sys.exit(1)
    publisher.run(stories, dry_run=args.dry_run,
                  platforms=args.platforms, languages=args.languages)
    log.info("Termine.")


if __name__ == "__main__":
    main()


# ===========================================================================
# README
# ===========================================================================
"""
INSTALLATION
------------
    pip install moviepy pillow gTTS requests google-auth google-auth-oauthlib \\
                google-api-python-client deep-translator feedparser \\
                arabic-reshaper python-bidi

    # ImageMagick requis pour le texte (moviepy)
    #   Ubuntu/Debian : sudo apt-get install imagemagick
    #   macOS : brew install imagemagick

POLICES NON-LATINES
-------------------
Pour un rendu correct des scripts non-latins, installe les polices Noto :
    - Ubuntu/Debian : sudo apt-get install fonts-noto fonts-noto-extra fonts-noto-cjk
    - macOS : brew tap homebrew/cask-fonts && brew cask install font-noto-sans font-noto-sans-cjk
    Polices utilisees par langue :
      ar  : /usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf
      zh  : /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
      ja  : /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
      ko  : /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
      hi  : /usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf
      th  : /usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf
      am  : /usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf
    Les autres langues utilisent DejaVuSans (inclus par defaut).

LANGUES
-------
~20 langues supportees : FR, EN, ES, PT, DE, AR, EN-GB/AU/IN,
    ZH, JA, KO, HI, TH, VI, ID, RU, SW, AM, YO, ZU.
    - Les histoires predefinies sont ecrites en francais vulgarise.
    - Elles sont traduites automatiquement via deep-translator (Google).
    - Wikipedia et les actualites (RSS) utilisent la langue native
      de chaque edition (meilleure qualite que la traduction).
    - L'arabe est rendu en RTL (right-to-left) via PIL + arabic-reshaper.
    - La voix off (gTTS) utilise la langue cible pour chaque video.

VULGARISATION
-------------
Le script simplifie le langage :
    - Histoires predefinies : ecrites en francais simple et direct.
    - Wikipedia/actualites : la classe Vulgarizer remplace les mots
      complexes par des equivalents simples.
    - Pour une vulgarisation avancee, integre une API LLM dans
      Vulgarizer.vulgarize().

ACTUALITES
----------
Le script recupere des articles d'actualite via RSS (feedparser) :
    - FR : Le Monde, France Info
    - EN : BBC, Deutsche Welle
    - ES : Deutsche Welle
    - PT : Deutsche Welle
    - DE : Deutsche Welle, Spiegel
    - AR : Deutsche Welle
    Les flux sont configurables dans NEWS_FEEDS.

UTILISATION
-----------
    # Tout publier dans les ~20 langues
    python multi_platform_publisher.py

    # Sans publier (verifier le rendu)
    python multi_platform_publisher.py --dry-run

    # Une histoire precise
    python multi_platform_publisher.py --story mandela

    # Langues specifiques seulement
    python multi_platform_publisher.py --languages fr en ar

    # Selection auto (predefinie puis Wikipedia)
    python multi_platform_publisher.py --auto

    # Un article Wikipedia au hasard
    python multi_platform_publisher.py --wikipedia

    # Actualite du jour
    python multi_platform_publisher.py --news

    # Planificateur (5 publications/jour dans toutes les langues)
    python multi_platform_publisher.py --schedule

    # Creneaux personnalises
    python multi_platform_publisher.py --schedule --times 09:00 13:00 19:00

    # YouTube seulement, en espagnol et anglais
    python multi_platform_publisher.py --platforms youtube --languages es en

NOTIFICATIONS EMAIL
-------------------
    export SMTP_HOST="smtp.gmail.com"
    export SMTP_PORT="587"
    export SMTP_USER="toi@gmail.com"
    export SMTP_PASSWORD="mot_de_passe_application"
    export EMAIL_TO="toi@gmail.com"
Un email est envoye a chaque publication (par episode, par langue).

AUTHENTIFICATION PLATEFORMES
----------------------------
TikTok : https://developers.tiktok.com/ (Content Posting API)
    export TIKTOK_CLIENT_KEY="..."
    export TIKTOK_CLIENT_SECRET="..."
    export TIKTOK_ACCESS_TOKEN="..."

YouTube : https://console.cloud.google.com/ (YouTube Data API v3)
    Telecharge client_secret.json a la racine.

Dailymotion : https://partner.dailymotion.com/
    export DAILYMOTION_API_KEY="..."
    export DAILYMOTION_API_SECRET="..."
    export DAILYMOTION_USERNAME="..."
    export DAILYMOTION_PASSWORD="..."

Facebook : https://developers.facebook.com/ (Graph API, Page video)
    export FACEBOOK_PAGE_ID="..."
    export FACEBOOK_ACCESS_TOKEN="..."
    export FACEBOOK_API_VERSION="v19.0"  # optionnel

Instagram : https://developers.facebook.com/ (Instagram Graph API)
    Compte professionnel relie a une page Facebook.
    export INSTAGRAM_ACCOUNT_ID="..."
    export INSTAGRAM_ACCESS_TOKEN="..."
    export INSTAGRAM_API_VERSION="v19.0"  # optionnel

X (Twitter) : https://developer.x.com/ (API v2, upload media chunke)
    Depuis mai 2025, l'upload video exige un jeton utilisateur OAuth 2.0
    (Authorization Code + PKCE, scopes tweet.write + media.write) —
    l'ancien flux OAuth 1.0a (consumer/access token) ne fonctionne plus
    pour l'upload de media.
    export X_USER_ACCESS_TOKEN="..."

Snapchat Spotlight : PAS d'API publique en libre-service.
    La publication automatisee sur Spotlight necessite un acces
    partenaire specifique (Snap Content Publisher API), accorde au cas
    par cas par Snap Inc. — il n'y a pas d'inscription self-service
    equivalente aux autres plateformes de cette liste. SnapchatUploader
    est laisse en place comme point d'extension mais ne publie rien
    tant que cet acces n'a pas ete obtenu.

Pinterest : https://developers.pinterest.com/ (API v5)
    export PINTEREST_ACCESS_TOKEN="..."
    export PINTEREST_BOARD_ID="..."

Telegram : https://core.telegram.org/bots/api (Bot API)
    Cree un bot via @BotFather, puis un canal par langue.
    Ajoute le bot comme administrateur de chaque canal.
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHANNEL_FR="@mon_canal_fr"
    export TELEGRAM_CHANNEL_EN="@my_channel_en"
    export TELEGRAM_CHANNEL_ES="@mi_canal_es"
    export TELEGRAM_CHANNEL_PT="@meu_canal_pt"
    export TELEGRAM_CHANNEL_DE="@mein_kanal_de"
    export TELEGRAM_CHANNEL_AR="@my_channel_ar"

Spotify (Podcast) : PAS d'API publique documentee.
    Spotify for Podcasters (ex-Anchor) n'expose aucune API officielle
    pour publier un episode par programme. La methode fiable est de
    soumettre une seule fois le flux RSS de ton hebergeur (Buzzsprout,
    Transistor...) sur https://podcasters.spotify.com/ : chaque nouvel
    episode ajoute au flux via ApplePodcastsUploader sera alors indexe
    automatiquement par Spotify, sans appel direct necessaire.

Apple Podcasts : via un hebergeur (Buzzsprout, Transistor)
    Apple n'offre pas d'upload direct : on pousse vers un hebergeur
    qui met a jour le flux RSS qu'Apple indexe.
    export APPLE_PODCAST_HOST="buzzsprout"  # ou "transistor"
    export APPLE_PODCAST_API_KEY="..."
    export APPLE_PODCAST_SHOW_ID="..."

VULGARISATION INTELLIGENTE (GEMINI)
-----------------------------------
    export GEMINI_API_KEY="..."
    export GEMINI_MODEL="gemini-2.0-flash"  # optionnel
Si GEMINI_API_KEY est defini, le script utilise Gemini pour
vulgariser les textes Wikipedia et actualites. Sinon, il utilise
le dictionnaire de remplacement integre.

NOM DE LA CHAINE
-----------------
    export CHANNEL_NAME="Cultivia"
Nom du compte sur toutes les plateformes (TikTok, YouTube, Instagram,
X, Telegram, etc.). 8 caracteres — compatible avec toutes les
limites de nom d'utilisateur. Modifiable via la variable
d'environnement CHANNEL_NAME.

VERIFICATION ETHIQUE / CGU
--------------------------
Le script verifie automatiquement avant chaque publication :
    1. Mots interdits (haine, violence, contenu explicite) dans le
       texte, la narration et la description.
    2. Affirmations medicales et financieres sensibles (cures, profits
       garantis, etc.).
    3. Attribution de la source (Wikipedia, RSS) ajoutee automatiquement.
    4. Disclaimer pour les actualites (information non verifiee) dans
       les ~20 langues.
    5. Respect des limites de longueur par plateforme (280 pour X,
       2200 pour TikTok/Instagram, 5000 pour YouTube, etc.).
    6. Troncature automatique si la description depasse la limite.
Si un contenu est rejete, il est skippe et un email d'echec est envoye.
Pour desactiver : CONFIG["ethics"]["enabled"] = False.

NOTES
-----
- Chaque video : 10 s, 1080x1920, H.264, voix off + musique 15%.
- Avec ~20 langues et 11 plateformes, chaque episode produit
  ~220 videos + ~40 podcasts (un podcast par langue sur Spotify
  + Apple Podcasts).
- Respecte les quotas YouTube (10000 unites/jour, 1 upload = 1600).
- Le time.sleep(5) entre publications est un minimum, a adapter.
- Verifie les droits de la musique et de la synthese vocale avant
  publication massive.
- Respecte les CGU de chaque plateforme (pas de spam, pas de contenu
  trompeur, pas d'usurpation d'identite).
"""