# DEV.to publishing checklist

This package is ready to publish as a draft. It deliberately does **not** publish
to DEV.to. Its cover and diagrams use public raw GitHub URLs that resolve after
the repository changes are pushed to `main`.

## Package contents

- Article: `docs/ARTICLE.md`
- Cover: `docs/assets/agenthop-devto-cover.png` (PNG, 1000 × 420)
- Repository: <https://github.com/Thegm26/AgentHop>

## Publish steps

1. Sign in to DEV.to and create a **new post**.
2. Confirm the repository changes have been pushed to `main`, then open each
   raw GitHub cover/diagram URL from `docs/ARTICLE.md` in a browser. DEV's
   [editor guide](https://dev.to/p/editor_guide) recommends a 1000 × 420 cover
   image; this package's cover uses that size.
3. Paste the article body into DEV's Markdown editor. Preserve the front matter
   but keep `published: false` until the final review.
4. Preview on desktop and mobile. Confirm the title, subtitle, cover crop,
   headings, code blocks, links, and the four tags: `opensource`, `react`,
   `python`, `productivity`.
5. The article already uses uploaded-ready PNG diagrams, not Mermaid fences.
   If a raw GitHub image does not render in DEV's preview, upload the matching
   local asset with the editor and replace only that image URL. Mermaid source
   remains in `docs/diagrams/` for future edits.
6. Proofread the draft for product claims. Keep the independent/unofficial
   disclaimer, MVP limits, backup warning, and AI-assistance disclosure.
7. Open every link from the preview, including the GitHub repository and the
   official Codex documentation links added in the repository README.
8. Add a short editor's note or update date only if it improves accuracy.
9. Change `published` to `true` and publish when the preview is clean.

## Final preflight

- [ ] Cover and diagram raw GitHub URLs resolve after the `main` push and render
      in the preview.
- [ ] No local paths, account names, tokens, session data, or screenshots of
      sensitive state remain in the post.
- [ ] No more than four DEV tags are present.
- [ ] The PNG diagrams render; the Mermaid source files remain available for
      future changes.
- [ ] The article is still honest about being an unofficial, local-first MVP.
- [ ] The GitHub link and quickstart commands were checked from a fresh clone.
