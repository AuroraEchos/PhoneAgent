# PhoneAgent Website Refined UI

This package is a drop-in replacement for the existing `docs/` directory.

## Main refinements

- Scroll progress indicator and active navigation state.
- Cursor spotlight on feature, architecture, terminal, roadmap, and CTA cards.
- Animated runtime steps and subtle hero parallax.
- Open-AutoGLM / Zhipu BigModel acknowledgement strip.
- Recommended `autoglm-phone` provider configuration card.
- Back-to-top control and improved mobile layout.
- More refined glass surfaces, shadows, dividers, and hover states.
- Browser-language detection with persistent language selection.
- Fixed the recursive `writeStoredLanguage()` bug in the previous script.

## Replace

Copy the files in this package over the repository's current `docs/` directory:

```bash
cp -a docs/. /path/to/PhoneAgent/docs/
```

Then preview locally:

```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`.
