import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { fixupConfigRules, fixupPluginRules } from '@eslint/compat'
import typescriptEslint from '@typescript-eslint/eslint-plugin'
import stylisticTs from '@stylistic/eslint-plugin-ts'
import unicorn from 'eslint-plugin-unicorn'
import _import from 'eslint-plugin-import'
import globals from 'globals'
import tsParser from '@typescript-eslint/parser'
import js from '@eslint/js'
import { FlatCompat } from '@eslint/eslintrc'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const compat = new FlatCompat({
  baseDirectory: __dirname,
  recommendedConfig: js.configs.recommended,
  allConfig: js.configs.all
})

export default [
  {
    ignores: ['**/*.spec.js']
  },
  ...fixupConfigRules(
    compat.extends(
      'eslint:recommended',
      'plugin:@typescript-eslint/recommended',
      'plugin:import/recommended',
      'plugin:import/typescript',
      'prettier'
    )
  ),
  {
    plugins: {
      '@typescript-eslint': fixupPluginRules(typescriptEslint),
      '@stylistic/ts': stylisticTs,
      unicorn,
      import: fixupPluginRules(_import)
    },
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.browser
      },
      parser: tsParser,
      ecmaVersion: 'latest',
      sourceType: 'commonjs'
    },
    settings: {
      'import/resolver': {
        typescript: true,
        node: true
      }
    },
    rules: {
      '@typescript-eslint/no-non-null-assertion': ['off'],
      'no-async-promise-executor': ['off'],
      'no-underscore-dangle': [
        'error',
        {
          allowAfterThis: true
        }
      ],
      'prefer-destructuring': ['off'],
      'comma-dangle': ['error', 'never'],
      semi: ['error', 'never'],
      'object-curly-spacing': ['error', 'always'],
      'unicorn/prefer-node-protocol': 'error',
      '@stylistic/ts/member-delimiter-style': [
        'error',
        {
          multiline: {
            delimiter: 'none',
            requireLast: true
          },
          singleline: {
            delimiter: 'comma',
            requireLast: false
          }
        }
      ],
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/consistent-type-definitions': 'error',
      'import/no-named-as-default': 'off',
      'import/no-named-as-default-member': 'off',
      'import/order': [
        'error',
        {
          groups: [
            'builtin',
            'external',
            'internal',
            'parent',
            'sibling',
            'index'
          ],
          'newlines-between': 'always'
        }
      ]
    }
  },
  {
    files: ['skills/**/*.ts'],
    rules: {
      'import/order': 'off'
    }
  },
  {
    files: ['**/*.ts'],
    rules: {
      '@typescript-eslint/explicit-function-return-type': 'error'
    }
  }
]
