# Running AI Coach Web

This is the frontend for Running AI Coach, a running analysis product that turns FIT files into readable summaries, trend insights, and next-run recommendations.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

The landing page lives in `src/app/page.tsx`.

The first frontend milestone is to support:

- FIT upload
- report rendering
- trend view
- grounded follow-up Q&A

## Scripts

- `npm run dev` starts the app locally.
- `npm run lint` runs ESLint.
- `npm run build` creates a production build.

## Next Steps

1. Replace the static landing page with a real upload flow.
2. Connect to the FastAPI upload endpoint.
3. Add report and trend screens using structured report JSON.
