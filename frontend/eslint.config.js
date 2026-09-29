// ESLint: type-aware TypeScript rules, React hooks and accessibility. 0 errors and 0 warnings
// is the gate (spec §13). Fixtures and tooling never reach the product (spec §12.2).

import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'dist/',
      'coverage/',
      'test-results/',
      'playwright-report/',
      'src/api/generated/',
      'tests/fixtures/',
    ],
  },
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/tests/**', '**/tools/**'],
              message: 'Fixtures and tooling never reach the product (spec §12.2).',
            },
          ],
        },
      ],
    },
  },
  {
    // The 3D world drives three.js objects, which are mutable by design: React Three Fiber has
    // effects and frame callbacks change cameras, textures and meshes in place. The compiler's
    // immutability and ref rules cannot tell those objects from React state.
    files: ['src/world/**/*.{ts,tsx}'],
    rules: {
      'react-hooks/immutability': 'off',
      'react-hooks/refs': 'off',
    },
  },
  {
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
  {
    files: ['**/*.js'],
    ...tseslint.configs.disableTypeChecked,
  },
);
