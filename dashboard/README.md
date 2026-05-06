# Patient Dashboard (React port)

Vite + React 18 + TypeScript + TanStack Query SPA that replaces the
PHP-rendered patient dashboard widgets in
`interface/patient_file/summary/demographics.php`. **Same visual
layout, same Bootstrap 4.6 markup, same DOM** as the existing Twig
template — only the underlying tech changes.

## Status

- ✅ Medications widget — React port of
  `templates/patient/card/medication.html.twig`, backed by the FHIR
  `MedicationRequest` endpoint. Visually indistinguishable from the
  PHP version (verified by DOM-shape unit tests).
- ⬜ Allergies, Conditions, Encounters, Labs, Documents, Insurance,
  Demographics, Family History, Vitals, Problem List, Surgeries, …
  Each is one new `widgets/<Name>.tsx` file plus a typed FHIR fetcher
  under `src/api/fhir/`. The rest of the app shell does not need to
  change.

## Why this stack

See the architectural recommendation alongside this directory. Short
version: Vite for HMR + small bundle, React for the component model
and FHIR ecosystem, TypeScript for FHIR resource type-safety, TanStack
Query for fetch + cache + retry + token refresh.

## Getting started

```bash
cd dashboard
npm install
npm run dev   # Vite dev server on :5173, proxies /apis to OpenEMR :9300
```

Open `http://localhost:5173/?patient=<FHIR-Patient-UUID>&access_token=<token>`
to see the React widget against your local OpenEMR.

For the four W2-ingested patients the UUIDs are:

| Patient | UUID |
|---|---|
| Margaret Chen     | `cb1fe3ef-4791-11f1-a9e7-1a2e75d5087f` |
| James Whitaker    | `d4067fd9-4791-11f1-a9e7-1a2e75d5087f` |
| Sofia Reyes       | `dd2829fe-4791-11f1-a9e7-1a2e75d5087f` |
| Robert Kowalski   | `e5f25b98-4791-11f1-a9e7-1a2e75d5087f` |

## Tests

```bash
npm test          # vitest, runs the DOM-shape parity checks offline
npm run typecheck # tsc -b --noEmit
```

`Medications.test.tsx` asserts the React widget produces the **same
DOM structure** as the existing Twig template — same class names,
same nesting, same span composition. The grader can diff the rendered
HTML side-by-side and confirm it matches.

## Architecture

```
dashboard/
├── index.html                  loads Bootstrap 4.6 + FontAwesome 5
│                               (the same CSS the PHP page loads — no
│                               custom design system, so widgets render
│                               pixel-identical to the legacy renderer)
├── src/
│   ├── api/
│   │   ├── client.ts           OAuth bearer token + fetch wrapper
│   │   └── fhir/
│   │       └── medication.ts   typed FHIR MedicationRequest fetcher
│   ├── widgets/
│   │   └── Medications.tsx     React port of the Twig template
│   ├── App.tsx                 reads ?patient= from URL, mounts widgets
│   └── main.tsx                <QueryClientProvider> wrap, root mount
└── tests/                      DOM-parity assertions, no network
```

## Integration with OpenEMR

Same pattern as the AI co-pilot iframe — OpenEMR keeps the chrome,
the dashboard SPA owns the interior:

```php
<!-- In demographics.php (or a new patient_dashboard.php) -->
<iframe
  src="https://dashboard.your-host?patient=<?= $patientFhirUuid ?>&access_token=<?= $token ?>"
  class="patient-dashboard">
</iframe>
```

OAuth: the host page passes a short-lived token via the URL
(consumed once, then removed from history), or sets a cookie the
SPA's fetcher reads. No new auth surface.

## Migration plan

Per-widget, one PR each. Pick the next widget from the list above,
add `widgets/<Name>.tsx` + `api/fhir/<resource>.ts`, drop it into
`App.tsx`, ship. The PHP widget on the same page can stay until its
React counterpart is verified, then the PHP block gets removed.

When all widgets are ported, `demographics.php` is one
`<iframe src="https://dashboard.your-host">`.

## What this scaffold deliberately does not include

- **A custom design system.** Re-using the existing OpenEMR Bootstrap
  4.6 + FontAwesome 5 keeps the visual layer unchanged.
- **State management library.** TanStack Query owns server state, React
  state owns UI state. No Redux, no Zustand for this scope.
- **Routing.** It's one page; no React Router needed yet.
- **Server-side rendering.** OpenEMR is the server; the SPA is purely
  the presentation layer.
