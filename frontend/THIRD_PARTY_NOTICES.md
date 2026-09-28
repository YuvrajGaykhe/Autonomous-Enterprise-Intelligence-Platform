# Third-party notices

This file lists third-party code and assets that were copied or adapted into the frontend (spec §5,
§12.4). Packages installed through `package.json` keep their own licences in `node_modules`.

## Code adapted from shadcn/ui

- **Repository:** https://github.com/shadcn-ui/ui
- **Licence:** MIT, reproduced below.
- **Files:**
  - `src/ui/button.tsx`: the Button component (new-york style), cut down to the variants this app
    uses (`default`, `outline`, `ghost`) and the sizes `default` and `sm`.
  - `src/ui/card.tsx`: the Card component (new-york style), reduced to `Card` and `CardTitle`. `Card`
    renders a `section`.
  - `src/ui/skeleton.tsx`: the Skeleton component (new-york style), unchanged apart from imports.
- **How it was adapted:** shadcn/ui is copied into a project rather than installed. These files
  follow its new-york registry components on the Radix `Slot` primitive, restyled with this app's
  theme variables.

```
MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Fonts

The production build bundles these font files from their Fontsource packages (D-F-18). Each family
is licensed under the SIL Open Font License 1.1, whose text ships in the package's `LICENSE` file:

- Inter: `@fontsource/inter`
- JetBrains Mono: `@fontsource/jetbrains-mono`
- Silkscreen: `@fontsource/silkscreen`

## Vendored code (`src/vendor/`) and models (`public/models/`)

There are none yet. F3 and F4 add them here: the CC0 furniture models and the walk-grid code adapted
from Claw3D.
