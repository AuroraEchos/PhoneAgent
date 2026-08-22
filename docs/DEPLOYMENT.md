# PhoneAgent Website Deployment

The project website is a dependency-free static site located in `docs/`.

The landing page links to a first-party source guide at `guide.html`. The
reader loads the Markdown files under `docs/subsystems/` at runtime, renders
them without a third-party CDN, keeps subsystem links inside the site, and
rewrites source-code links to the public GitHub repository.

## 1. Repository URL

The public repository URL is configured near the top of `docs/script.js`:

```javascript
const SITE_CONFIG = {
  repositoryUrl: "https://github.com/AuroraEchos/PhoneAgent",
  defaultLanguage: "en",
};
```

All GitHub, release, issue, README, license, architecture, and clone links are derived from this value.

## 2. Deploy with GitHub Actions (recommended)

The repository includes `.github/workflows/pages.yml`.

1. Push the repository to GitHub.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Push a change under `docs/`, or manually run the `Deploy GitHub Pages` workflow.

The site will be available at:

```text
https://auroraechos.github.io/PhoneAgent/
```

## 3. Deploy directly from the branch

Instead of the workflow, GitHub Pages can publish the directory directly:

1. Open **Settings → Pages**.
2. Set **Source** to **Deploy from a branch**.
3. Select branch `main` and directory `/docs`.
4. Save the configuration.

Do not enable both deployment methods simultaneously.

## 4. Preview locally

From the repository root:

```bash
python -m http.server 8000 --directory docs
```

Then open:

```text
http://localhost:8000
```

## Static site structure

```text
docs/
├── index.html
├── guide.html
├── guide.js
├── style.css
├── script.js
├── 404.html
├── .nojekyll
├── ARCHITECTURE.md
├── DEPLOYMENT.md
├── subsystems/
│   ├── README.md
│   └── *_SUBSYSTEM.md
└── assets/
    ├── logo.svg
    ├── favicon.svg
    └── og-image.png
```

The site uses no npm packages, CDN scripts, analytics, cookies, or frontend build step.

`scripts/check_static_site.py` verifies the source-guide manifest and the required 1200 × 630
social-preview image. CI, release, and Pages workflows also syntax-check every `docs/*.js` file.
Regenerate the preview asset after a branding change with:

```bash
uv run python scripts/generate_og_image.py
```
