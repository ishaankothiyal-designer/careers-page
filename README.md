# Sample careers page

A buildless demo for testing the careers-page repository. Orbit is a fictional company, and all job listings are illustrative. No applications or personal data are collected.

## Run locally

Open `index.html` in a modern browser, or serve this directory:

```sh
python3 -m http.server 8000
```

Then visit http://localhost:8000. No dependencies or build step are required.

## Try the demo

- Search for `designer` to see two roles, or `remote` to see three.
- Choose Engineering to see the Frontend Engineer role.
- Combine a search with a team filter. A query with no matches shows a reset action.
- Select a role to open its details. Close it with the close button or Escape.
- Check the layout on desktop and mobile; all filters and role buttons support keyboard navigation.

## Files

- `index.html`: semantic page structure and role-details dialog.
- `styles.css`: responsive layout, focus styles, and reduced-motion support.
- `script.js`: sample roles, combined filtering, empty state, and dialog behavior.

## Repository setup

An empty GitHub repository needs an initial commit on `main` before a feature branch and pull request can be created. Once `main` exists, put these files on a separate branch and open a pull request against `main`.
