# PipPal Core - Competitor Matrix Source Evidence

Issue: [#59](https://github.com/bug-factory-kft/pippal/issues/59)

Target release branch: `release/0.2.4`

Evidence date / access date: 2026-05-14

Worker: AB

## Purpose

This is source evidence for a Core competitor matrix, not final
marketing copy. It records what official or primary sources verify and
keeps unverified items as hypotheses or unknowns.

Method:

- Prefer current official product, support, pricing, privacy, and local
  repo docs.
- Do not infer "no" from silence unless the source directly says so.
- Treat app-store claims, reviews, and third-party comparison copy as
  lower-confidence context unless repeated in official product docs.
- Use the same dimensions for every product so positioning work can
  compare facts without broad claims.

## Evidence Matrix

Legend:

- `Verified`: supported by a linked official/local source in this file.
- `Unknown`: not found in the official sources checked during this pass.
- `Hypothesis`: reasonable product inference, but not verified enough for
  buyer-facing copy.

### PipPal Core

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | The public Core source is MIT-licensed and the Community edition is described as fully usable on its own. Sources: [README](../README.md), [LICENSE.md](../LICENSE.md). | Packaged Store pricing is out of scope for Core/public; do not mix Pro price claims into this row. |
| Offline / local behavior | Core uses local Piper TTS, states "No cloud. No API keys. No telemetry.", and privacy docs say there is no analytics, telemetry, crash reporting, or usage statistics. Sources: [README](../README.md), [PRIVACY.md](PRIVACY.md), [ROADMAP.md](ROADMAP.md). | Fresh setup and voice installation can download Piper/voices over HTTPS; fully offline first-run after a clean clone is not verified. |
| Selected-text-anywhere behavior | Core selected-text reading uses a global hotkey and clipboard copy path. The release evidence warns the design works only when the focused app exposes selected text through normal copy semantics. Source: [SELECTED_TEXT_RELIABILITY.md](SELECTED_TEXT_RELIABILITY.md). | The broad "anywhere" claim is not release-proven; use constrained wording until the app compatibility matrix passes. |
| Document import | Explorer context-menu integration is documented for `.txt` and `.md` files. PDF / EPUB import is listed as a future roadmap item. Source: [ROADMAP.md](ROADMAP.md). | Rich document import beyond `.txt` / `.md` is not a Core v0.2.4 fact. |
| OCR / screenshot | No Core OCR or screenshot reader feature is documented in the checked Core docs. | Treat OCR/screenshot as absent from current Core positioning unless a separate implementation ticket lands. |
| Audio export | No user-facing Core audio export is documented in README/Roadmap. Source search only found plugin-oriented comments and benchmark wording, not a Core UI or CLI promise. | Human review should confirm whether any hidden/developer export path should be excluded from buyer-facing Core copy. |
| Queue / resume | Core documents Queue selection and Pause / Resume hotkeys. Roadmap notes current pause/resume restarts the current sentence from the start. Sources: [README](../README.md), [ROADMAP.md](ROADMAP.md). | Document-level resume across imported PDFs/EPUBs is a future roadmap item, not current Core. |
| Privacy posture | Local-first reading, no telemetry, no account requirement, and no cloud TTS in the open-source build are documented. Sources: [README](../README.md), [PRIVACY.md](PRIVACY.md), [ROADMAP.md](ROADMAP.md). | Privacy wording should mention setup-time downloads separately from reading-time text handling. |
| Windows fit | Windows tray app, global hotkeys, `winsound`, `pystray`, `keyboard`, Settings, autostart, and Explorer context menu are documented. Sources: [README](../README.md), [ROADMAP.md](ROADMAP.md). | Cross-platform support is future work; Windows is the only current Core fit claim. |

### Speechify

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Official pricing lists a Free plan with up to 1.5x speed, 10 robotic voices, and text-to-speech features only; Premium is listed at `$29 /Month` with 1000+ voices, 60+ languages, Scan & Listen, AI summaries/chats, and cloud-drive integrations. Source: [Speechify pricing](https://speechify.com/pricing/). | Annual effective pricing, trial terms, and plan limits beyond the visible pricing page need separate review before use. |
| Offline / local behavior | The privacy policy says user content includes text/documents uploaded, entered, or transmitted through the services, and saved content is stored locally and synced with Speechify servers. Source: [Speechify privacy](https://speechify.com/privacy/). | Windows offline reading behavior was not verified. Do not call it local-only. |
| Selected-text-anywhere behavior | Speechify has Windows, web, Chrome, Edge, Mac, iOS, and Android surfaces; the Windows page says users can listen to text anywhere on their computer. Sources: [Speechify Windows](https://speechify.com/windows/), [Speechify text-to-speech](https://speechify.com/text-to-speech-online/). | The checked sources did not verify a Windows-wide selected-text hotkey/clipboard behavior comparable to PipPal Core. |
| Document import | Official pages mention turning text, PDFs, books, docs, emails, articles, websites, and cloud-drive content into audio. Sources: [Speechify text-to-speech](https://speechify.com/text-to-speech-online/), [Speechify pricing](https://speechify.com/pricing/). | Exact supported file type list was not verified. |
| OCR / screenshot | Pricing lists Scan & Listen for Premium; the text-to-speech page describes OCR by taking a picture to scan written text. Sources: [Speechify pricing](https://speechify.com/pricing/), [Speechify text-to-speech](https://speechify.com/text-to-speech-online/). | Screenshot-reader behavior on Windows desktop was not verified. |
| Audio export | The text-to-speech page says users can listen to text or download audio instantly. Source: [Speechify text-to-speech](https://speechify.com/text-to-speech-online/). | Which plan gates download/export and any personal/commercial-use restrictions were not verified in this pass. |
| Queue / resume | The Chrome extension copy says users can pick up where they left off. Source: [Speechify text-to-speech](https://speechify.com/text-to-speech-online/). | Queueing multiple arbitrary selections was not found in official sources. |
| Privacy posture | Speechify says it does not sell information, collects user content, may use service providers, cookies/analytics/advertising tools, and employees generally do not monitor user content except listed circumstances. Source: [Speechify privacy](https://speechify.com/privacy/). | Needs legal/privacy review before making comparative privacy claims. |
| Windows fit | Official Windows app page links to Microsoft Store and describes Windows text-to-speech / dictation. Source: [Speechify Windows](https://speechify.com/windows/). | Relationship between Windows app, Edge extension, and web app feature parity was not verified. |

### NaturalReader

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Official help says basic features are available for free while advanced features require subscription. Plus is listed at `$20.90 USD/month` or `$119 USD/year`; Pro is `$25.90 USD/month` or `$159 USD/year`. Sources: [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version), [NaturalReader pricing](https://help.naturalreaders.com/en/articles/8854700-plans-pricing-personal-version). | Region/app-store tax differences are explicitly noted by NaturalReader; do not quote final checkout prices without checking region. |
| Offline / local behavior | The personal version is web/mobile/Chrome extension based; MP3 conversion lets subscribers create files for offline listening. Sources: [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version), [NaturalReader text/audio](https://help.naturalreaders.com/en/articles/11543218-working-with-text-and-audio-personal-version). | No local-only Windows TTS behavior was verified. |
| Selected-text-anywhere behavior | The Chrome extension reads online content in Chrome or Edge; click-to-read starts playback from text inside the app/browser flow. Sources: [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version), [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version). | No global Windows selected-text-anywhere hotkey was found in official sources. |
| Document import | Official docs list upload/listen support for PDF, Word, EPUB, and many other formats across web/mobile apps. Sources: [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version), [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version). | DRM-protected ebooks are explicitly unsupported; exact handling can vary by file. |
| OCR / screenshot | OCR and Scan to Text are subscription features for scanned/image-based files. Sources: [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version), [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version). | Screenshot-area reader behavior was not verified. |
| Audio export | MP3 conversion is a paid feature; free users cannot convert to MP3 and free voices cannot be converted to MP3. Source: [NaturalReader text/audio](https://help.naturalreaders.com/en/articles/11543218-working-with-text-and-audio-personal-version). | Commercial redistribution requires a separate commercial product/license. |
| Queue / resume | NaturalReader supports resume reading in documents, bookmarks, and playback controls. Source: [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version). | Queueing arbitrary selected snippets was not found. |
| Privacy posture | NaturalReader's privacy policy says it collects personal data, usage data, cookies/tracking data, uses service providers/analytics, and transfers data to Canada. Source: [NaturalReader privacy PDF](https://www.naturalreaders.com/media/privacy.pdf). | Needs legal/privacy review before making comparative claims. |
| Windows fit | Web app works in Windows browsers; a shortcut can make it app-like; Chrome extension can be used with Chrome or Edge. Source: [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version). | Native Windows desktop app behavior was not verified for the current personal version. |

### Microsoft Edge Read aloud

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Read aloud is a built-in Microsoft Edge feature. Source: [Microsoft Edge Read aloud](https://www.microsoft.com/en-us/edge/features/read-aloud). | No separate Read aloud pricing page was found; avoid "free" wording unless tied to Edge being installed/available. |
| Offline / local behavior | Microsoft says Read aloud works online and offline, with only a few voice options offline. Source: [Microsoft Edge Read aloud](https://www.microsoft.com/en-us/edge/features/read-aloud). | Voice selection and quality offline were not tested. |
| Selected-text-anywhere behavior | Users can select specific content in Edge and right-click/read aloud selection; it can also launch from address bar or menu. Source: [Microsoft Edge Read aloud](https://www.microsoft.com/en-us/edge/features/read-aloud). | This is not Windows-wide selected text; it is an Edge browser surface. |
| Document import | Edge accessibility copy says Read aloud can listen to text in web pages, PDFs, and documents. Source: [Microsoft Edge accessibility](https://www.microsoft.com/en-us/edge/features/accessibility). | Import/library behavior is not comparable to dedicated document-reader apps. |
| OCR / screenshot | Edge has separate automatic image descriptions for screen readers, but no OCR/screenshot reader for arbitrary selected text was verified in Read aloud sources. Source: [Microsoft Edge accessibility](https://www.microsoft.com/en-us/edge/features/accessibility). | Do not position it as OCR. |
| Audio export | No audio export was found in the checked Microsoft Read aloud sources. | Needs manual product check before using "no export" in public copy. |
| Queue / resume | Read aloud has play/pause and previous/next paragraph controls in Immersive Reader support docs. Source: [Microsoft support - Immersive Reader](https://support.microsoft.com/en-US/edge/use-immersive-reader-in-microsoft-edge). | Cross-session queue/resume was not verified. |
| Privacy posture | The checked Read aloud/accessibility pages do not state content privacy details for this feature. | Needs Microsoft privacy/support review before comparative privacy claims. |
| Windows fit | Edge is available on Windows and Read aloud is built into the browser. Sources: [Microsoft Edge Read aloud](https://www.microsoft.com/en-us/edge/features/read-aloud), [Microsoft Edge accessibility](https://www.microsoft.com/en-us/edge/features/accessibility). | Fit is browser-centric, not tray/global-hotkey-centric. |

### Balabolka

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Official site states Balabolka remains freeware and lists License: Freeware. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Donation/purchase of Cross+A is separate from Balabolka license. |
| Offline / local behavior | Balabolka is a Windows TTS program using voices installed on the system through Microsoft Speech API; portable version can run from USB. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Network behavior/telemetry was not stated in the checked official page. |
| Selected-text-anywhere behavior | Official page says it can read clipboard content and can be controlled by system tray or global hotkeys. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | A PipPal-style selected-text capture hotkey from arbitrary apps was not verified. |
| Document import | Official page lists many supported file formats, including PDF, EPUB, DOCX, PPTX, HTML, RTF, XLSX, and others. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Format fidelity and DRM/scanned-document handling were not verified. |
| OCR / screenshot | Official page links a separate Text Extract Utility, but no OCR/screenshot-reader feature was verified in the main checked page. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Needs product/manual check if OCR matters to the matrix. |
| Audio export | Official page says on-screen text can be saved as an audio file; command-line utility can read aloud or save as audio. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Exact audio formats and batch-export limits were not verified. |
| Queue / resume | Official page mentions system tray/global hotkey control, but not queue/resume. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Queue/resume unknown. |
| Privacy posture | Local Windows/SAPI design is implied by use of installed system voices, but the official page checked does not state a privacy policy or telemetry position. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Do not claim "private" or "no telemetry" without a separate source. |
| Windows fit | Windows/SAPI program, portable version, tray/global hotkeys, and command-line utilities are documented. Source: [Balabolka](https://www.cross-plus-a.com/balabolka.htm). | Modern Windows 11 UX fit was not assessed. |

### ElevenReader

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Pricing/terms show a Free plan with monthly Hours; pricing FAQ says free plans get 10 hours that reset monthly. The comparison block lists Premium monthly price at `$11/month`, and terms define paid subscriptions such as Ultra. Sources: [ElevenReader pricing](https://elevenreader.io/pricing), [ElevenReader terms](https://elevenreader.io/elevenreader-terms). | Promotions, app-store checkout, annual price, and regional taxes were not verified. |
| Offline / local behavior | Offline downloads are a paid/Ultra feature; pricing says offline downloads stay inside ElevenReader and cannot be shared/exported. Sources: [ElevenReader pricing](https://elevenreader.io/pricing), [ElevenReader terms](https://elevenreader.io/elevenreader-terms). | Not local TTS; cloud generation/service behavior is implied by ElevenLabs service terms but not benchmarked. |
| Selected-text-anywhere behavior | ElevenReader is available as iOS, Android, web/desktop, and Chrome extension; it supports uploads, URLs, docs, and pasted text. Sources: [ElevenReader devices](https://help.elevenlabs.io/hc/en-us/articles/26197762328209-Which-devices-is-ElevenReader-available-on), [ElevenReader home](https://elevenreader.io/). | No Windows-wide selected-text hotkey/clipboard behavior was verified. |
| Document import | Official FAQ says users can upload ePubs and PDFs, import articles via links, scan images, and copy/paste text; homepage lists PDFs, URLs, Docs, Texts. Source: [ElevenReader home](https://elevenreader.io/). | Exact file type list beyond examples was not verified. |
| OCR / screenshot | Official FAQ says users can scan content from images. Source: [ElevenReader home](https://elevenreader.io/). | Desktop screenshot-area behavior was not verified. |
| Audio export | Pricing FAQ says audio files cannot be exported from ElevenReader; offline downloads remain within the app. The home FAQ says export audio is only on ElevenLabs web platform or ElevenLabs mobile apps, not ElevenReader. Sources: [ElevenReader pricing](https://elevenreader.io/pricing), [ElevenReader home](https://elevenreader.io/). | Confirm current app UI if export becomes strategically important. |
| Queue / resume | Previously generated audio replay does not cost additional hours; offline downloads can play in-app without Wi-Fi/data. Sources: [ElevenReader pricing](https://elevenreader.io/pricing), [ElevenReader terms](https://elevenreader.io/elevenreader-terms). | Selection queue/resume workflow was not found. |
| Privacy posture | Home FAQ says content is processed securely and not shared or used to train public or third-party models. ElevenLabs privacy says personal data may be stored via third-party cloud services, used for usage understanding/model research, moderated for safety, and users can opt out of training for future Personal Data. Sources: [ElevenReader home](https://elevenreader.io/), [ElevenLabs privacy](https://elevenlabs.io/privacy). | Needs legal/privacy review before condensed comparative claims. |
| Windows fit | Web/desktop users can sign in at `elevenreader.io`; Chrome extension is linked. Source: [ElevenReader devices](https://help.elevenlabs.io/hc/en-us/articles/26197762328209-Which-devices-is-ElevenReader-available-on). | No native Windows tray/app integration was verified. |

### Texthelp Read&Write

| Dimension | Verified facts | Unknowns / hypotheses |
| --- | --- | --- |
| Price / free tier | Official subscription page says Read&Write is available by annual subscription and instructs users to contact Texthelp/Everway for subscription/pricing details. Source: [Read&Write subscription](https://support.texthelp.com/help/what-does-my-readwrite-subscription-include). | Public per-seat price was not found on official pages in this pass. |
| Offline / local behavior | Read&Write for Windows is installed locally on PC; support lists features that require internet, including initial sign-in/activation, updates, Picture Dictionary, Translator, Online Dictation, and Online Voices. Sources: [Read&Write subscription](https://support.texthelp.com/help/what-does-my-readwrite-subscription-include), [Read&Write internet-required features](https://support.texthelp.com/help/wp-readwrite-for-windows-features-that-require-internet-access). | Offline core reading behavior by document/app surface needs product testing. |
| Selected-text-anywhere behavior | Office 365 support says speech is supported by selection and from cursor position in Office Online, and selected-text features work with Office 365 apps. Source: [Read&Write Office 365 support](https://support.texthelp.com/help/readwrite-for-windows-and-office-365-support). | Windows-wide selected-text-anywhere behavior was not verified. |
| Document import | Subscription includes Read&Write and OrbitNote across platforms; Texthelp ePub Reader can open ePubs from Google Drive, within the app, or as a desktop PWA. Sources: [Read&Write subscription](https://support.texthelp.com/help/what-does-my-readwrite-subscription-include), [Texthelp ePub Reader](https://support.texthelp.com/help/using-the-texthelp-epub-reader). | General document import matrix beyond ePub/PDF/Office surfaces was not fully mapped. |
| OCR / screenshot | Read&Write for Windows includes a PDF scan/OCR flow to make image PDFs readable; support also references Screenshot Reader for exam/locked-browser contexts. Sources: [Scan a PDF for reading](https://support.texthelp.com/help/pdfexport/id/5a7b134d8e121ce3715046df), [Using Read&Write with SBAC](https://support.texthelp.com/help/using-readwrite-with-sbac). | Exact OCR limits, accuracy, and screenshot reader availability by license were not verified. |
| Audio export | Office 365 support lists Audio Maker among supported Chrome features for Office Online. The ePub Reader page lists Audio Maker among included Read&Write Chrome tools. Sources: [Read&Write Office 365 support](https://support.texthelp.com/help/readwrite-for-windows-and-office-365-support), [Texthelp ePub Reader](https://support.texthelp.com/help/using-the-texthelp-epub-reader). | Exact export format and Windows desktop availability need confirmation. |
| Queue / resume | No queue/resume fact was found in the checked official sources. | Unknown. |
| Privacy posture | Internet-required-features doc shows multiple online dependencies and initial sign-in/activation. Source: [Read&Write internet-required features](https://support.texthelp.com/help/wp-readwrite-for-windows-features-that-require-internet-access). | Need Everway/Texthelp privacy policy review before comparative privacy claims. |
| Windows fit | Read&Write for Windows is installed locally, supported on Windows 10 or above per current system requirements, and subscription access includes Windows plus browser/mobile surfaces. Sources: [Read&Write system requirements](https://support.texthelp.com/help/system-requirements), [Read&Write subscription](https://support.texthelp.com/help/what-does-my-readwrite-subscription-include). | Education/Work/AtW licensing variants may affect available features. |

## Human Review Questions

- Confirm whether Core has any intentionally hidden/developer-only audio export
  path that should stay out of public positioning.
- Decide whether the competitor matrix should compare only free tiers, paid
  personal plans, or the best available consumer plan per product.
- Legal/privacy review is needed before any claim that PipPal is "more
  private" than a named competitor.
- Product review should decide whether "selected-text-anywhere" means
  Windows-wide clipboard hotkey, browser selection, document click-to-read,
  or any of those.
- Pricing should be rechecked immediately before publication because vendor
  pages can change without notice.

## Source Register

All external sources below were accessed on 2026-05-14.

| Source ID | Source | Notes |
| --- | --- | --- |
| PIP-README | [PipPal README](../README.md) | Local Core features, Windows setup, privacy headline, hotkeys. |
| PIP-PRIVACY | [PipPal privacy](PRIVACY.md) | Local privacy posture and telemetry statement. |
| PIP-ROADMAP | [PipPal roadmap](ROADMAP.md) | Current Core state, future PDF/EPUB import, wording constraints. |
| PIP-SELECTED | [Selected-text reliability evidence](SELECTED_TEXT_RELIABILITY.md) | Limits on "anywhere" / normal-copy behavior. |
| SPEECHIFY-PRICING | [Speechify pricing](https://speechify.com/pricing/) | Free and Premium plan facts. |
| SPEECHIFY-TTS | [Speechify text-to-speech](https://speechify.com/text-to-speech-online/) | Platforms, document/source claims, OCR, download wording. |
| SPEECHIFY-WINDOWS | [Speechify Windows](https://speechify.com/windows/) | Windows app positioning. |
| SPEECHIFY-PRIVACY | [Speechify privacy](https://speechify.com/privacy/) | User content, service providers, sharing/sale posture. |
| NATURAL-FEATURES | [NaturalReader features](https://help.naturalreaders.com/en/articles/8823808-what-features-are-available-in-naturalreader-ai-text-to-speech-personal-version) | Feature availability, OCR, resume, MP3. |
| NATURAL-PRICING | [NaturalReader pricing](https://help.naturalreaders.com/en/articles/8854700-plans-pricing-personal-version) | Plus/Pro plan prices and limits. |
| NATURAL-INTRO | [NaturalReader intro](https://help.naturalreaders.com/en/articles/8584530-what-is-naturalreader-ai-text-to-speech-personal-version) | Platforms and file types. |
| NATURAL-AUDIO | [NaturalReader text/audio](https://help.naturalreaders.com/en/articles/11543218-working-with-text-and-audio-personal-version) | MP3/offline export details. |
| NATURAL-PRIVACY | [NaturalReader privacy PDF](https://www.naturalreaders.com/media/privacy.pdf) | Data collection, service providers, transfers. |
| EDGE-READ | [Microsoft Edge Read aloud](https://www.microsoft.com/en-us/edge/features/read-aloud) | Online/offline, selected text in Edge, browser controls. |
| EDGE-ACCESS | [Microsoft Edge accessibility](https://www.microsoft.com/en-us/edge/features/accessibility) | Read aloud in web pages, PDFs, documents. |
| EDGE-IMMERSIVE | [Microsoft support - Immersive Reader](https://support.microsoft.com/en-US/edge/use-immersive-reader-in-microsoft-edge) | Read aloud toolbar controls. |
| BALABOLKA | [Balabolka](https://www.cross-plus-a.com/balabolka.htm) | Freeware, supported formats, SAPI/local program, audio save. |
| ELEVEN-HOME | [ElevenReader home](https://elevenreader.io/) | Import, scan, export FAQ, privacy FAQ, devices. |
| ELEVEN-PRICING | [ElevenReader pricing](https://elevenreader.io/pricing) | Free hours, `$11/month`, offline downloads, export limits. |
| ELEVEN-TERMS | [ElevenReader terms](https://elevenreader.io/elevenreader-terms) | Hours system, personal use, offline/purchased content terms. |
| ELEVEN-DEVICES | [ElevenReader devices](https://help.elevenlabs.io/hc/en-us/articles/26197762328209-Which-devices-is-ElevenReader-available-on) | iOS/Android/web/desktop availability. |
| ELEVEN-PRIVACY | [ElevenLabs privacy](https://elevenlabs.io/privacy) | Cloud storage, training opt-out, moderation, transfers. |
| TEXTHELP-SUBSCRIPTION | [Read&Write subscription](https://support.texthelp.com/help/what-does-my-readwrite-subscription-include) | Subscription model and platform access. |
| TEXTHELP-SYSTEM | [Read&Write system requirements](https://support.texthelp.com/help/system-requirements) | Current Windows requirements. |
| TEXTHELP-INTERNET | [Read&Write internet-required features](https://support.texthelp.com/help/wp-readwrite-for-windows-features-that-require-internet-access) | Online dependencies and offline notes. |
| TEXTHELP-EPUB | [Texthelp ePub Reader](https://support.texthelp.com/help/using-the-texthelp-epub-reader) | ePub/document surface and Audio Maker tools. |
| TEXTHELP-PDFSCAN | [Scan a PDF for reading](https://support.texthelp.com/help/pdfexport/id/5a7b134d8e121ce3715046df) | OCR/PDF scan workflow. |
| TEXTHELP-SBAC | [Using Read&Write with SBAC](https://support.texthelp.com/help/using-readwrite-with-sbac) | Screenshot Reader evidence. |
| TEXTHELP-O365 | [Read&Write Office 365 support](https://support.texthelp.com/help/readwrite-for-windows-and-office-365-support) | Selection support, Screenshot Reader, Audio Maker in Office Online. |
