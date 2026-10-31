// @ts-check
import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

export default defineConfig({
  files: ['**/*.{js,mjs,ts,tsx}'],
  ignores: ['dist/**', 'src/api/schema.d.ts'],
  extends: [js.configs.recommended, tseslint.configs.recommended],
});
